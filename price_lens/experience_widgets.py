"""Presentation for automatic EXP watching; no sampling or accounting lives here."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap,QIcon
from pathlib import Path
from PySide6.QtWidgets import (QCheckBox,QComboBox,QDialog,QDialogButtonBox,QFrame,QHBoxLayout,QFormLayout,
    QHeaderView,QLineEdit,QPushButton,QTableWidget,QVBoxLayout,QWidget)
from .motion import MotionLabel,RollingLabel


def label(value="",name="",parent=None):
    widget=MotionLabel(value,parent)
    widget.setWordWrap(True);widget.setObjectName(name)
    return widget


def number(value="",name=""):
    widget=RollingLabel(value);widget.setObjectName(name);return widget


def with_unit(value,unit):
    row=QWidget();layout=QHBoxLayout(row);layout.setContentsMargins(0,0,0,0);layout.setSpacing(3)
    layout.addWidget(value,1)
    suffix=unit_label(unit);suffix.setFixedWidth(22)
    policy=suffix.sizePolicy();policy.setRetainSizeWhenHidden(True);suffix.setSizePolicy(policy)
    suffix.setAlignment(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter)
    layout.addWidget(suffix)
    return row,suffix


def unit_label(unit):
    suffix=label('' if unit=='meso' else unit,'expUnit')
    if unit=='meso':
        suffix.setPixmap(QPixmap(str(Path(__file__).parent/'resources/meso.svg')))
        suffix.setAccessibleName('meso');suffix.setToolTip('meso')
    return suffix


def build(panel,layout,enabled,window_minutes=None):
    panel.setObjectName("experiencePage")
    panel.setStyleSheet("""
        QWidget#experiencePage { background: transparent; }
        QFrame#expHero { background: #222b39; border: none; border-radius: 12px; }
        QFrame#expHero QWidget { background: transparent; border: none; }
        QFrame#expHero QLabel { border: none; background: transparent; }
        QLabel#expEyebrow { color: #a6b3c5; font-size: 10px; font-weight: 600; }
        QLabel#trackingHeading { color: #edf1f7; font-size: 15px; font-weight: 700; }
        QLabel#expUnit { color: #b2bdcd; font-size: 11px; }
        QLabel#expIdentity { font-size: 14px; font-weight: 600; color: #edf1f7; }
        QLabel#expMap, QLabel#expMuted { color: #a7b2c2; font-size: 11px; }
        QLabel#trackingFigure { color: #edc68a; font-size: 20px; font-weight: 650; }
        QLabel#expMetric { font-size: 18px; font-weight: 600; color: #e5eaf2; }
        QLabel#expPosition { font-size: 16px; font-weight: 600; color: #dce4ef; }
        QComboBox, QLineEdit { background: #1b2330; color: #e4eaf3; border: 1px solid #3b485c; border-radius: 6px; padding: 7px 9px; }
        QDialog { background: #171e29; }
        QTableWidget { background: #1c2532; alternate-background-color: #202b3a; border: 1px solid #354255; border-radius: 7px; selection-background-color: #39475c; }
        QHeaderView::section { background: #273344; color: #aebbd0; border: none; padding: 8px 6px; font-size: 10px; }
        QTableWidget::item { padding: 6px; border-bottom: 1px solid #2d394b; }
    """)
    layout.setContentsMargins(0,8,0,0);layout.setSpacing(8)
    panel.character=label('', 'expIdentity');panel.map_label=label('', 'expMap')
    layout.addWidget(panel.character);layout.addWidget(panel.map_label)
    clock=QHBoxLayout();clock.setContentsMargins(16,0,16,0)
    clock.addWidget(label('Time watching','expMuted'));clock.addStretch()
    panel.elapsed=number('—','expMetric');panel.elapsed.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
    clock.addWidget(panel.elapsed);layout.addLayout(clock)
    hero=QFrame();hero.setObjectName("expHero")
    hero_layout=QVBoxLayout(hero);hero_layout.setContentsMargins(16,12,16,12);hero_layout.setSpacing(8)
    panel.exp_heading=label('EXP','trackingHeading');hero_layout.addWidget(panel.exp_heading)
    rate_row=QHBoxLayout();rate_row.setSpacing(12)
    panel.minute_caption=label("Per minute","expEyebrow")
    panel.hour_caption=label("Per hour","expEyebrow")
    panel.gain=number('—','trackingFigure')
    panel.rate=number("—","trackingFigure");panel.hour_rate=number("—","trackingFigure")
    panel.exp_units=[]
    for caption,value in ((label('Session gain','expEyebrow'),panel.gain),(panel.minute_caption,panel.rate),(panel.hour_caption,panel.hour_rate)):
        row,unit=with_unit(value,'');panel.exp_units.append(unit)
        column=QVBoxLayout();column.setSpacing(5);column.addWidget(caption);column.addWidget(row);rate_row.addLayout(column,1)
    hero_layout.addLayout(rate_row)
    panel.raw_hint=label("","expMuted");panel.raw_hint.hide();hero_layout.addWidget(panel.raw_hint)
    panel.observation=label("","expMuted");hero_layout.addWidget(panel.observation)
    metrics=QHBoxLayout();metrics.addWidget(label('Next level','expMuted'))
    panel.eta=number('—','expPosition');metrics.addWidget(panel.eta);metrics.addStretch()
    hero_layout.addLayout(metrics)
    layout.addWidget(hero)
    money=QFrame();money.setObjectName('expHero')
    money_layout=QVBoxLayout(money);money_layout.setContentsMargins(16,10,16,10);money_layout.setSpacing(7)
    panel.meso_heading=label('MESO','trackingHeading');panel.meso_heading.setProperty('currencyIcon',False);money_layout.addWidget(panel.meso_heading)
    metrics=QHBoxLayout();metrics.setSpacing(12)
    panel.meso_gain,panel.meso_rate,panel.meso_hour=[number('—','trackingFigure') for _ in range(3)]
    panel.meso_captions=[];panel.meso_units=[]
    for title,widget in zip(('Net change','Per minute','Per hour'),(panel.meso_gain,panel.meso_rate,panel.meso_hour)):
        row,unit=with_unit(widget,'meso');panel.meso_units.append(unit)
        caption=label(title,'expEyebrow');panel.meso_captions.append(caption)
        column=QVBoxLayout();column.setSpacing(4);column.addWidget(caption);column.addWidget(row);metrics.addLayout(column,1)
    money_layout.addLayout(metrics)
    wallet=QHBoxLayout();wallet.addWidget(label('Wallet balance','expMuted'))
    panel.wallet_balance=number('—','expMuted');wallet.addWidget(panel.wallet_balance)
    panel.wallet_unit=unit_label('meso');policy=panel.wallet_unit.sizePolicy();policy.setRetainSizeWhenHidden(True);panel.wallet_unit.setSizePolicy(policy)
    wallet.addWidget(panel.wallet_unit);wallet.addStretch();money_layout.addLayout(wallet)
    panel.meso_status=label('', 'expMuted');money_layout.addWidget(panel.meso_status)
    layout.addWidget(money)
    controls=QHBoxLayout()
    panel.start_button=QPushButton("Start tracking");panel.start_button.setObjectName("primary")
    panel.start_button.clicked.connect(panel.start)
    panel.pause_button=QPushButton("Pause");panel.pause_button.clicked.connect(panel.toggle_pause)
    panel.stop_button=QPushButton("Stop and save");panel.stop_button.clicked.connect(panel.stop)
    panel.save_button=panel.stop_button
    for button in (panel.start_button,panel.pause_button,panel.stop_button):
        button.setMinimumHeight(32);controls.addWidget(button,1)
    layout.addLayout(controls)
    options_row=QHBoxLayout()
    panel.overlay_check=QCheckBox("Show tracking overlay in the game")
    panel.overlay_check.setChecked(True);panel.overlay_check.toggled.connect(panel.overlay_changed.emit)
    options_row.addWidget(panel.overlay_check);layout.addLayout(options_row)
    panel.state=label("","expMuted");layout.addWidget(panel.state)
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
        'EXP gain' if panel.display_mode=='raw' else 'Progress gain','Per minute','Net'])
    header=panel.table.horizontalHeaderItem(5)
    header.setIcon(QIcon(str(Path(__file__).parent/'resources/meso.svg')))
    header.setToolTip('Net mesos')
