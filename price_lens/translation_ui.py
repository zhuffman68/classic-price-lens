"""Translation controls and the latest local results; no capture or networking."""
from PySide6.QtCore import Signal,Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QCheckBox,QPushButton,QScrollArea,QFrame,QLabel
from .motion import reveal


class TranslationPanel(QWidget):
    enabled_changed=Signal(bool)
    translate_requested=Signal()
    shortcut_requested=Signal()
    clear_requested=Signal()

    def __init__(self,enabled=False,parent=None):
        super().__init__(parent)
        layout=QVBoxLayout(self);layout.setContentsMargins(0,12,0,0);layout.setSpacing(12)
        self.enabled_check=QCheckBox("Enable local Korean translation")
        self.enabled_check.setChecked(enabled);self.enabled_check.toggled.connect(self.enabled_changed.emit)
        layout.addWidget(self.enabled_check)
        actions=QHBoxLayout()
        self.translate_button=QPushButton("Translate now");self.translate_button.setMinimumHeight(34)
        self.translate_button.setObjectName("primary");self.translate_button.clicked.connect(self.translate_requested.emit)
        self.shortcut_button=QPushButton("Shortcut…");self.shortcut_button.clicked.connect(self.shortcut_requested.emit)
        actions.addWidget(self.translate_button,1);actions.addWidget(self.shortcut_button);layout.addLayout(actions)
        self.hint=QLabel("Press your shortcut near a Korean speech bubble. English appears beside it with the original below.")
        self.hint.setWordWrap(True);self.hint.setStyleSheet("color:#a6b1bf; font-size:11px")
        layout.addWidget(self.hint)
        self.status_label=QLabel("Enable translation to get started.");self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.results=QWidget();self.results_layout=QVBoxLayout(self.results);self.results_layout.setContentsMargins(0,0,0,0)
        scroll.setWidget(self.results);layout.addWidget(scroll,1)
        clear=QPushButton("Clear results and popups");clear.clicked.connect(self.clear_requested.emit)
        layout.addWidget(clear);self.card_key=None;self.set_cards([])

    def set_shortcut(self,description):
        self.shortcut_button.setText("Shortcut: "+description)
        self.hint.setText(f"Press {description} near a Korean speech bubble. English appears beside it with the original below.")

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
