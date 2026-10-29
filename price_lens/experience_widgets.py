"""Presentation for automatic EXP watching; no sampling or accounting lives here."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from pathlib import Path
from PySide6.QtWidgets import (QCheckBox,QComboBox,QDialog,QDialogButtonBox,QFrame,QHBoxLayout,QFormLayout,
    QHeaderView,QLineEdit,QPushButton,QTableWidget,QVBoxLayout,QWidget,QSizePolicy)
from .motion import MotionLabel,RollingLabel


def label(value="",name="",parent=None):
    widget=MotionLabel(value,parent)
    widget.setWordWrap(True);widget.setObjectName(name)
    return widget


def number(value="",name=""):
    widget=RollingLabel(value);widget.setObjectName(name);return widget


def build(panel,layout):
    panel.setObjectName("experiencePage")
    panel.setStyleSheet("""
        QWidget#experiencePage { background: transparent; }
        QFrame#expHero { background: #222b39; border: none; border-radius: 12px; }
        QFrame#expHero QWidget { background: transparent; border: none; }
        QFrame#expHero QLabel { border: none; background: transparent; }
        QLabel#expEyebrow { color: #a6b3c5; font-size: 10px; font-weight: 600; }
        QLabel#trackingHeading { color: #edf1f7; font-size: 15px; font-weight: 650; }
        QLabel#expIdentity { font-size: 14px; font-weight: 500; color: #edf1f7; }
        QLabel#expLevel { font-size:11px; color:#b5c2d4; background:#283344; border-radius:5px; padding:3px 7px; }
        QLabel#expMap, QLabel#expMuted { color: #a7b2c2; font-size: 11px; }
        QLabel#trackingFigure { color: #edc68a; font-size: 21px; font-weight: 500; }
        QLabel#mesoFigure { color: #edc68a; font-size: 19px; font-weight: 500; }
        QLabel#expMetric { font-size: 18px; font-weight: 600; color: #e5eaf2; }
        QLabel#trackingClock { font-size: 29px; font-weight: 500; color: #e5eaf2; }
        QLabel#expPosition { font-size: 16px; font-weight: 600; color: #dce4ef; }
        QComboBox, QLineEdit { background: #1b2330; color: #e4eaf3; border: 1px solid #3b485c; border-radius: 6px; padding: 7px 9px; }
        QDialog { background: #171e29; }
        QTableWidget { background: #1c2532; alternate-background-color: #202b3a; border: 1px solid #354255; border-radius: 7px; selection-background-color: #39475c; }
        QHeaderView::section { background: #273344; color: #aebbd0; border: none; padding: 8px 6px; font-size: 10px; }
        QTableWidget::item { padding: 6px; border-bottom: 1px solid #2d394b; }
    """)
    layout.setContentsMargins(0,5,0,0);layout.setSpacing(9)
    identity=QHBoxLayout();identity.setContentsMargins(15,0,15,0);identity.setSpacing(8)
    panel.character=label('', 'expIdentity');panel.character.setWordWrap(False)
    panel.level_label=label('','expLevel');panel.level_label.setWordWrap(False)
    panel.level_label.setSizePolicy(QSizePolicy.Policy.Maximum,QSizePolicy.Policy.Fixed)
    panel.level_label.setProperty('currencyIcon',False)
    panel.map_label=label('', 'expMap');panel.map_label.setWordWrap(False)
    panel.map_label.setProperty('elideRight',True)
    panel.map_label.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
    panel.map_label.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
    identity.addWidget(panel.character,0);identity.addWidget(panel.level_label,0);identity.addWidget(panel.map_label,1)
    layout.addLayout(identity)
    clock=QHBoxLayout();clock.setContentsMargins(16,0,16,0)
    panel.elapsed=number('—','trackingClock');panel.elapsed.setAlignment(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter)
    panel.elapsed.setProperty('reserveText','99:59:59')
    panel.elapsed.setAccessibleName('Tracking duration');panel.elapsed.setFixedWidth(164)
    clock.addWidget(panel.elapsed);clock.addSpacing(12)
    controls=QHBoxLayout()
    panel.start_button=QPushButton("Start tracking");panel.start_button.setObjectName("primary")
    panel.start_button.clicked.connect(panel.start)
    panel.pause_button=QPushButton("Pause");panel.pause_button.setObjectName('primary');panel.pause_button.clicked.connect(panel.toggle_pause)
    panel.stop_button=QPushButton("Stop and save");panel.stop_button.clicked.connect(panel.stop)
    panel.save_button=panel.stop_button
    for button in (panel.start_button,panel.pause_button,panel.stop_button):
        button.setMinimumHeight(32);controls.addWidget(button,1)
    clock.addLayout(controls,1);layout.addLayout(clock)
    hero=QFrame();hero.setObjectName("expHero")
    hero_layout=QVBoxLayout(hero);hero_layout.setContentsMargins(16,12,16,12);hero_layout.setSpacing(8)
    panel.exp_heading=label('EXP','trackingHeading');hero_layout.addWidget(panel.exp_heading)
    rate_row=QHBoxLayout();rate_row.setSpacing(12)
    panel.minute_caption=label("Per minute","expEyebrow")
    panel.hour_caption=label("Per hour","expEyebrow")
    panel.gain=number('—','trackingFigure')
    panel.rate=number("—","trackingFigure");panel.hour_rate=number("—","trackingFigure")
    for caption,value in ((label('Session gain','expEyebrow'),panel.gain),(panel.minute_caption,panel.rate),(panel.hour_caption,panel.hour_rate)):
        value.setMinimumWidth(0)
        column=QVBoxLayout();column.setSpacing(4);column.addWidget(caption);column.addWidget(value);rate_row.addLayout(column,1)
    hero_layout.addLayout(rate_row)
    panel.raw_hint=label("","expMuted");panel.raw_hint.hide();hero_layout.addWidget(panel.raw_hint)
    panel.observation=label("","expMuted");hero_layout.addWidget(panel.observation)
    panel.observation.setToolTip('Per-minute and per-hour EXP rates average up to five minutes of active, readable tracking. Pauses and unreadable intervals are excluded. Standing still while tracking is running counts toward the average.')
    metrics=QHBoxLayout();metrics.setSpacing(6);panel.eta_caption=label('Level — - ETA','expMuted');metrics.addWidget(panel.eta_caption)
    panel.eta=number('—','expPosition');metrics.addWidget(panel.eta);metrics.addStretch()
    hero_layout.addLayout(metrics)
    layout.addWidget(hero)
    money=QFrame();money.setObjectName('expHero')
    money_layout=QVBoxLayout(money);money_layout.setContentsMargins(16,10,16,10);money_layout.setSpacing(7)
    panel.meso_heading=label('MESO','trackingHeading');panel.meso_heading.setProperty('currencyIcon',False);money_layout.addWidget(panel.meso_heading)
    metrics=QHBoxLayout();metrics.setSpacing(12)
    panel.meso_gain,panel.meso_rate,panel.meso_hour=[number('—','mesoFigure') for _ in range(3)]
    panel.meso_captions=[]
    for title,widget in zip(('Session gain','Per minute','Per hour'),(panel.meso_gain,panel.meso_rate,panel.meso_hour)):
        widget.setMinimumWidth(0)
        caption=label(title,'expEyebrow');panel.meso_captions.append(caption)
        column=QVBoxLayout();column.setSpacing(4);column.addWidget(caption);column.addWidget(widget);metrics.addLayout(column,1)
    money_layout.addLayout(metrics)
    panel.meso_status=label('', 'expMuted')
    panel.meso_status.setToolTip('Meso rates divide confirmed pickups by active session time. Pauses are excluded. Missing pickup messages can leave gains uncounted.')
    money_layout.addWidget(panel.meso_status)
    layout.addWidget(money)
    options_row=QHBoxLayout()
    panel.overlay_check=QCheckBox("Show EXP overlay")
    panel.overlay_check.setToolTip('Show EXP gain, pace and level-up ETA at the bottom left of the game.')
    panel.overlay_check.setChecked(True);panel.overlay_check.toggled.connect(panel.overlay_changed.emit)
    panel.meso_overlay_check=QCheckBox('Show meso overlay')
    panel.meso_overlay_check.setToolTip('Show meso pickups and rates at the bottom left of the game.')
    panel.meso_overlay_check.setChecked(True);panel.meso_overlay_check.toggled.connect(panel.meso_overlay_changed.emit)
    options_row.addWidget(panel.overlay_check);options_row.addWidget(panel.meso_overlay_check);options_row.addStretch()
    layout.addLayout(options_row)
    panel.state=label("","expMuted");panel.state.setFixedHeight(19)
    policy=panel.state.sizePolicy();policy.setRetainSizeWhenHidden(True);panel.state.setSizePolicy(policy);layout.addWidget(panel.state)
    context=QFormLayout();context.setVerticalSpacing(6)
    panel.map_input = QLineEdit()
    panel.map_input.setMaxLength(160)
    panel.map_input.setPlaceholderText("Use the detected map")
    panel.map_input.setAccessibleName("Training map or session label")
    context.addRow(label('Map label','expMuted'),panel.map_input)
    panel.notes = QLineEdit()
    panel.notes.setMaxLength(240)
    panel.notes.setPlaceholderText("Weapon, party, buffs… (optional)")
    context.addRow(label('Notes','expMuted'),panel.notes)
    layout.addLayout(context)
    panel.map_input.textEdited.connect(panel.edit_context)
    panel.notes.textEdited.connect(panel.edit_context)
    links=QHBoxLayout();panel.history_button=QPushButton('History');panel.history_button.setMinimumHeight(32)
    links.addStretch();links.addWidget(panel.history_button);layout.addLayout(links)
    panel.best=label('','expMuted');layout.addWidget(panel.best);layout.addStretch()

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
    panel.table = QTableWidget(0,6)
    history_headers(panel)
    panel.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    panel.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    panel.table.setShowGrid(False)
    panel.table.setAlternatingRowColors(True)
    panel.table.verticalHeader().hide()
    panel.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
    for column in range(1,6):panel.table.horizontalHeader().setSectionResizeMode(column,QHeaderView.ResizeMode.ResizeToContents)
    history.addWidget(panel.table,1)
    close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    close.rejected.connect(panel.history_dialog.reject)
    history.addWidget(close)
    panel.history_button.clicked.connect(panel.history_dialog.open)


def history_headers(panel):
    panel.table.setHorizontalHeaderLabels(['Map / date','Level','Time',
        'EXP gain' if panel.display_mode=='raw' else 'Progress gain','Per minute','Picked up'])
    header=panel.table.horizontalHeaderItem(5)
    header.setIcon(QIcon(str(Path(__file__).parent/'resources/meso.svg')))
    header.setToolTip('Meso pickups; older runs used wallet changes')
