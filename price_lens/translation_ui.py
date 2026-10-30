"""Translation controls and the latest local results; no capture or networking."""
from PySide6.QtCore import Signal,Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QCheckBox,QPushButton,QScrollArea,QFrame,QLabel,QDoubleSpinBox
from .motion import reveal,AnimatedTabs,MotionLabel
from .composer_ui import ComposerWidget


def grouped_history(cards):
    """Group consecutive equal results without changing the arrival ledger."""
    from .chat_text import message_key
    result=[]
    for index,card in enumerate(cards):
        key=(card.get('speaker'),message_key(card['original']),card['text'])
        if result and card.get('speaker') and result[-1]['_content_key']==key:
            result[-1]['repeat_count']+=1
            if any(word in card.get('note','') for word in ('Partial','uncertain','OCR correction')):
                result[-1]['note']=card['note']
            continue
        result.append({**card,'_content_key':key,'_widget_key':card.get('id',index),'repeat_count':1})
    return result


class TranslationResultCard(QFrame):
    def __init__(self,card,parent=None):
        super().__init__(parent);self.setObjectName('card');self.value=None
        body=QVBoxLayout(self);body.setContentsMargins(14,12,14,12)
        self.labels=[]
        for style in ('color:#b4c4d8;font-size:11px','font-size:14px;color:#edf1f7',
                      'font-size:12px;color:#aab5c5','color:#e4bd7b;font-size:10px'):
            label=MotionLabel('');label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True);label.setStyleSheet(style);body.addWidget(label);self.labels.append(label)
        self.update_card(card)

    def update_card(self,card):
        count=card.get('repeat_count',1);speaker=card.get('speaker') or 'Korean message'
        note=card.get('note','')
        warning=('Partial translation · check the original' if 'Partial' in note else
                 'Numbers uncertain · original retained' if 'uncertain' in note else
                 'Possible OCR correction · check the original' if 'OCR correction' in note else '')
        values=(f'{speaker} · ×{count}' if count>1 else speaker,card['text'],card['original'],warning)
        if values==self.value:return
        self.value=values
        for label,text in zip(self.labels,values):
            if label.text()!=text:label.setText(text)
            label.setVisible(bool(text))
        self.labels[2].setToolTip('First OCR reading: '+card['ocr_original'] if card.get('ocr_original') else '')


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
            spin.setAlignment(Qt.AlignmentFlag.AlignRight)
            spin.lineEdit().setTextMargins(0,0,0,0)
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
        layout.addWidget(clear);self.card_key=None;self.result_cards={};self.empty_label=None;self.set_cards([])
        if composer is not None:
            self.writer=ComposerWidget(composer,compose_shortcut,configure_compose,self)
            writer_scroll=QScrollArea();writer_scroll.setWidgetResizable(True);writer_scroll.setFrameShape(QFrame.Shape.NoFrame);writer_scroll.setWidget(self.writer)
            self.modes.addTab(writer_scroll,'Write Korean')

    def set_active(self,active):self.translate_button.setText('Restart scan' if active else 'Scan now')

    def set_status(self,message):
        self.status_label.setText(message)

    def set_cards(self,cards):
        cards=grouped_history(cards)
        key=tuple((c['_widget_key'],c.get('speaker'),c.get('original'),c.get('text'),c.get('note'),c['repeat_count']) for c in cards)
        if key==self.card_key:return
        self.card_key=key
        wanted={card['_widget_key'] for card in cards}
        for identity in list(self.result_cards):
            if identity not in wanted:
                widget=self.result_cards.pop(identity);self.results_layout.removeWidget(widget);widget.hide();widget.deleteLater()
        if self.empty_label is not None:
            self.results_layout.removeWidget(self.empty_label);self.empty_label.deleteLater();self.empty_label=None
        for index,card in enumerate(cards):
            identity=card['_widget_key'];frame=self.result_cards.get(identity)
            if frame is None:
                frame=TranslationResultCard(card,self.results);self.result_cards[identity]=frame
                self.results_layout.insertWidget(index,frame);frame.show();reveal(frame)
            else:
                frame.update_card(card)
                if self.results_layout.indexOf(frame)!=index:
                    self.results_layout.removeWidget(frame);self.results_layout.insertWidget(index,frame)
        if not cards:
            label=QLabel("Translated messages will appear here. Recent results stay here after their in-game cards disappear.")
            label.setWordWrap(True);label.setStyleSheet('color:#939eac;font-size:11px');self.results_layout.insertWidget(0,label);self.empty_label=label
        if not getattr(self,'results_stretch',False):
            self.results_layout.addStretch();self.results_stretch=True
