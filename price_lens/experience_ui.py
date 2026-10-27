"""EXP controls and local history; pixel capture remains in the existing reader."""
from datetime import datetime
import sqlite3
import time

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFileDialog, QTableWidgetItem, QVBoxLayout, QWidget

from .experience import ExperienceTracker, SessionHistory, duration_text



class ExperiencePanel(QWidget):
    changed = Signal()
    enabled_changed = Signal(bool)

    def __init__(self, history_path, *, enabled=True, window_minutes=5, parent=None):
        super().__init__(parent)
        self.tracker = ExperienceTracker()
        self.history = None
        self.storage_error = ""
        try:
            self.history = SessionHistory(history_path)
        except (OSError, sqlite3.Error) as error:
            self.storage_error = "Session storage unavailable: " + str(error)
        self.connected = False
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
        return self.enabled_check.isChecked()

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
        self.tracker.interrupt()
        if self.tracker.run:
            self.tracker.pause(self.user_paused or not enabled)
        self.enabled_changed.emit(enabled)
        self.refresh()

    def set_connected(self, connected):
        if self.connected and not connected:
            self.tracker.interrupt()
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
        self.map_input.setPlaceholderText(self.tracker.map_name or "Map name · keep the minimap title visible, or enter a name")
        self.persist_completed()
        if accepted and previous and previous.character != self.tracker.current.character:
            self.watch_totals = {"seconds":0.0,"progress":0.0,"exp":0.0}
            self.watch_approximate = False
            self.watch_epoch = time.time()
        if accepted and self.connected and not self.tracker.run and self.tracker.current.character:
            self.start()
        self.refresh()
        self.changed.emit()

    def start(self):
        if self.connected and self.enabled and self.tracker.fresh(time.monotonic()):
            self.tracker.start(self.map_input.text().strip(), self.notes.text().strip())
            if self.user_paused:self.tracker.pause(True)
        self.refresh()
        self.changed.emit()

    def toggle_pause(self):
        self.user_paused = not self.user_paused
        self.tracker.pause(self.user_paused)
        self.refresh()
        self.changed.emit()

    def save(self):
        self.tracker.finish("Session reset")
        self.persist_completed()
        self.watch_totals = {"seconds":0.0,"progress":0.0,"exp":0.0}
        self.watch_epoch = time.time()
        self.watch_approximate = False
        self.user_paused = False
        self.start()
        self.refresh()
        self.changed.emit()

    def persist_completed(self):
        if not self.history:
            return
        saved = False
        while self.tracker.completed:
            try:
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
        if reading:
            self.character.setText(f"{reading.character or 'Character'} · Level {reading.level}")
            self.position.setText(f"{reading.percent/100:.2f}%")
            self.position.setToolTip("Progress through the current level" + (" · last reading" if not fresh else ""))
            self.bar.setValue(reading.percent)
            self.bar.setFormat(f"{reading.exp:,} EXP · {reading.percent/100:.2f}%" + (" · last reading" if not fresh else ""))
        self.pause_button.setEnabled(run is not None and self.enabled)
        self.pause_button.setText("Resume watching" if self.user_paused else "Pause watching")
        self.save_button.setEnabled(run is not None)
        self.map_label.setText(run.map_name if run else self.map_input.text().strip() or tracker.map_name or "Map detected from the minimap · or add a label in Session options")
        self.minute_caption.setText("EXP / MIN" if self.display_mode=="raw" else "PROGRESS / MIN")
        self.hour_caption.setText("EXP / HOUR" if self.display_mode=="raw" else "PROGRESS / HOUR")
        totals = self.totals()
        if run:
            window = tracker.window(300)
            rate,hour = window["rate"],window["exp_hour"]
            prefix = "≈" if run.approximate_exp else ""
            if self.display_mode=="raw":
                self.rate.setText(f"{prefix}{hour/60:,.0f}" if hour is not None else "—")
                self.hour_rate.setText(f"{prefix}{hour:,.0f}" if hour is not None else "—")
            else:
                self.rate.setText(f"{rate*60:+.2f}%" if rate is not None else "—")
                self.hour_rate.setText(f"{rate*3600:+.1f}%" if rate is not None else "—")
            self.raw_hint.setText(f"{prefix}{hour/60:,.0f} EXP/min · {prefix}{hour:,.0f} EXP/hour" if hour is not None else "Raw EXP rates appear with the first stable estimate.")
            self.raw_hint.setVisible(self.display_mode=="both")
            self.observation.setText(f"Smoothed over {duration_text(window['seconds'])} of recent training" if rate is not None else f"Measuring · {round(window['seconds'])} of 30 seconds")
            approximate = self.watch_approximate or run.approximate_exp or any(r.approximate_exp for r in tracker.completed if r.started>=self.watch_epoch)
            total_prefix = "≈" if approximate else ""
            self.gain.setText(f"{total_prefix}{totals['exp']:+,.0f}" if self.display_mode=="raw" else f"{totals['progress']:+.2f}%")
            self.elapsed.setText(duration_text(totals["seconds"]))
            self.eta.setText(duration_text(window["eta"]) if rate is not None and rate>0 else "—")
            self.details.setText(f"Session: {totals['progress']:+.2f}% level progress · {total_prefix}{totals['exp']:,.0f} EXP · {duration_text(totals['seconds'])}\n"+
                                 (f"Recent raw pace: {prefix}{hour/60:,.0f} EXP/min · {prefix}{hour:,.0f} EXP/hour\n" if hour is not None else "")+
                                 "Rates use readable, unpaused time; standing still counts. Missing stretches are excluded. Map changes save a history segment and watching continues."+
                                 (f"\nEXP lost: {run.lost:.2f}%" if run.lost else "")+(f" · {run.gaps} unreadable/paused gap(s)" if run.gaps else ""))
        else:
            self.rate.setText("—");self.hour_rate.setText("—");self.raw_hint.hide()
            self.observation.setText("Watching begins automatically with a readable EXP bar.")
            self.gain.setText("—");self.elapsed.setText("0m 00s");self.eta.setText("—")
            self.details.setText("Your last 500 history segments stay on this device. Percentage progress carries across level-ups; inferred raw EXP totals can be approximate.")
        state = ("EXP watching is off." if not self.enabled else "Start screen reading to watch EXP automatically." if not self.connected else
                 "Watching paused." if self.user_paused else "EXP bar is hidden or unreadable · timer held." if reading and not fresh else
                 "Watching automatically · standing still counts toward your rate." if run else tracker.message)
        self.state.setText(self.storage_error or state)

    def overlay_row(self):
        tracker = self.tracker
        run = tracker.run
        if not run or not tracker.fresh(time.monotonic()):return None
        window = tracker.window(300)
        rate,hour = window["rate"],window["exp_hour"]
        eta = window["eta"]
        title = "EXP watching paused" if self.user_paused else f"Lv. {tracker.current.level+1} in ≈ {duration_text(eta)}" if eta is not None else "Measuring level-up pace…"
        percentage = f"{rate*60:+.2f}%/min · {rate*3600:+.1f}%/hour" if rate is not None else "Collecting 30 seconds of EXP readings"
        prefix = "≈" if run.approximate_exp else ""
        raw = f"{prefix}{hour/60:,.0f} EXP/min · {prefix}{hour:,.0f} EXP/hour" if hour is not None else ""
        text = f"{duration_text(self.totals()['seconds'])} tracked" if self.user_paused else raw if self.display_mode=="raw" and raw else percentage
        return {"key":"experience","kind":"experience","name":title,"text":text,
                "extra":raw if self.display_mode=="both" and not self.user_paused else "","color":"#e4bd7b"}

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
        self.table.setHorizontalHeaderLabels(["Map / date","Level","Time","EXP gain" if self.display_mode=="raw" else "Progress gain","EXP / min" if self.display_mode=="raw" else "Progress / min"])
        self.history_button.setText(f"History · {len(rows)}" if rows else "History")
        bests = {}
        for index, row in enumerate(rows):
            rate = row["progress"]/row["seconds"]*60 if row["seconds"] else 0
            raw_rate = row["exp"]/row["seconds"]*60 if row["seconds"] else 0
            raw_prefix = "≈" if row["approximate_exp"] else ""
            date = datetime.fromtimestamp(row["started"]).strftime("%b %d %H:%M")
            values = [f"{row['map_name']}\n{date}", str(row["start_level"]) + (f"→{row['end_level']}" if row["end_level"] != row["start_level"] else ""),
                      duration_text(row["seconds"]),(f"{raw_prefix}{row['exp']:+,.0f}" if self.display_mode=="raw" else f"{row['progress']:+.2f}%"),
                      (f"{raw_prefix}{raw_rate:,.0f}" if self.display_mode=="raw" else f"{rate:+.2f}%")]
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
        self.tracker.finish("App closed")
        self.persist_completed()
