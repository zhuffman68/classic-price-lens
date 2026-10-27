"""Clipboard-only Korean composer shared by the Translation page and hotkey popup."""
from PySide6.QtCore import Qt,QTimer,QPropertyAnimation,QEasingCurve
from PySide6.QtGui import QFontDatabase,QFont
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLineEdit,QPushButton,QFrame,QProgressBar,QDialog,QScrollArea
from .motion import MotionLabel,visibility,enabled,reveal
from .outgoing_text import clean,LIMIT

_korean_family=None


class ComposerWidget(QWidget):
    def __init__(self,composer,shortcut='F8',configure=None,parent=None):
        super().__init__(parent);self.composer=composer
        layout=QVBoxLayout(self);layout.setContentsMargins(0,12,0,0);layout.setSpacing(12)
        title=QHBoxLayout();title.addWidget(MotionLabel('Write in Korean'),1)
        self.shortcut=QPushButton('Shortcut: '+shortcut);self.shortcut.setObjectName('quiet')
        self.shortcut.setAutoDefault(False)
        if configure:self.shortcut.clicked.connect(configure)
        else:self.shortcut.hide()
        title.addWidget(self.shortcut);layout.addLayout(title)
        hint=MotionLabel('Type English. Enter translates and copies the Korean draft.');hint.setWordWrap(True)
        hint.setStyleSheet('color:#a6b1bf;font-size:11px');layout.addWidget(hint)
        self.input=QLineEdit();self.input.setMaxLength(LIMIT);self.input.setClearButtonEnabled(True)
        self.input.setPlaceholderText('WTS Work Gloves 250k ea, pmo')
        self.input.setAccessibleName('English message to translate into Korean')
        self.input.setStyleSheet('QLineEdit { padding:12px; background:#222c3b; border:1px solid #3b4b61; border-radius:7px; } QLineEdit:focus {border-color:#d9ad66;}')
        self.input.textChanged.connect(composer.set_text);self.input.returnPressed.connect(composer.request_copy);layout.addWidget(self.input)
        self.progress=QProgressBar();self.progress.setRange(0,0);self.progress.setTextVisible(False);self.progress.setFixedHeight(3);self.progress.hide();layout.addWidget(self.progress)
        self.preview=QFrame();self.preview.setObjectName('card');preview=QVBoxLayout(self.preview);preview.setContentsMargins(14,12,14,12)
        caption=MotionLabel('KOREAN PREVIEW');caption.setStyleSheet('color:#a6b1bf;font-size:10px');preview.addWidget(caption)
        self.output=MotionLabel();self.output.setWordWrap(True);self.output.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        global _korean_family
        if _korean_family is None:
            identity=QFontDatabase.addApplicationFont(str(composer.root/'price_lens/resources/fonts/Maplestory-Bold.ttf'))
            families=QFontDatabase.applicationFontFamilies(identity);_korean_family=families[0] if families else ''
        font=QFont(self.output.font());font.setPixelSize(16)
        if _korean_family:font.setFamilies(['Noto Sans',_korean_family])
        self.output.setFont(font);preview.addWidget(self.output)
        self.expansion=MotionLabel();self.expansion.setWordWrap(True);self.expansion.setStyleSheet('color:#a6b1bf;font-size:10px');preview.addWidget(self.expansion)
        self.preview.hide();layout.addWidget(self.preview)
        self.status=MotionLabel();self.status.setWordWrap(True);self.status.setStyleSheet('color:#a6b1bf;font-size:11px');layout.addWidget(self.status)
        self.copy=QPushButton('Translate && Copy');self.copy.setObjectName('primary');self.copy.setMinimumHeight(36)
        self.copy.setAutoDefault(False)
        self.copy.clicked.connect(composer.request_copy);layout.addWidget(self.copy)
        self.toast=QFrame();self.toast.setStyleSheet('QFrame {background:#203c34;border-radius:6px;}')
        row=QVBoxLayout(self.toast);row.setContentsMargins(12,8,12,8)
        message=MotionLabel('Copied to clipboard · paste with Ctrl+V in Classic World');message.setWordWrap(True);message.setStyleSheet('color:#a3dfbe;font-size:11px');row.addWidget(message)
        self.toast.hide();layout.addWidget(self.toast)
        self.toast_timer=QTimer(self);self.toast_timer.setSingleShot(True);self.toast_timer.setInterval(2400)
        self.toast_timer.timeout.connect(lambda:visibility(self.toast,False))
        manual=MotionLabel('You choose where to paste and when to send. Translation stays local.');manual.setWordWrap(True);manual.setStyleSheet('color:#8f9baa;font-size:10px');layout.addWidget(manual)
        layout.addStretch(1);composer.changed.connect(self.refresh);composer.copied.connect(self.show_copied);self.refresh()

    def refresh(self):
        c=self.composer
        if clean(self.input.text())!=c.text:
            self.input.blockSignals(True);self.input.setText(c.text);self.input.blockSignals(False)
        self.output.setText(c.result)
        self.expansion.setText('Understood: '+c.expanded if c.expanded and c.expanded.casefold()!=clean(c.text).casefold() else '')
        visibility(self.preview,bool(c.result))
        self.progress.setVisible(c.busy and not c.error)
        self.status.setText(c.error or c.note or c.status)
        self.status.setStyleSheet('color:#e4bd7b;font-size:11px' if c.error or 'Ambiguous' in c.note else 'color:#a6b1bf;font-size:11px')
        self.copy.setEnabled(bool(c.text) and c.copy_pending is None)
        self.copy.setText('Translating…' if c.copy_pending is not None else 'Translate && Copy')

    def show_copied(self,*_):
        visibility(self.toast,True);reveal(self.toast);self.toast_timer.start()

    def set_shortcut(self,value):self.shortcut.setText('Shortcut: '+value)


