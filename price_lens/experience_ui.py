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
        from .experience_widgets import build
        build(self, QVBoxLayout(self), enabled, window_minutes)
        self.refresh_history()
        self.refresh()

    @property
    def enabled(self):
        return self.enabled_check.isChecked()

    def select_window(self, index):
        value = self.window_picker.itemData(index)
        self.window_minutes.setVisible(value is None)
        if value is not None:
            self.window_minutes.setValue(value)
        else:
            self.window_minutes.setFocus()
            self.window_minutes.selectAll()
        self.refresh()
        self.changed.emit()

    def edit_context(self, *_):
        if self.tracker.run:
            self.tracker.run.map_name = self.map_input.text().strip() or self.tracker.map_name or "Unlabelled map"
            self.tracker.run.notes = self.notes.text().strip()
        self.refresh()
        self.changed.emit()

    def set_enabled(self, enabled):
        self.tracker.interrupt()
        if not enabled:
            self.tracker.pause(True)
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
        if self.tracker.ingest(payload, at):
            self.tracker.observe_map(payload, at)
            current = self.tracker.current
            identity = (current.character, current.level)
            if identity != self.last_character:
                self.last_character = identity
                self.refresh_history()
        self.map_input.setPlaceholderText(self.tracker.map_name or "Map name · keep the minimap title visible, or enter a name")
        self.persist_completed()
        self.refresh()
        self.changed.emit()

    def start(self):
        if self.connected and self.enabled and self.tracker.fresh(time.monotonic()):
            self.tracker.start(self.map_input.text().strip(), self.notes.text().strip())
        self.refresh()
        self.changed.emit()

    def toggle_pause(self):
        self.tracker.pause(not self.tracker.paused)
        self.refresh()
        self.changed.emit()

    def save(self):
        self.tracker.finish()
        self.persist_completed()
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
            self.tracker.completed.pop(0)
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
        self.start_button.setEnabled(self.enabled and fresh and run is None and bool(reading.character))
        self.start_button.setVisible(run is None)
        self.pause_button.setEnabled(run is not None and self.enabled)
        self.pause_button.setVisible(run is not None)
        self.pause_button.setText("Resume session" if tracker.paused else "Pause session")
        self.save_button.setEnabled(run is not None)
        self.save_button.setVisible(run is not None)
        self.map_label.setText(run.map_name if run else self.map_input.text().strip() or tracker.map_name or "Map detected from the minimap · or add a label in Session options")
        if run:
            window = tracker.window(self.window_minutes.value()*60)
            rate = window["rate"]
            self.rate.setText(f"{rate*self.window_minutes.value()*60:+.2f}% / {self.window_minutes.value()} min" if rate is not None else "Measuring your pace…")
            self.observation.setText(f"Based on {duration_text(window['seconds'])} of recent training" if rate is not None else f"{round(window['seconds'])} of 30 seconds · keep training")
            prefix = "≈" if run.approximate_exp else ""
            eta = duration_text(window["eta"]) if rate is not None and rate > 0 else "—"
            raw = f" · {prefix}{window['exp_hour']:,.0f} EXP/h" if window["exp_hour"] is not None else ""
            self.gain.setText(f"{run.progress:+.2f}%")
            self.elapsed.setText(duration_text(run.seconds))
            self.eta.setText(eta)
            self.details.setText(f"Observed: {window['progress']:+.2f}% in {duration_text(window['seconds'])}{raw}\nSession: {run.progress:+.2f}% · {prefix}{run.exp:,.0f} EXP · {duration_text(run.seconds)} · next level ≈ {eta}" +
                                 (f"\nEXP lost: {run.lost:.2f}%" if run.lost else "") + (f" · {run.gaps} unreadable/paused gap(s)" if run.gaps else ""))
        else:
            self.rate.setText("Ready to train" if fresh else "Waiting for the game")
            self.observation.setText("Start a session to measure your EXP gain.")
            self.gain.setText("—")
            self.elapsed.setText("—")
            self.eta.setText("—")
            self.details.setText("Rates use readable, unpaused time, including time standing still. Missing stretches are excluded. Across level-ups, % means level-progress points; raw EXP totals can be approximate. Your last 500 saved sessions stay on this device.")
        state = ("EXP reading is off." if not self.enabled else "Start screen reading to track EXP." if not self.connected
                 else "EXP bar is hidden or unreadable · session held." if reading and not fresh else tracker.message)
        self.state.setText(self.storage_error or state)

    def overlay_row(self):
        run = self.tracker.run
        if not run:
            return None
        window = self.tracker.window(self.window_minutes.value()*60)
        rate = window["rate"]
        message = ("Session paused" if self.tracker.paused else
                   f"{rate*self.window_minutes.value()*60:+.2f}% / {self.window_minutes.value()}m · next ≈ {duration_text(window['eta'])}" if rate is not None
                   else "Measuring EXP pace…")
        return {"key":"experience", "name":f"EXP · {run.character or 'Session'} · Lv. {self.tracker.current.level}",
                "text":message,"color":"#e4bd7b"}

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
        self.history_button.setText(f"History · {len(rows)}" if rows else "History")
        bests = {}
        for index, row in enumerate(rows):
            rate = row["progress"]/row["seconds"]*300 if row["seconds"] else 0
            date = datetime.fromtimestamp(row["started"]).strftime("%b %d %H:%M")
            values = [f"{row['map_name']}\n{date}", str(row["start_level"]) + (f"→{row['end_level']}" if row["end_level"] != row["start_level"] else ""),
                      duration_text(row["seconds"]),f"{row['progress']:+.2f}%",f"{rate:+.2f}%"]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(f"{row['character']} · {row['job']}\n{row['notes']}\n{row['reason']} · {row['gaps']} gap(s)")
                self.table.setItem(index, column, item)
            self.table.setRowHeight(index, 44)
            current = self.tracker.current
            if row["seconds"] >= 120 and not row["gaps"] and current and row["character"] == current.character and row["start_level"] == row["end_level"] == current.level:
                bests[row["map_name"]] = max(bests.get(row["map_name"], float("-inf")), rate)
        self.best.setText("Your best maps: " + " · ".join(f"{name}: {rate:+.2f}% /5m" for name,rate in sorted(bests.items(), key=lambda pair:pair[1], reverse=True)[:2]) if bests else "")
        self.best.setVisible(bool(bests))
        self.best.setToolTip("Tests of 2+ minutes on the same character and level, without unreadable stretches. Use your notes to account for gear and party changes.")
        self.export_button.setEnabled(bool(rows))

    def export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export EXP sessions", "classic-price-lens-sessions.csv", "CSV files (*.csv)")
        if path and self.history:
            try:
                self.history.export(path)
            except (OSError, sqlite3.Error) as error:
                self.storage_error = "Export failed: " + str(error)
                self.refresh()

    def close_session(self):
        self.tracker.finish("App closed")
        self.persist_completed()
