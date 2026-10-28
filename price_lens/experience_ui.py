"""EXP controls and local history; pixel capture remains in the existing reader."""
from datetime import datetime
import sqlite3
import time

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFileDialog, QTableWidgetItem, QVBoxLayout, QWidget

from .experience import ExperienceTracker, SessionHistory, Run, duration_text
from .mesos import MesoTracker
from .domain import age_text



class ExperiencePanel(QWidget):
    changed = Signal()
    enabled_changed = Signal(bool)
    overlay_changed = Signal(bool)

    def __init__(self, history_path, *, enabled=True, window_minutes=5, parent=None):
        super().__init__(parent)
        self.tracker = ExperienceTracker()
        self.mesos = MesoTracker()
        self.session_checkpoint = 0.0
        self.history = None
        self.storage_error = ""
        try:
            self.history = SessionHistory(history_path)
        except (OSError, sqlite3.Error) as error:
            self.storage_error = "Session storage unavailable: " + str(error)
        self.connected = False
        self.requested = False
        self.paused_window = None
        self.last_character = None
        self.overlay_enabled = True
        self.display_mode = "percent"
        self.user_paused = False
        self.watch_approximate = False
        self.watch_epoch = time.time()
        self.watch_totals = {"seconds":0.0,"progress":0.0,"exp":0.0}
        from .experience_widgets import build
        build(self, QVBoxLayout(self), enabled, window_minutes)
        self.refresh_history()
        self.refresh()

    @property
    def enabled(self):
        return self.requested

    def set_display(self, mode):
        self.display_mode = mode if mode in ("percent","raw","both") else "percent"
        self.refresh()
        self.refresh_history()

    def totals(self):
        values = dict(self.watch_totals)
        runs = list(self.tracker.completed) + ([self.tracker.run] if self.tracker.run else [])
        for run in runs:
            if run.started >= self.watch_epoch:
                for key in values:values[key] += getattr(run,key)
        return values

    def edit_context(self, *_):
        if self.tracker.run:
            self.tracker.run.map_name = self.map_input.text().strip() or self.tracker.map_name or "Unlabelled map"
            self.tracker.run.notes = self.notes.text().strip()
        self.refresh()
        self.changed.emit()

    def set_enabled(self, enabled):
        self.start() if enabled else self.stop()

    def set_connected(self, connected):
        if self.requested:self.mesos.tick(time.monotonic(), self.connected)
        if self.connected and not connected:
            self.tracker.interrupt()
            self.mesos.interrupt()
        self.connected = connected
        self.refresh()

    def feed(self, result):
        if not self.enabled:
            return
        payload = result.get("experience") or {}
        at = result.get("atMs", 0)/1000
        previous = self.tracker.current
        accepted = self.tracker.ingest(payload, at)
        if accepted:
            self.tracker.observe_map(payload, at)
            current = self.tracker.current
            identity = (current.character, current.level)
            if identity != self.last_character:
                self.last_character = identity
                self.refresh_history()
        self.map_input.setPlaceholderText(self.tracker.map_name or "Use the detected map")
        self.persist_completed()
        if accepted and previous and previous.character != self.tracker.current.character:
            self.watch_totals = {"seconds":0.0,"progress":0.0,"exp":0.0}
            self.watch_approximate = False
            self.watch_epoch = time.time()
            self.mesos.reset(time.monotonic())
            self.session_checkpoint = 0.0
        # Never accept a wallet from an unconfirmed character switch.
        character = payload.get('character')
        same_character = not previous or not character or character == previous.character or accepted
        if result.get('walletRead') and same_character:
            self.mesos.tick(time.monotonic(), self.connected)
            self.mesos.ingest(result.get('wallet'), at)
        if accepted and self.connected and not self.tracker.run and self.tracker.current.character:
            self.begin_run()
        self.refresh()
        self.changed.emit()

    def start(self):
        if not self.connected:return
        if not self.requested:
            self.requested=True;self.user_paused=False;self.paused_window=None
            self.watch_totals={"seconds":0.0,"progress":0.0,"exp":0.0}
            self.watch_epoch=time.time();self.watch_approximate=False
            self.mesos.reset(time.monotonic())
            self.session_checkpoint = 0.0
            self.tracker.interrupt();self.enabled_changed.emit(True)
        if self.tracker.fresh(time.monotonic()):self.begin_run()
        self.refresh();self.changed.emit()

    def begin_run(self):
        if self.requested and self.connected and self.tracker.fresh(time.monotonic()):
            self.tracker.start(self.map_input.text().strip(),self.notes.text().strip())
            if self.user_paused:self.tracker.pause(True)

    def stop(self):
        self.mesos.tick(time.monotonic(), self.connected)
        self.finish_wallet_only('Stopped')
        self.tracker.finish("Stopped");self.persist_completed()
        self.requested=False;self.user_paused=False;self.paused_window=None
        self.enabled_changed.emit(False);self.refresh();self.changed.emit()

    def toggle_pause(self):
        if not self.requested:return
        self.user_paused = not self.user_paused
        self.paused_window=self.tracker.window(300).copy() if self.user_paused else None
        self.tracker.pause(self.user_paused)
        self.mesos.tick(time.monotonic(), self.connected)
        self.mesos.pause(self.user_paused)
        self.refresh()
        self.changed.emit()

    def save(self):
        self.tracker.finish("Session reset")
        self.persist_completed()
        self.watch_totals = {"seconds":0.0,"progress":0.0,"exp":0.0}
        self.watch_epoch = time.time()
        self.watch_approximate = False
        self.user_paused = False
        self.mesos.reset(time.monotonic())
        self.session_checkpoint = 0.0
        self.start()
        self.refresh()
        self.changed.emit()

    def persist_completed(self):
        if not self.history:
            return
        saved = False
        while self.tracker.completed:
            try:
                run = self.tracker.completed[0]
                if not getattr(run, '_wallet_saved', False):
                    for key,value in self.mesos.checkpoint().items():setattr(run,key,value)
                    run.session_seconds = max(0,self.mesos.seconds-self.session_checkpoint)
                    self.session_checkpoint = self.mesos.seconds
                    run._wallet_saved = True
                self.history.save(self.tracker.completed[0])
            except (OSError, sqlite3.Error) as error:
                self.storage_error = "Could not save session: " + str(error)
                break
            finished = self.tracker.completed.pop(0)
            if finished.started >= self.watch_epoch:
                self.watch_approximate |= finished.approximate_exp
                for key in self.watch_totals:self.watch_totals[key] += getattr(finished,key)
            saved = True
        if saved:
            self.storage_error = ""
            self.refresh_history()

    def refresh(self, *_):
        tracker = self.tracker
        reading, run = tracker.current, tracker.run
        fresh = self.connected and tracker.fresh(time.monotonic())
        if self.requested:self.mesos.tick(time.monotonic(),self.connected)
        if reading:
            self.character.setText(f"{reading.character or 'Character'} · Level {reading.level}")
        self.character.setVisible(reading is not None)
        self.pause_button.setEnabled(self.enabled)
        self.pause_button.setText("Resume" if self.user_paused else "Pause")
        self.start_button.setVisible(not self.requested)
        self.start_button.setEnabled(self.connected)
        self.pause_button.setVisible(self.requested)
        self.stop_button.setVisible(self.requested)
        self.stop_button.setEnabled(self.requested)
        map_name = (run.map_name if run and run.map_name != 'Unlabelled map' else self.map_input.text().strip() or tracker.map_name)
        self.map_label.setText(map_name)
        self.map_label.setVisible(bool(map_name))
        for unit in self.exp_units:unit.setText('EXP' if self.display_mode=='raw' else '')
        totals = self.totals()
        if run:
            window = self.paused_window if self.user_paused and self.paused_window else tracker.window(300)
            rate,hour = window["rate"],window["exp_hour"]
            prefix = "≈" if run.approximate_exp else ""
            if self.display_mode=="raw":
                self.rate.setText(f"{prefix}{hour/60:,.0f}" if hour is not None else "—")
                self.hour_rate.setText(f"{prefix}{hour:,.0f}" if hour is not None else "—")
            else:
                self.rate.setText(f"{rate*60:+.2f}%" if rate is not None else "—")
                self.hour_rate.setText(f"{rate*3600:+.1f}%" if rate is not None else "—")
            self.raw_hint.setText(f"{prefix}{hour/60:,.0f} EXP/min · {prefix}{hour:,.0f} EXP/hour" if hour is not None else '')
            self.raw_hint.setVisible(self.display_mode=="both" and hour is not None)
            self.observation.setText(f"Recent pace · {duration_text(window['seconds'])} of training" if rate is not None else f"Measuring pace · {max(0,30-round(window['seconds']))}s of readings remaining")
            approximate = self.watch_approximate or run.approximate_exp or any(r.approximate_exp for r in tracker.completed if r.started>=self.watch_epoch)
            total_prefix = "≈" if approximate else ""
            self.gain.setText(f"{total_prefix}{totals['exp']:+,.0f}" if self.display_mode=="raw" else f"{totals['progress']:+.2f}%")
            self.elapsed.setText(duration_text(self.mesos.seconds,seconds_in_hours=True))
            self.eta.setText(duration_text(window["eta"]) if rate is not None and rate>0 else "—")
        else:
            self.rate.setText("—");self.hour_rate.setText("—");self.raw_hint.hide()
            self.observation.setText('')
            self.gain.setText("—");self.elapsed.setText(duration_text(self.mesos.seconds,seconds_in_hours=True));self.eta.setText("—")
        self.observation.setVisible(bool(self.observation.text()))
        state=('' if not self.requested else
               "Screen reading is paused · tracking is held." if not self.connected else
               "Paused · elapsed time and gains are held." if self.user_paused else
               "EXP bar hidden or unreadable · EXP estimates held." if reading and not fresh else
               '' if run else "Waiting for a readable EXP bar…")
        self.state.setText(self.storage_error or state)
        self.state.setVisible(bool(self.storage_error or state))
        self.refresh_mesos()

    def refresh_mesos(self):
        wallet = self.mesos
        now = time.monotonic()
        if self.requested:wallet.tick(now, self.connected)
        self.meso_gain.setText(f'{wallet.gain:+,}' if wallet.observed else '—')
        self.wallet_balance.setText(f'{wallet.current:,}' if wallet.current is not None else '—')
        rate = wallet.rate(now) if self.requested and not self.user_paused else None
        self.meso_rate.setText(f'{rate:+,.0f}' if rate is not None else '—')
        self.meso_hour.setText(f'{rate*60:+,.0f}' if rate is not None else '—')
        from .motion import fading_visibility
        for unit,available in zip(self.meso_units,(wallet.observed,rate is not None,rate is not None)):
            fading_visibility(unit,available)
        fading_visibility(self.wallet_unit,wallet.current is not None)
        if not self.requested:
            status = 'Open the item inventory while tracking to read your wallet.'
        elif self.user_paused:
            status = 'Paused · wallet changes are excluded until tracking resumes.'
        elif wallet.fresh(now):
            status = 'Wallet visible · net change includes purchases, sales and trades.'
        elif wallet.candidate:
            status = 'Confirming wallet balance…'
        elif wallet.last_seen is not None:
            status = f'Last seen {age_text(now-wallet.last_seen)} ago · reopen inventory to update.'
        else:
            status = 'Open the item inventory to read your meso balance.'
        self.meso_status.setText(status)

    def overlay_row(self):
        tracker = self.tracker
        run = tracker.run
        if not self.requested:return None
        if not run or (not self.user_paused and not tracker.fresh(time.monotonic())):
            if not self.mesos.observed:return None
            wallet=self.mesos;now=time.monotonic();rate=wallet.rate(now)
            return {'key':'experience','kind':'experience','color':'#e4bd7b',
                    'name':'EXP/Meso tracking paused' if self.user_paused else 'Meso tracking · EXP bar unreadable',
                    'text':f'Net mesos {wallet.gain:+,}'+(f' · {rate:+,.0f}/min' if rate is not None and not self.user_paused else ''),
                    'extra':f'Wallet {wallet.current:,}'+(' · last seen' if not wallet.fresh(now) else '')}
        window = self.paused_window if self.user_paused and self.paused_window else tracker.window(300)
        rate,hour = window["rate"],window["exp_hour"]
        eta = window["eta"]
        title = "EXP tracking paused" if self.user_paused else f"Lv. {tracker.current.level+1} in ≈ {duration_text(eta)}" if eta is not None else "EXP tracking · estimating pace…"
        percentage = f"{rate*60:+.2f}%/min · {rate*3600:+.1f}%/hour" if rate is not None else f"Estimating pace · {round(window['seconds'])}/30 seconds"
        prefix = "≈" if run.approximate_exp else ""
        raw = f"{prefix}{hour/60:,.0f} EXP/min · {prefix}{hour:,.0f} EXP/hour" if hour is not None else ""
        text = f"{duration_text(self.mesos.seconds)} tracked" if self.user_paused else raw if self.display_mode=="raw" and raw else percentage
        details = [raw] if self.display_mode=="both" and not self.user_paused and raw else []
        if self.mesos.observed:
            rate = self.mesos.rate(time.monotonic())
            detail = f'Meso {self.mesos.gain:+,}'
            if rate is not None and not self.user_paused:detail += f' · {rate:+,.0f}/min'
            elif not self.user_paused and not self.mesos.fresh(time.monotonic()):detail += ' · last seen'
            details.append(detail)
        return {"key":"experience","kind":"experience","name":title,"text":text,
                "extra":'\n'.join(details),"color":"#e4bd7b"}

    def refresh_history(self, *_):
        if not self.history:
            return
        try:
            rows = self.history.rows()
        except (OSError, sqlite3.Error, ValueError) as error:
            self.storage_error = "Could not read session history: " + str(error)
            return
        selected = self.filter.currentData()
        characters = sorted({row["character"] for row in rows if row["character"]})
        self.filter.blockSignals(True)
        self.filter.clear()
        self.filter.addItem("All characters", "")
        for name in characters:
            self.filter.addItem(name, name)
        self.filter.setCurrentIndex(max(0, self.filter.findData(selected)))
        self.filter.blockSignals(False)
        rows = [row for row in rows if not selected or row["character"] == selected]
        self.table.setRowCount(len(rows))
        from .experience_widgets import history_headers
        history_headers(self)
        self.history_button.setText(f"History · {len(rows)}" if rows else "History")
        bests = {}
        for index, row in enumerate(rows):
            rate = row["progress"]/row["seconds"]*60 if row["seconds"] else 0
            raw_rate = row["exp"]/row["seconds"]*60 if row["seconds"] else 0
            raw_prefix = "≈" if row["approximate_exp"] else ""
            date = datetime.fromtimestamp(row["started"]).strftime("%b %d %H:%M")
            values = [f"{row['map_name']}\n{date}", str(row["start_level"]) + (f"→{row['end_level']}" if row["end_level"] != row["start_level"] else ""),
                      duration_text(row.get('session_seconds') if row.get('session_seconds') is not None else row['seconds']),(f"{raw_prefix}{row['exp']:+,.0f}" if self.display_mode=="raw" else f"{row['progress']:+.2f}%"),
                      (f"{raw_prefix}{raw_rate:,.0f}" if self.display_mode=="raw" else f"{rate:+.2f}%"),
                      f"{row['mesos']:+,}" if row.get('mesos') is not None else '—']
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(f"{row['character']} · {row['job']}\n{row['notes']}\n{row['reason']} · {row['gaps']} gap(s)")
                self.table.setItem(index, column, item)
            self.table.setRowHeight(index, 44)
            current = self.tracker.current
            if row["seconds"] >= 120 and not row["gaps"] and current and row["character"] == current.character and row["start_level"] == row["end_level"] == current.level:
                bests[row["map_name"]] = max(bests.get(row["map_name"], float("-inf")), raw_rate if self.display_mode=="raw" else rate)
        self.best.setText("Your best maps: " + " · ".join((f"{name}: {rate:,.0f} EXP/min" if self.display_mode=="raw" else f"{name}: {rate:+.2f}%/min") for name,rate in sorted(bests.items(), key=lambda pair:pair[1], reverse=True)[:2]) if bests else "")
        self.best.setVisible(bool(bests))
        self.best.setToolTip("Tests of 2+ minutes on the same character and level, without unreadable stretches. Use your notes to account for gear and party changes.")
        self.export_button.setEnabled(bool(rows))

    def export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export EXP sessions", "lupin-sessions.csv", "CSV files (*.csv)")
        if path and self.history:
            try:
                self.history.export(path)
            except (OSError, sqlite3.Error) as error:
                self.storage_error = "Export failed: " + str(error)
                self.refresh()

    def close_session(self):
        self.finish_wallet_only('App closed')
        self.tracker.finish("App closed")
        self.persist_completed()

    def finish_wallet_only(self,reason):
        if not self.requested or self.tracker.run or self.mesos.segment_start is None:return
        import uuid
        reading=self.tracker.current
        self.tracker.completed.append(Run(uuid.uuid4().hex,self.watch_epoch,
            reading.character if reading else '', reading.job if reading else '',
            self.map_input.text().strip() or self.tracker.map_name or 'Unlabelled map',self.notes.text().strip(),
            reading.level if reading else 0,reading.level if reading else 0,
            seconds=self.mesos.seconds,reason=reason))