class ComposerDialog(QDialog):
    def __init__(self,composer,shortcut,configure=None):
        super().__init__(None,Qt.WindowType.Tool|Qt.WindowType.WindowStaysOnTopHint)
        self.composer=composer;self.setWindowTitle('Write in Korean · Lupin');self.setMinimumWidth(420);self.resize(460,360)
        layout=QVBoxLayout(self);layout.setContentsMargins(18,12,18,16)
        self.editor=ComposerWidget(composer,shortcut,configure,self)
        scroll=QScrollArea(self);scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.Shape.NoFrame);scroll.setWidget(self.editor);layout.addWidget(scroll)
        self.copy_identity=None
        self.dismiss=QTimer(self);self.dismiss.setSingleShot(True);self.dismiss.setInterval(180);self.dismiss.timeout.connect(self.finish_copy)
        composer.copied.connect(self.copied)
        self.finished.connect(lambda *_:(self.dismiss.stop(),composer.cancel_copy()))
        self.fade=QPropertyAnimation(self,b'windowOpacity',self);self.fade.setDuration(110);self.fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.focus_timer=QTimer(self);self.focus_timer.setSingleShot(True);self.focus_timer.setInterval(0)
        self.focus_timer.timeout.connect(lambda:self.editor.input.setFocus(Qt.FocusReason.ShortcutFocusReason))

    def copied(self,*_):
        if self.isVisible():self.copy_identity=self.composer.identity;self.dismiss.start()

    def finish_copy(self):
        if self.copy_identity==self.composer.identity:self.accept()

    def showEvent(self,event):
        super().showEvent(event)
        self.fade.stop()
        if enabled(self):self.fade.setStartValue(.8);self.fade.setEndValue(1.0);self.fade.start()
        else:self.setWindowOpacity(1)
        self.focus_timer.start()

    def hideEvent(self,event):
        self.fade.stop();self.dismiss.stop();self.focus_timer.stop();self.composer.cancel_copy();super().hideEvent(event)
