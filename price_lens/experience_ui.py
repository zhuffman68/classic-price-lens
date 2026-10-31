"""EXP controls and local history; pixel capture remains in the existing reader."""
from datetime import datetime
from dataclasses import replace
import math
import sqlite3
import time

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFileDialog, QTableWidgetItem, QVBoxLayout, QWidget

from .experience import ExperienceTracker, SessionHistory, Run, Reading, MAX_GAP, duration_text, clock_text
from .mesos import PickupTracker
from .tracking_identity import TrackingIdentity, proof_pixels



class ExperiencePanel(QWidget):
    changed = Signal()
    enabled_changed = Signal(bool)
    overlay_changed = Signal(bool)
    meso_overlay_changed = Signal(bool)
    tracking_epoch_changed = Signal(int)

    def __init__(self, history_path, *, parent=None):
        super().__init__(parent)
        self.tracker = ExperienceTracker()
        self.mesos = PickupTracker()
        self.identity = TrackingIdentity()
        self.numeric_snapshot = None
        self.numeric_at = 0.0
        self.numeric_state = None
        self.rendered_numbers = None
        self.session_checkpoint = 0.0
        self.history = None
        self.storage_error = ""
        try:
            self.history = SessionHistory(history_path)
        except (OSError, sqlite3.Error) as error:
            self.storage_error = "Session storage unavailable: " + str(error)
        self.connected = False
        self.capture_frame_at = None
        self.tracking_epoch = 0
        self.tracking_floor_ms = 0
        self.recognition_held = False
        self.requested = False
        self.paused_window = None
        self.paused_meso_rate = None
        self.reacquiring = False
        self.identity_ready = True
        self.last_character = None
        self.display_mode = "percent"
        self.user_paused = False
        self.paused_context_ready = True
        self.pause_match_at = None
        self.pause_match_reading = None
        self.watch_approximate = False
        self.watch_epoch = time.time()
        self.watch_totals = {"seconds":0.0,"progress":0.0,"exp":0.0}
        from .experience_widgets import build
        build(self, QVBoxLayout(self))
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

    def clock_at(self):
        now=time.monotonic()
        if self.capture_frame_at is not None:now=min(now,self.capture_frame_at)
        return max(now,self.mesos.last_tick) if self.mesos.last_tick is not None else now

    def tick_mesos(self):
        if self.requested:
            self.mesos.tick(self.clock_at(),self.connected and not self.recognition_held)

    def invalidate_tracking(self):
        self.tracking_epoch+=1
        self.tracking_floor_ms=int(time.monotonic()*1000)
        self.tracking_epoch_changed.emit(self.tracking_epoch)

    def set_connected(self, connected, *, frame_at=None, refresh=True):
        # A missing/covered frame never advances the active clock beyond the
        # last verified pixels. Direct panel users may omit a capture clock.
        if frame_at is None:self.capture_frame_at=None
        elif type(frame_at) in (int,float) and math.isfinite(frame_at) and frame_at>0:
            self.capture_frame_at=frame_at
        self.tick_mesos()
        changed=self.connected!=bool(connected)
        if self.connected and not connected:
            self.interrupt_context()
            self.mesos.interrupt()
        self.connected = bool(connected)
        if (self.connected and self.recognition_held
                and not (self.tracker.current and self.tracker.current.character)):
            # Pickup tracking can run with an unreadable EXP bar. If no
            # character has ever been captured there is no identity to match.
            self.recognition_held=False
            self.identity_ready=True
        if refresh or changed:self.refresh()
        if changed:self.changed.emit()

    def interrupt_context(self):
        if self.requested and not self.recognition_held:
            if not self.user_paused:self.hold_pace()
            self.recognition_held=True
            self.reacquiring=not self.user_paused
            self.invalidate_tracking()
            self.paused_context_ready=False
            self.pause_match_at=None;self.pause_match_reading=None
        self.tracker.interrupt()
        self.mesos.interrupt()
        self.identity.candidate=None
        if self.tracker.current:self.identity_ready=False
        if self.user_paused and self.tracker.current and self.tracker.current.character:
            self.paused_context_ready=False;self.pause_match_at=None;self.pause_match_reading=None

    def observe_paused_context(self,payload,at):
        """Identify the visible character without mutating a paused session."""
        original=self.tracker.current
        reading=Reading.parse(payload,at)
        if not original or not original.character or reading is None or at<=original.at:return
        if not reading.same_character(original):
            self.paused_context_ready=False;self.pause_match_at=None;self.pause_match_reading=None
        elif not self.paused_context_ready:
            prior=self.pause_match_reading
            consistent=bool(prior and prior.level==reading.level and reading.exp>=prior.exp
                            and max(prior.bounds[0],reading.bounds[0])<=min(prior.bounds[1],reading.bounds[1]))
            if self.pause_match_at is not None and 0<at-self.pause_match_at<=MAX_GAP and consistent:
                self.paused_context_ready=True;self.pause_match_at=None
            else:self.pause_match_at=at;self.pause_match_reading=reading
        self.identity_ready=self.paused_context_ready

    def feed(self, result):
        if not self.enabled or not self.connected:
            return
        epoch=result.get('trackingEpoch',self.tracking_epoch)
        at_ms=result.get('atMs',0)
        if (type(epoch) is not int or epoch!=self.tracking_epoch
                or type(at_ms) is not int or at_ms<self.tracking_floor_ms):return
        if result.get('pickupsRead') and 'pickupNameProof' in result and self.identity.reference:
            proof=result['pickupNameProof'];pixels=proof_pixels(proof)
            reference=self.identity.reference
            if pixels is None or not self.identity.visual_match(reference,pixels,proof,reference.name)[0]:
                # A same-position game can retain its locator anchors while
                # showing another character. Check this job's name pixels
                # without teaching a new identity or accepting old pickups.
                self.tick_mesos();self.interrupt_context()
                self.refresh();self.changed.emit();return
        raw = result.get("experience") or {}
        payload = self.identity.prepare(raw) if 'experience' in result else {}
        at = at_ms/1000
        resumed_level=None
        if self.user_paused or self.recognition_held:
            self.observe_paused_context(payload,at)
            if not self.paused_context_ready:
                self.refresh();self.changed.emit();return
            if self.recognition_held:
                # Reanchor the active clock before releasing the automatic
                # hold, excluding the time spent confirming the old identity.
                self.mesos.tick(self.clock_at(),False)
                self.recognition_held=False
                reading=Reading.parse(payload,at)
                if reading and self.tracker.current and reading.level!=self.tracker.current.level:
                    resumed_level=reading
            if self.user_paused:
                self.refresh();self.changed.emit();return
        previous = self.tracker.current
        if previous and payload.get('identityKey') and previous.identity_key:
            if payload['identityKey']!=previous.identity_key:self.identity_ready=False
        if resumed_level is not None:
            # Two matching identity/level/bounds observations establish a new
            # baseline after hidden level gains, without closing the old run.
            prior=self.pause_match_reading
            self.tracker.current=replace(resumed_level,at=previous.at)
            self.tracker.bounds=(max(prior.bounds[0],resumed_level.bounds[0]),
                                 min(prior.bounds[1],resumed_level.bounds[1]))
            self.tracker.baseline=None;self.tracker.candidate=None;self.tracker.recovery.clear()
        accepted = self.tracker.ingest(payload, at) if 'experience' in result else False
        if accepted:
            display_name=self.identity.accept(payload,at)
            if display_name and self.tracker.refine_character(payload.get('identityKey'),display_name):
                held_reading=self.numeric_snapshot.get('reading') if self.numeric_snapshot else None
                if held_reading and held_reading.identity_key==payload.get('identityKey'):
                    self.numeric_snapshot['reading']=replace(held_reading,character=display_name)
                if self.history:
                    try:self.history.refine_character(payload['identityKey'],display_name)
                    except (OSError,sqlite3.Error,ValueError) as error:self.storage_error='Could not update character spelling: '+str(error)
            self.identity_ready=True
            self.reacquiring=False;self.paused_window=None;self.paused_meso_rate=None
            self.tracker.observe_map(payload, at)
            current = self.tracker.current
            identity = (current.character, current.level)
            if identity != self.last_character:
                self.last_character = identity
                self.refresh_history()
        self.map_input.setPlaceholderText(self.tracker.map_name or "Use the detected map")
        self.persist_completed()
        if accepted and previous and not previous.same_character(self.tracker.current):
            self.watch_totals = {"seconds":0.0,"progress":0.0,"exp":0.0}
            self.watch_approximate = False
            self.watch_epoch = time.time()
            self.mesos.reset(time.monotonic())
            self.session_checkpoint = 0.0
        # Never accept pickups from an unconfirmed character switch.
        character = payload.get('character')
        identity=payload.get('identityKey')
        if identity and previous and previous.identity_key:
            same_character=identity==previous.identity_key or accepted
        else:same_character=not previous or not character or character==previous.character or accepted
        if (result.get('pickupsRead') and same_character and self.tracker.candidate is None
                and not (previous and not self.identity_ready)):
            self.tick_mesos()
            self.mesos.ingest(result.get('pickups'), at)
        if accepted and self.connected and not self.tracker.run and self.tracker.current.character:
            self.begin_run()
        self.refresh()
        self.changed.emit()

    def start(self):
        if not self.connected:return
        if not self.requested:
            self.invalidate_tracking()
            self.requested=True;self.user_paused=False;self.paused_window=None
            self.paused_meso_rate=None;self.reacquiring=True
            self.recognition_held=False
            self.paused_context_ready=True;self.pause_match_at=None;self.pause_match_reading=None
            self.watch_totals={"seconds":0.0,"progress":0.0,"exp":0.0}
            self.watch_epoch=time.time();self.watch_approximate=False
            self.mesos.reset(time.monotonic())
            self.session_checkpoint = 0.0
            self.tracker.reset_pace();self.tracker.interrupt();self.enabled_changed.emit(True)
        self.refresh();self.changed.emit()

    def begin_run(self):
        if self.requested and self.connected and self.tracker.fresh(time.monotonic()):
            self.tracker.start(self.map_input.text().strip(),self.notes.text().strip())
            if self.user_paused:self.tracker.pause(True)

    def stop(self):
        self.tick_mesos()
        self.invalidate_tracking()
        self.finish_meso_only('Stopped')
        self.tracker.finish("Stopped");self.persist_completed()
        self.requested=False;self.user_paused=False;self.paused_window=None
        self.paused_meso_rate=None;self.reacquiring=False
        self.recognition_held=False
        self.paused_context_ready=True;self.pause_match_at=None;self.pause_match_reading=None
        self.enabled_changed.emit(False);self.refresh();self.changed.emit()

    def hold_pace(self):
        values=self.numeric_snapshot
        self.paused_window=(values.get('window') if values else self.tracker.window(300)).copy()
        self.paused_meso_rate=values.get('meso_rate') if values else self.mesos.rate(time.monotonic())

    def toggle_pause(self):
        if not self.requested:return
        if self.user_paused and not self.paused_context_ready:return
        self.tick_mesos()
        self.invalidate_tracking()
        if not self.user_paused:self.hold_pace()
        self.user_paused = not self.user_paused
        self.paused_context_ready=not self.recognition_held
        self.pause_match_at=None;self.pause_match_reading=None
        self.reacquiring=not self.user_paused
        self.tracker.pause(self.user_paused)
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
                if not getattr(run, '_meso_saved', False):
                    for key,value in self.mesos.checkpoint().items():setattr(run,key,value)
                    run.session_seconds = max(0,self.mesos.seconds-self.session_checkpoint)
                    self.session_checkpoint = self.mesos.seconds
                    run._meso_saved = True
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

    def numeric_values(self,now=None):
        """One two-second numeric snapshot shared by the panel and overlays."""
        now=time.monotonic() if now is None else now
        run=self.tracker.run;reading=self.tracker.current
        state=(self.requested,self.user_paused,self.recognition_held,self.reacquiring,self.identity_ready,self.paused_context_ready,self.connected,self.display_mode,
               run.id if run else None,(reading.identity_key or reading.character) if reading else '',reading.level if reading else None,self.mesos.observed)
        if self.numeric_snapshot is not None and state==self.numeric_state and now-self.numeric_at<2:return self.numeric_snapshot
        held=(self.user_paused or self.reacquiring) and self.paused_window is not None
        meso_held=(self.user_paused or self.recognition_held or not self.connected or self.reacquiring and not self.identity_ready) and self.paused_window is not None
        window=self.paused_window if held else self.tracker.window(300)
        self.numeric_state=state;self.numeric_at=now
        self.numeric_snapshot=dict(run=run,reading=reading,window=window.copy(),totals=self.totals(),
            meso_gain=self.mesos.gain,meso_observed=self.mesos.observed,last_pickup=self.mesos.last_pickup,
            meso_rate=(self.paused_meso_rate if meso_held else self.mesos.rate(now)) if self.mesos.observed else None,
            meso_gaps=self.mesos.gaps)
        return self.numeric_snapshot

    def exp_waiting(self):
        if self.reacquiring:
            return 'Reading EXP bar · confirmed values are held.', 'Reacquiring' if self.tracker.current else 'Reading EXP'
        issue = self.tracker.read_issue
        if issue == 'inconsistent':
            return 'Checking EXP values · estimates held.', 'Checking EXP'
        if issue == 'identity':
            return 'Character name unreadable · EXP estimates held.', 'Checking name'
        if issue == 'confirming':
            return 'Confirming level or EXP change · estimates held.', 'Confirming EXP'
        return 'Reading held · waiting for a clear EXP bar.', 'Reading held'

    def refresh(self, *_):
        tracker = self.tracker
        reading, run = tracker.current, tracker.run
        fresh = self.connected and tracker.fresh(time.monotonic())
        self.tick_mesos()
        self.elapsed.setText(clock_text(self.mesos.seconds))
        if reading:
            self.character.setText(reading.character or 'Character')
            self.level_label.setText(f'Level {reading.level}')
        self.character.setVisible(reading is not None)
        self.level_label.setVisible(reading is not None)
        self.pause_button.setEnabled(self.enabled and (not self.user_paused or self.paused_context_ready))
        self.pause_button.setText("Resume" if self.user_paused else "Pause")
        self.start_button.setVisible(not self.requested)
        self.start_button.setEnabled(self.connected)
        self.pause_button.setVisible(self.requested)
        self.stop_button.setVisible(self.requested)
        self.stop_button.setEnabled(self.requested)
        map_name = (run.map_name if run and run.map_name != 'Unlabelled map' else self.map_input.text().strip() or tracker.map_name)
        display_map=map_name
        if not self.map_input.text().strip() and map_name==tracker.map_name and ': ' in map_name:
            display_map=map_name.split(': ',1)[1]
        self.map_label.setText(display_map)
        self.map_label.setToolTip(map_name)
        self.map_label.setVisible(bool(map_name))
        values=self.numeric_values();update=values is not self.rendered_numbers
        if update:self.rendered_numbers=values;self.refresh_numbers(values)
        state=('' if not self.requested else
               "Screen reading is paused · tracking is held." if not self.connected else
               f"Paused · confirming {reading.character}." if self.recognition_held and reading else
               f"Paused · waiting for {reading.character}." if self.user_paused and not self.paused_context_ready and reading else
               "Paused · elapsed time and gains are held." if self.user_paused else
               self.exp_waiting()[0] if reading and not fresh else
               '' if run else "Waiting for a readable EXP bar…")
        self.state.setText(self.storage_error or state)
        self.state.setVisible(bool(self.storage_error or state))
        self.refresh_mesos(values,update)

    def refresh_numbers(self,values):
        run=values['run'];reading=values['reading'];window=values['window'];totals=values['totals']
        target=reading.level+1 if reading and reading.level<200 else '—'
        self.eta_caption.setText(f'Level {target} · ETA')
        if run:
            rate,hour=window['rate'],window['exp_hour'];prefix='≈' if run.approximate_exp else ''
            if self.display_mode=='raw':
                self.rate.setText(f'{prefix}{hour/60:,.0f} EXP' if hour is not None else '—')
                self.hour_rate.setText(f'{prefix}{hour:,.0f} EXP' if hour is not None else '—')
            else:
                self.rate.setText(f'{rate*60:+.2f}%' if rate is not None else '—')
                self.hour_rate.setText(f'{rate*3600:+.1f}%' if rate is not None else '—')
            self.raw_hint.setText(f"{prefix}{totals['exp']:+,.0f} EXP gained · {prefix}{hour/60:,.0f}/min · {prefix}{hour:,.0f}/hour" if hour is not None else '')
            self.raw_hint.setVisible(self.display_mode=='both' and hour is not None)
            self.observation.setText('' if rate is not None else f"Measuring pace · {max(0,30-round(window['seconds']))}s of clear EXP readings remaining")
            approximate=self.watch_approximate or run.approximate_exp or any(r.approximate_exp for r in self.tracker.completed if r.started>=self.watch_epoch)
            total_prefix='≈' if approximate else ''
            self.gain.setText(f"{total_prefix}{totals['exp']:+,.0f} EXP" if self.display_mode=='raw' else f"{totals['progress']:+.2f}%")
            self.eta.setText(duration_text(window['eta']) if rate is not None and rate>0 else '—')
        else:
            self.rate.setText('—');self.hour_rate.setText('—');self.raw_hint.hide();self.observation.setText('');self.gain.setText('—');self.eta.setText('—')
        self.observation.setVisible(bool(self.observation.text()))

    def refresh_mesos(self,values,update):
        pickups = self.mesos
        now = time.monotonic()
        if update:
            self.meso_gain.setText(f"{values['meso_gain']:+,} mesos" if values['meso_observed'] else '—')
            rate=values['meso_rate']
            self.meso_rate.setText(f'{rate:+,.0f} mesos' if rate is not None else '—')
            self.meso_hour.setText(f'{rate*60:+,.0f} mesos' if rate is not None else '—')
            for caption in self.meso_captions:caption.setVisible(values['meso_observed'])
        if not self.requested:
            status = ''
        elif not self.connected:
            status = 'Screen reading paused · pickups are held.'
        elif self.user_paused:
            status = 'Paused · recent pace held.'
        elif self.recognition_held:
            status = 'Paused · confirming the captured character.'
        elif pickups.fresh(now):
            status = 'Recent pace · watching pickups' + (f" · {values['meso_gaps']} gap(s)" if values['meso_gaps'] else '')
        elif pickups.candidate:
            status = 'Confirming pickup message…'
        elif pickups.last_seen is not None:
            status = 'Pickup messages obscured · waiting for a clear view.'
        else:
            status = 'Watching for pickup messages…'
        self.meso_status.setText(status)
        self.meso_status.setVisible(bool(status))

    def overlay_rows(self, now=None):
        now=time.monotonic() if now is None else now
        if not self.requested or self.recognition_held or self.user_paused and not self.paused_context_ready:
            return []
        tracker=self.tracker;values=self.numeric_values(now);run=values['run'];reading=values['reading'];window=values['window']
        rate,hour=window['rate'],window['exp_hour'];totals=values['totals']
        held=self.user_paused or not self.connected
        raw=self.display_mode=='raw'
        prefix='≈' if self.watch_approximate or run and run.approximate_exp else ''
        gain=f"{prefix}{totals['exp']:+,.0f} EXP" if raw else f"{totals['progress']:+.2f}%"
        if not run and not totals['seconds']:gain='—'
        minute=f'{prefix}{hour/60:,.0f} EXP' if raw and hour is not None else f'{rate*60:+.2f}%' if rate is not None else '—'
        hourly=f'{prefix}{hour:,.0f} EXP' if raw and hour is not None else f'{rate*3600:+.1f}%' if rate is not None else '—'
        status='Paused' if held else f"Measuring pace · {max(0,30-round(window['seconds']))}s" if rate is None else ''
        if not held and not tracker.fresh(now):status=self.exp_waiting()[0]
        note='Paused' if held else self.exp_waiting()[1] if not tracker.fresh(now) else f"Reading pace · {round(window['seconds'])}/30s" if rate is None else ''
        eta=duration_text(window['eta']) if window['eta'] is not None else '—'
        target=reading.level+1 if reading and reading.level<200 else '—'
        progress=f'{reading.percent/100:.2f}%' if reading else '—'
        clock=clock_text(self.mesos.seconds)
        exp=dict(key='experience',kind='tracking',name='EXP'+(f' · {reading.character} · Lv. {reading.level}' if reading else ''),
            text=gain,color='#e4bd7b',metrics=[('Gained',gain),('Per minute',minute),('Per hour',hourly)],
            footer=f'Level {target} · ETA {eta}',status=status,compact_note=note,
            basis='',clock=clock,progress=progress)
        if self.display_mode=='both' and hour is not None:
            exp['secondary']=f"{prefix}{totals['exp']:+,.0f} EXP · {prefix}{hour/60:,.0f} EXP/min · {prefix}{hour:,.0f} EXP/hour"
        pickups=self.mesos;meso_rate=values['meso_rate']
        meso_status=('Paused' if held else 'Watching pickup messages' if pickups.fresh(now) else 'Waiting for a clear pickup log')
        if pickups.gaps:meso_status+=f' · {pickups.gaps} gap(s)'
        total=f"{values['meso_gain']:+,}" if values['meso_observed'] else '—'
        last=values['last_pickup'];last_text=f'Last pickup: +{last:,}' if last is not None else 'Last pickup: —'
        meso=dict(key='meso-gain',kind='tracking',name='Meso gained',text=total,color='#b7d4a9',
            metrics=[('Picked up',total),('Per minute',f'{meso_rate:+,.0f}' if meso_rate is not None else '—'),
                     ('Per hour',f'{meso_rate*60:+,.0f}' if meso_rate is not None else '—')],footer=last_text,
            status=meso_status,compact_note='Paused' if held else 'Log hidden' if not pickups.fresh(now) else '',
            basis='',clock=clock,progress='')
        return [exp,meso]

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
        selected=self.filter.currentData()
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
                item.setToolTip(f"{row['character']} · {row['job']}\n{row['notes']}\n{row['reason']} · {row['gaps']} EXP gap(s)\nMeso basis: {row.get('meso_basis','wallet')} · {row.get('pickup_gaps',0)} pickup gap(s)")
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
        self.finish_meso_only('App closed')
        self.tracker.finish("App closed")
        self.persist_completed()

    def finish_meso_only(self,reason):
        if not self.requested or self.tracker.run or not self.mesos.observed:return
        import uuid
        reading=self.tracker.current
        self.tracker.completed.append(Run(uuid.uuid4().hex,self.watch_epoch,
            reading.character if reading else '', reading.job if reading else '',
            self.map_input.text().strip() or self.tracker.map_name or 'Unlabelled map',self.notes.text().strip(),
            reading.level if reading else 0,reading.level if reading else 0,
            seconds=self.mesos.seconds,reason=reason,identity_key=reading.identity_key if reading else ''))
