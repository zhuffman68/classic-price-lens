"""EXP controls and local history; pixel capture remains in the existing reader."""
from datetime import datetime
import sqlite3
import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QProgressBar, QPushButton, QSpinBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .experience import ExperienceTracker, SessionHistory, duration_text


def text(value="", style=""):
    widget = QLabel(value)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    widget.setStyleSheet(style)
    return widget


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
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(9)
        self.enabled_check = QCheckBox("Read EXP from the visible status bar")
        self.enabled_check.setChecked(enabled)
        self.enabled_check.toggled.connect(self.set_enabled)
        layout.addWidget(self.enabled_check)
        self.character = text("Waiting for a readable EXP bar", "font-size: 14px; font-weight: 650")
        layout.addWidget(self.character)
        self.bar = QProgressBar()
        self.bar.setRange(0, 10_000)
        self.bar.setFormat("EXP —")
        self.bar.setMaximumHeight(20)
        layout.addWidget(self.bar)
        window_row = QHBoxLayout()
        window_row.addWidget(text("Compare pace over"))
        self.window_minutes = QSpinBox()
        self.window_minutes.setRange(1, 60)
        self.window_minutes.setSuffix(" min")
        self.window_minutes.setValue(max(1, min(60, window_minutes)))
        self.window_minutes.valueChanged.connect(self.refresh)
        self.window_minutes.valueChanged.connect(lambda: self.changed.emit())
        window_row.addWidget(self.window_minutes)
        window_row.addStretch()
        layout.addLayout(window_row)
        self.rate = text("Start a session to measure your pace.", "font-size: 18px; font-weight: 650; color: #e4bd7b")
        self.details = text("", "color: #a6b1bf; font-size: 11px")
        layout.addWidget(self.rate)
        layout.addWidget(self.details)
        self.map_input = QLineEdit()
        self.map_input.setMaxLength(160)
        self.map_input.setPlaceholderText("Map name · detected from the minimap, or enter your own")
        self.map_input.setAccessibleName("Training map or session label")
        layout.addWidget(self.map_input)
        self.notes = QLineEdit()
        self.notes.setMaxLength(240)
        self.notes.setPlaceholderText("Optional notes: weapon, party, buffs…")
        layout.addWidget(self.notes)
        buttons = QHBoxLayout()
        self.start_button = QPushButton("Start session")
        self.start_button.setObjectName("primary")
        self.start_button.clicked.connect(self.start)
        self.pause_button = QPushButton("Pause session")
        self.pause_button.clicked.connect(self.toggle_pause)
        self.save_button = QPushButton("Save session")
        self.save_button.clicked.connect(self.save)
        for button in (self.start_button, self.pause_button, self.save_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.state = text("", "font-size: 11px; color: #a6b1bf")
        layout.addWidget(self.state)
        layout.addWidget(text("Saved sessions", "font-size: 14px; font-weight: 650"))
        filter_row = QHBoxLayout()
        self.filter = QComboBox()
        self.filter.addItem("All characters", "")
        self.filter.currentIndexChanged.connect(self.refresh_history)
        filter_row.addWidget(self.filter, 1)
        self.export_button = QPushButton("Export CSV…")
        self.export_button.clicked.connect(self.export)
        filter_row.addWidget(self.export_button)
        layout.addLayout(filter_row)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Map / date", "Level", "Time", "Net EXP %", "% / 5 min"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, 5):
            self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setMinimumHeight(140)
        layout.addWidget(self.table, 1)
        self.best = text("Run a few tests on different maps to compare them here.", "font-size: 11px; color: #a6b1bf")
        layout.addWidget(self.best)
        layout.addWidget(text("Rates use readable, unpaused time, including time standing still. Missing stretches are excluded. Across level-ups, % means level-progress points; EXP totals can be approximate.", "font-size: 10px; color: #939eac"))
        self.refresh_history()
        self.refresh()

    @property
    def enabled(self):
        return self.enabled_check.isChecked()

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
            self.character.setText(f"{reading.character or 'Character'} · Lv. {reading.level}" + (f" {reading.job}" if reading.job else ""))
            self.bar.setValue(reading.percent)
            self.bar.setFormat(f"{reading.exp:,} EXP · {reading.percent/100:.2f}%" + (" · last reading" if not fresh else ""))
        self.start_button.setEnabled(self.enabled and fresh and run is None and bool(reading.character))
        self.pause_button.setEnabled(run is not None and self.enabled)
        self.pause_button.setText("Resume session" if tracker.paused else "Pause session")
        self.save_button.setEnabled(run is not None)
        self.map_input.setEnabled(run is None)
        self.notes.setEnabled(run is None)
        if run:
            window = tracker.window(self.window_minutes.value()*60)
            rate = window["rate"]
            self.rate.setText(f"Pace {rate*self.window_minutes.value()*60:+.2f}% / {self.window_minutes.value()} min" if rate is not None else "Measuring pace · needs 30 seconds")
            prefix = "≈" if run.approximate_exp else ""
            eta = duration_text(window["eta"]) if rate is not None and rate > 0 else "—"
            raw = f" · {prefix}{window['exp_hour']:,.0f} EXP/h" if window["exp_hour"] is not None else ""
            self.details.setText(f"Observed: {window['progress']:+.2f}% in {duration_text(window['seconds'])}{raw}\nSession: {run.progress:+.2f}% · {prefix}{run.exp:,.0f} EXP · {duration_text(run.seconds)} · next level ≈ {eta}" +
                                 (f"\nEXP lost: {run.lost:.2f}%" if run.lost else "") + (f" · {run.gaps} unreadable/paused gap(s)" if run.gaps else ""))
        else:
            self.rate.setText("Start a session to measure your pace.")
            self.details.setText("Start, train, then save. Your last 500 sessions stay on this device.")
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
        self.best.setText("Your best tests at this level (2+ min, no gaps): " + " · ".join(f"{name}: {rate:+.2f}% /5m" for name,rate in sorted(bests.items(), key=lambda pair:pair[1], reverse=True)[:3])
                          if bests else "Personal map comparisons use tests of 2+ minutes on the same character and level, without missing stretches. Notes help account for gear and party changes.")
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
