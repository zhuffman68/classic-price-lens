"""Presentation for automatic EXP watching; no sampling or accounting lives here."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox,QComboBox,QDialog,QDialogButtonBox,QFrame,QHBoxLayout,
    QHeaderView,QLineEdit,QProgressBar,QPushButton,QTableWidget,QVBoxLayout)
from .motion import MotionLabel,RollingLabel


def label(value="",name="",parent=None):
    widget=MotionLabel(value,parent)
    widget.setWordWrap(True);widget.setObjectName(name)
    return widget


def number(value="",name=""):
    widget=RollingLabel(value);widget.setObjectName(name);return widget


def build(panel,layout,enabled,window_minutes=None):
    panel.setObjectName("experiencePage")
    panel.setStyleSheet("""
        QWidget#experiencePage { background: transparent; }
        QFrame#expHero { background: #222b39; border: 1px solid #354255; border-radius: 12px; }
        QFrame#expHero QLabel { border: none; background: transparent; }
        QLabel#expEyebrow { color: #a6b3c5; font-size: 10px; font-weight: 600; }
        QLabel#expIdentity { font-size: 14px; font-weight: 600; color: #edf1f7; }
        QLabel#expMap, QLabel#expMuted { color: #a7b2c2; font-size: 11px; }
        QLabel#expRate { color: #edc68a; font-size: 26px; font-weight: 650; }
        QLabel#expMetric { font-size: 18px; font-weight: 600; color: #e5eaf2; }
        QLabel#expPosition { font-size: 16px; font-weight: 600; color: #dce4ef; }
        QProgressBar { background: #303a48; border: none; border-radius: 3px; }
        QProgressBar::chunk { background: #c6a166; border-radius: 3px; }
        QComboBox, QLineEdit { background: #1b2330; color: #e4eaf3; border: 1px solid #3b485c; border-radius: 6px; padding: 7px 9px; }
        QDialog { background: #171e29; }
        QTableWidget { background: #1c2532; alternate-background-color: #202b3a; border: 1px solid #354255; border-radius: 7px; selection-background-color: #39475c; }
        QHeaderView::section { background: #273344; color: #aebbd0; border: none; padding: 8px 6px; font-size: 10px; }
        QTableWidget::item { padding: 6px; border-bottom: 1px solid #2d394b; }
        QPushButton#expLink { background: transparent; border: none; color: #b8c7dc; padding: 5px 0; text-align: left; }
        QPushButton#expLink:hover { color: #edc68a; }
    """)
    layout.setContentsMargins(0,8,0,0);layout.setSpacing(8)
    identity=QHBoxLayout();names=QVBoxLayout();names.setSpacing(3)
    panel.character=label("Ready to watch your EXP","expIdentity")
    panel.map_label=label("Keep the game's EXP bar visible.","expMap")
    names.addWidget(panel.character);names.addWidget(panel.map_label);identity.addLayout(names,1)
    panel.position=number("—","expPosition");panel.position.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
    identity.addWidget(panel.position);layout.addLayout(identity)
    panel.bar=QProgressBar();panel.bar.setRange(0,10000);panel.bar.setTextVisible(False);panel.bar.setFixedHeight(6)
    layout.addWidget(panel.bar)
    hero=QFrame();hero.setObjectName("expHero")
    hero_layout=QVBoxLayout(hero);hero_layout.setContentsMargins(16,12,16,12);hero_layout.setSpacing(8)
    rate_row=QHBoxLayout()
    panel.minute_caption=label("PROGRESS / MIN","expEyebrow")
    panel.hour_caption=label("PROGRESS / HOUR","expEyebrow")
    panel.rate=number("—","expRate");panel.hour_rate=number("—","expRate")
    for caption,value in ((panel.minute_caption,panel.rate),(panel.hour_caption,panel.hour_rate)):
        column=QVBoxLayout();column.setSpacing(5);column.addWidget(caption);column.addWidget(value);rate_row.addLayout(column,1)
    hero_layout.addLayout(rate_row)
    panel.raw_hint=label("","expMuted");panel.raw_hint.hide();hero_layout.addWidget(panel.raw_hint)
    panel.observation=label("Press Start tracking to begin a session.","expMuted");hero_layout.addWidget(panel.observation)
    metrics=QHBoxLayout()
    panel.gain,panel.elapsed,panel.eta=[number("—","expMetric") for _ in range(3)]
    for title,widget in zip(("SESSION GAIN","TIME WATCHING","NEXT LEVEL"),(panel.gain,panel.elapsed,panel.eta)):
        column=QVBoxLayout();column.setSpacing(5);column.addWidget(label(title,"expEyebrow"));column.addWidget(widget);metrics.addLayout(column,1)
    hero_layout.addLayout(metrics)
    layout.addWidget(hero)
    controls=QHBoxLayout()
    panel.start_button=QPushButton("Start tracking");panel.start_button.setObjectName("primary")
    panel.start_button.clicked.connect(panel.start)
    panel.pause_button=QPushButton("Pause");panel.pause_button.clicked.connect(panel.toggle_pause)
    panel.stop_button=QPushButton("Stop and save");panel.stop_button.clicked.connect(panel.stop)
    panel.save_button=panel.stop_button
    for button in (panel.start_button,panel.pause_button,panel.stop_button):
        button.setMinimumHeight(32);controls.addWidget(button,1)
    layout.addLayout(controls)
    panel.shortcut_hint=label("Super + F10 · Start / pause / resume","expMuted")
    options_row=QHBoxLayout();options_row.addWidget(panel.shortcut_hint,1)
    panel.overlay_check=QCheckBox("Show EXP overlay in the game")
    panel.overlay_check.setChecked(True);panel.overlay_check.toggled.connect(panel.overlay_changed.emit)
    options_row.addWidget(panel.overlay_check);layout.addLayout(options_row)
    panel.state=label("","expMuted");layout.addWidget(panel.state)
    links=QHBoxLayout();panel.options_button=QPushButton("Session options…");panel.history_button=QPushButton("History")
    panel.options_button.setObjectName("expLink")
    panel.history_button.setMinimumHeight(32)
    links.addWidget(panel.options_button);links.addStretch();links.addWidget(panel.history_button);layout.addLayout(links)
    panel.best=label("","expMuted");layout.addWidget(panel.best);layout.addStretch()

    panel.options_dialog = QDialog(panel)
    panel.options_dialog.setWindowTitle("Session options")
    panel.options_dialog.setMinimumWidth(360)
    options = QVBoxLayout(panel.options_dialog)
    options.setContentsMargins(20,20,20,20)
    options.setSpacing(12)
    options.addWidget(label("Give this run some context", "expIdentity"))
    options.addWidget(label("Map names are detected from the minimap. You can enter a label and add notes for comparing your runs.","expMuted"))
    options.addWidget(label("Map or session label", "expEyebrow"))
    panel.map_input = QLineEdit()
    panel.map_input.setMaxLength(160)
    panel.map_input.setPlaceholderText("Use the detected map")
    panel.map_input.setAccessibleName("Training map or session label")
    options.addWidget(panel.map_input)
    options.addWidget(label("Notes", "expEyebrow"))
    panel.notes = QLineEdit()
    panel.notes.setMaxLength(240)
    panel.notes.setPlaceholderText("Weapon, party, buffs… (optional)")
    options.addWidget(panel.notes)
    panel.map_input.textEdited.connect(panel.edit_context)
    panel.notes.textEdited.connect(panel.edit_context)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    buttons.rejected.connect(panel.options_dialog.reject)
    options.addWidget(buttons)
    panel.options_button.clicked.connect(panel.options_dialog.open)

    panel.history_dialog = QDialog(panel)
    panel.history_dialog.setWindowTitle("Training history")
    panel.history_dialog.resize(720,460)
    history = QVBoxLayout(panel.history_dialog)
    history.setContentsMargins(20,20,20,20)
    history.setSpacing(12)
    history.addWidget(label("Training history", "expIdentity"))
    history.addWidget(label("Compare your saved runs. Pace is shown per minute; notes are available on each row.", "expMuted"))
    filters = QHBoxLayout()
    panel.filter = QComboBox()
    panel.filter.currentIndexChanged.connect(panel.refresh_history)
    filters.addWidget(panel.filter,1)
    panel.export_button = QPushButton("Export CSV…")
    panel.export_button.clicked.connect(panel.export)
    filters.addWidget(panel.export_button)
    history.addLayout(filters)
    panel.table = QTableWidget(0,5)
    panel.table.setHorizontalHeaderLabels(["Map / date","Level","Time","EXP gain","Progress / min"])
    panel.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    panel.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    panel.table.setShowGrid(False)
    panel.table.setAlternatingRowColors(True)
    panel.table.verticalHeader().hide()
    panel.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
    for column in range(1,5):panel.table.horizontalHeader().setSectionResizeMode(column,QHeaderView.ResizeMode.ResizeToContents)
    history.addWidget(panel.table,1)
    close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    close.rejected.connect(panel.history_dialog.reject)
    history.addWidget(close)
    panel.history_button.clicked.connect(panel.history_dialog.open)
