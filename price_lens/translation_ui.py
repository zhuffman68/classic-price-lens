"""Translation controls and the latest local results; no capture or networking."""
from PySide6.QtCore import Signal,Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QCheckBox,QPushButton,QScrollArea,QFrame,QLabel,QDoubleSpinBox
from .motion import reveal,AnimatedTabs,MotionLabel
from .composer_ui import ComposerWidget


class TranslationPanel(QWidget):
    enabled_changed=Signal(bool)
    translate_requested=Signal()
    clear_requested=Signal()
    timing_changed=Signal(float,float)

    def __init__(self,enabled=False,parent=None,composer=None,compose_shortcut='Meta+F8',configure_compose=None,scan_seconds=4.0,linger_seconds=1.5):
        super().__init__(parent)
        outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0)
        self.modes=AnimatedTabs(self);outer.addWidget(self.modes)
        reader=QWidget();self.modes.addTab(reader,'Read Korean')
        layout=QVBoxLayout(reader);layout.setContentsMargins(0,12,0,0);layout.setSpacing(12)
        self.enabled_check=QCheckBox("Enable Korean translation")
        self.enabled_check.setToolTip('Scan Korean text in the shared game window. The Korean writer works separately.')
        self.enabled_check.setChecked(enabled);self.enabled_check.toggled.connect(self.enabled_changed.emit)
        enable_row=QHBoxLayout();enable_row.addWidget(self.enabled_check,1)
        self.status_label=MotionLabel('Translation disabled');self.status_label.setStyleSheet('color:#a6b1bf;font-size:11px')
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
        self.status_label.setWordWrap(True);enable_row.addWidget(self.status_label,1);layout.addLayout(enable_row)
        actions=QHBoxLayout()
        self.translate_button=QPushButton("Scan now");self.translate_button.setMinimumHeight(34)
        self.translate_button.setObjectName("primary");self.translate_button.clicked.connect(self.translate_requested.emit)
        self.translate_button.setEnabled(enabled)
        self.enabled_check.toggled.connect(self.translate_button.setEnabled)
        actions.addWidget(self.translate_button,1);layout.addLayout(actions)
        self.hint=QLabel("Scan the Classic World window for Korean text. Results appear as soon as they’re ready.")
        self.hint.setWordWrap(True);self.hint.setStyleSheet("color:#a6b1bf; font-size:11px")
        layout.addWidget(self.hint)
        timings=QVBoxLayout();timings.setSpacing(7)
        self.scan=QDoubleSpinBox();self.scan.setRange(1,10);self.scan.setSingleStep(.5);self.scan.setSuffix(' s');self.scan.setValue(scan_seconds)
        self.linger=QDoubleSpinBox();self.linger.setRange(0,5);self.linger.setSingleStep(.5);self.linger.setSuffix(' s');self.linger.setValue(linger_seconds)
        self.timing_labels=[]
        for text,spin in (('Keep checking for',self.scan),('Keep after disappearance',self.linger)):
            spin.setDecimals(1);spin.setFixedWidth(96)
            spin.setStyleSheet('QDoubleSpinBox {background:#222c3b;color:#e7edf5;border:1px solid #45536a;border-radius:6px;padding:4px 6px;}')
            row=QHBoxLayout();row.setSpacing(8)
            caption=QLabel(text);self.timing_labels.append(caption)
            row.addWidget(caption);row.addStretch();row.addWidget(spin)
            timings.addLayout(row)
        layout.addLayout(timings)
        self.scan.setToolTip('Results appear as soon as text is read. Keep checking for new or moving text during this window; press again to restart.')
        for spin in (self.scan,self.linger):spin.valueChanged.connect(lambda *_:self.timing_changed.emit(self.scan.value(),self.linger.value()))
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.results=QWidget();self.results_layout=QVBoxLayout(self.results);self.results_layout.setContentsMargins(0,0,0,0)
        scroll.setWidget(self.results);layout.addWidget(scroll,1)
        clear=QPushButton("Clear results and popups");clear.clicked.connect(self.clear_requested.emit)
        layout.addWidget(clear);self.card_key=None;self.set_cards([])
        if composer is not None:
            self.writer=ComposerWidget(composer,compose_shortcut,configure_compose,self)
            writer_scroll=QScrollArea();writer_scroll.setWidgetResizable(True);writer_scroll.setFrameShape(QFrame.Shape.NoFrame);writer_scroll.setWidget(self.writer)
            self.modes.addTab(writer_scroll,'Write Korean')

    def set_active(self,active):self.translate_button.setText('Restart scan' if active else 'Scan now')

    def set_status(self,message):
        self.status_label.setText(message)

    def set_cards(self,cards):
        key=tuple((c.get('speaker'),c.get('original'),c.get('text'),c.get('note')) for c in cards)
        if key==self.card_key:return
        self.card_key=key
        while self.results_layout.count():
            widget=self.results_layout.takeAt(0).widget()
            if widget:widget.hide();widget.deleteLater()
        for card in cards:
            frame=QFrame();frame.setObjectName("card");body=QVBoxLayout(frame);body.setContentsMargins(14,12,14,12)
            for text,style in ((card.get('speaker') or 'Korean message','color:#b4c4d8;font-size:11px'),
                               (card['text'],'font-size:14px;color:#edf1f7'),
                               (card['original'],'font-size:12px;color:#aab5c5')):
                label=QLabel(text);label.setTextFormat(Qt.TextFormat.PlainText);label.setWordWrap(True);label.setStyleSheet(style);body.addWidget(label)
            note=card.get('note','')
            if 'Partial' in note or 'uncertain' in note:
                label=QLabel('Partial translation · check the original' if 'Partial' in note else 'Numbers uncertain · original retained')
                label.setWordWrap(True);label.setStyleSheet('color:#e4bd7b;font-size:10px');body.addWidget(label)
            self.results_layout.addWidget(frame);frame.show();reveal(frame)
        if not cards:
            label=QLabel("Translated messages will appear here. Recent results stay here after their in-game cards disappear.")
            label.setWordWrap(True);label.setStyleSheet('color:#939eac;font-size:11px');self.results_layout.addWidget(label)
        self.results_layout.addStretch()
