"""Our own focusable writer surface; translation and clipboard stay in the GUI.

The annotation helper uses XWayland when needed for desktop positioning. Its
click-through canvas is never made interactive: this is a separate managed tool
window, with bounded draft/state messages and no access to a game window.
"""
from PySide6.QtCore import QObject, QRect, Qt, QTimer, Signal, QVariantAnimation, QEasingCurve,QEvent
from pathlib import Path
from PySide6.QtGui import QFont,QFontDatabase
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,QScrollArea

from .fonts import interface_font
from .outgoing_text import LIMIT, clean


def composer_state(composer):
    return {key: getattr(composer, key) for key in ('text', 'result', 'expanded', 'note', 'error', 'status')} | {
        'busy': bool(composer.busy), 'copy_pending': composer.copy_pending is not None}


class ComposerOverlayController(QObject):
    """Authoritative GUI-side bridge. Old surfaces cannot authorize a new draft."""
    visibility_changed = Signal()
    fallback_requested = Signal(str)

    def __init__(self, composer, overlay, parent=None):
        super().__init__(parent)
        self.composer, self.overlay = composer, overlay
        self.session = self.ack = 0
        self.active = self.presented = False
        self.allow_cancel=False
        self.submitted_identity=None
        self.placement = None
        self.actual_box = None
        self.shortcut = ''
        self.reduced = False
        self.activation_token=''
        composer.changed.connect(self.sync)
        composer.copied.connect(self.sync)
        overlay.writer_event.connect(self.receive)
        overlay.writer_lost.connect(self.lost)

    def command(self, operation):
        self.overlay.update_writer(dict(operation=operation, session=self.session, ack=self.ack,
            state=composer_state(self.composer), placement=self.placement,
            shortcut=self.shortcut, reduce_motion=self.reduced))

    def open(self, placement, shortcut, reduced=False,activation_token=''):
        if not placement or placement['box'][3]<200 or not self.overlay.writer_available:
            return False
        # A new opening retires any unacknowledged events from the old surface.
        self.session += 1
        self.ack = 0
        self.active = self.presented = True
        self.allow_cancel=True
        self.submitted_identity=None
        self.placement = placement
        self.actual_box = None
        self.shortcut, self.reduced = shortcut, reduced
        self.activation_token=activation_token
        self.command('open')
        self.visibility_changed.emit()
        return True

    def sync(self):
        if self.session:
            self.command('state')

    def context(self, placement, *, reduced=False):
        motion_changed=self.reduced!=reduced
        self.reduced = reduced
        if not self.active:
            if self.presented and motion_changed:self.sync()
            return
        if placement is None:
            self.close()
        elif placement != self.placement:
            self.placement = placement
            self.command('place')
        elif motion_changed:self.sync()

    def close(self):
        if not self.presented:
            return
        if self.active:
            self.composer.cancel_copy()
        self.active = False
        self.allow_cancel=False
        self.command('close')

    def lost(self):
        if self.active:self.composer.cancel_copy()
        self.active=self.presented=False
        self.allow_cancel=False
        self.actual_box=None
        self.visibility_changed.emit()

    def rectangle(self):
        if not self.presented or not self.placement:
            return None
        # Reserve the full expansion area immediately, before the first helper
        # report, so neither OCR nor notifications race the opening animation.
        return QRect(*(self.actual_box or self.placement['box']))

    def receive(self, report):
        if not isinstance(report, dict) or report.get('session') != self.session:
            return
        event = report.get('event')
        if event == 'layout':
            box = report.get('box')
            if isinstance(box, list) and len(box) == 4 and all(type(n) is int and abs(n) < 65536 for n in box):
                self.actual_box = box if box[2] > 0 and box[3] > 0 else None
            if report.get('visible') is False:
                self.active = self.presented = False
                self.allow_cancel=False
                self.actual_box = None
                self.visibility_changed.emit()
            return
        sequence = report.get('sequence')
        if (type(sequence) is not int or not self.presented or (not self.active and not (event=='cancel' and self.allow_cancel))
                or not self.ack < sequence <= self.ack + 4096):
            return
        if event not in ('edit', 'submit', 'cancel','fallback'):
            return
        text = report.get('text', '')
        if not isinstance(text, str) or len(text) > LIMIT:
            return
        self.ack = sequence
        if event == 'cancel':
            may_cancel=self.active or self.submitted_identity==self.composer.identity
            self.active = False
            self.allow_cancel=False
            if may_cancel:
                self.composer.cancel_copy();self.composer.changed.emit()
        else:
            self.composer.set_text(text)
            if event == 'submit':
                self.active = False
                self.submitted_identity=self.composer.identity
                self.composer.request_copy()
            elif event=='fallback':
                self.close()
                self.fallback_requested.emit(self.activation_token)
        self.sync()


class RemoteComposer(QObject):
    """Presentation mirror only; it cannot translate or write the clipboard."""
    changed = Signal()
    submission_started = Signal(int)
    copy_submitted = Signal(int)

    def __init__(self, send, parent=None):
        super().__init__(parent)
        self.send = send
        self.session = self.sequence = 0
        self.text = self.result = self.expanded = self.note = self.error = ''
        self.status = ''
        self.busy = self.copy_pending = False
        self.submitted=False

    def apply(self, command):
        session = command.get('session')
        if type(session) is not int or session < self.session:
            return False
        if session != self.session:
            if command.get('operation') != 'open':
                return False
            self.session, self.sequence = session, 0
        state = command.get('state')
        if not isinstance(state, dict) or command.get('ack', -1) < self.sequence:
            return False
        if command.get('operation')=='open':self.submitted=False
        for name in ('text', 'result', 'expanded', 'note', 'error', 'status'):
            value = state.get(name, '')
            setattr(self, name, value[:4096] if isinstance(value, str) else '')
        self.busy = bool(state.get('busy'))
        self.copy_pending = bool(state.get('copy_pending'))
        self.changed.emit()
        return True

    def event(self, action):
        self.sequence += 1
        self.send(dict(event=action, session=self.session, sequence=self.sequence, text=self.text))

    def set_text(self, value):
        value = clean(value)[:LIMIT]
        if value == self.text:
            return
        self.text = value
        self.result = self.expanded = self.note = self.error = ''
        self.copy_pending = False
        self.status = 'Preparing a Korean preview…' if value else ''
        self.event('edit')
        self.changed.emit()

    def request_copy(self):
        if not self.text or self.copy_pending or self.submitted:
            return
        self.copy_pending = self.submitted = True
        # Freeze before a fast reply; publish Submit before a reduced-motion
        # hide can report the surface closed and retire this authorization.
        self.submission_started.emit(self.session)
        self.event('submit')
        self.copy_submitted.emit(self.session)

    def cancel_copy(self):
        self.copy_pending = False
        self.event('cancel')


class WriterOverlay(QDialog):
    """Small independent editor, bottom anchored and growing away from the HUD."""
    def __init__(self, composer, report, parent=None):
        flags = Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        super().__init__(parent, flags)
        self.setWindowTitle('Write in Korean · Lupin')
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.composer, self.report = composer, report
        self.placement = None
        self.submitting = self.closing = False
        self.submission_frozen=False
        self.reduced = False
        self.target = QRect()
        self.level = 1.0
        self.setFont(interface_font(11))
        self.setStyleSheet('''
            QFrame#writerPanel { background:rgba(22,28,38,247); border:1px solid #5c6777; border-radius:9px; }
            QLabel { color:#d8dee7; background:transparent; border:0; }
            QLineEdit { color:#edf1f7; background:#222c3b; border:1px solid #4a596d; border-radius:5px; padding:6px 7px; }
            QLineEdit:focus { border-color:#9ebde3; }
            QPushButton { color:#e6edf7; background:#344c69; border:1px solid #527298; border-radius:5px; padding:4px 9px; }
            QPushButton:hover { background:#405f83; }
            QPushButton:disabled { color:#8591a1; background:#283241; border-color:#3b4655; }
            QPushButton#writerClose { background:transparent; border:0; color:#b5c1d1; padding:0; font-size:17px; }
        ''')
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        self.panel = QFrame(); self.panel.setObjectName('writerPanel'); outer.addWidget(self.panel)
        layout = QVBoxLayout(self.panel); layout.setContentsMargins(10, 8, 10, 9); layout.setSpacing(6)
        header = QHBoxLayout(); header.setSpacing(6)
        self.title = QLabel('Write in Korean'); self.title.setFont(interface_font(11, QFont.Weight.DemiBold))
        header.addWidget(self.title, 1)
        self.dismiss = QPushButton('×'); self.dismiss.setObjectName('writerClose'); self.dismiss.setFixedSize(22, 21)
        self.dismiss.setAccessibleName('Cancel Korean message'); self.dismiss.clicked.connect(self.reject)
        header.addWidget(self.dismiss); layout.addLayout(header)
        self.input = QLineEdit(); self.input.setMaxLength(LIMIT)
        self.input.setPlaceholderText('English · Enter to translate & copy'); self.input.setAccessibleName('English message to translate into Korean')
        self.input.setClearButtonEnabled(True)
        self.input.textChanged.connect(composer.set_text); self.input.returnPressed.connect(composer.request_copy)
        layout.addWidget(self.input)
        self.focus_help=QFrame();help_layout=QHBoxLayout(self.focus_help);help_layout.setContentsMargins(0,0,0,0);help_layout.setSpacing(5)
        hint=QLabel('Click the field to type');hint.setStyleSheet('color:#b5c9e4;font-size:10px')
        help_layout.addWidget(hint,1)
        fallback=QPushButton('Open in Lupin');fallback.setAutoDefault(False)
        fallback.clicked.connect(lambda:composer.event('fallback'));help_layout.addWidget(fallback)
        self.focus_help.hide();layout.addWidget(self.focus_help)
        self.body=QFrame();body_layout=QVBoxLayout(self.body);body_layout.setContentsMargins(0,0,0,0);body_layout.setSpacing(5)
        self.body_scroll=QScrollArea();self.body_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.body_scroll.setWidgetResizable(True);self.body_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body_scroll.setStyleSheet('QScrollArea,QScrollArea>QWidget>QWidget {background:transparent;border:0;}')
        self.body_scroll.setWidget(self.body);layout.addWidget(self.body_scroll)
        self.preview = QLabel(); self.preview.setWordWrap(True);self.preview.setMinimumWidth(0)
        self.preview.setTextFormat(Qt.TextFormat.PlainText)
        self.preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        font=interface_font(13)
        identity=QFontDatabase.addApplicationFont(str(Path(__file__).parent/'resources/fonts/Maplestory-Bold.ttf'))
        families=QFontDatabase.applicationFontFamilies(identity)
        if families:font.setFamilies([font.family(),families[0]])
        self.preview.setFont(font);body_layout.addWidget(self.preview)
        self.detail = QLabel(); self.detail.setWordWrap(True); self.detail.setTextFormat(Qt.TextFormat.PlainText)
        self.detail.setStyleSheet('color:#aab8ca;font-size:10px');body_layout.addWidget(self.detail)
        actions = QHBoxLayout(); actions.setSpacing(6)
        self.shortcut = QLabel(); self.shortcut.setStyleSheet('color:#99a9bf;font-size:10px'); actions.addWidget(self.shortcut, 1)
        self.copy = QPushButton('Translate && Copy'); self.copy.setAutoDefault(False)
        self.copy.clicked.connect(composer.request_copy); actions.addWidget(self.copy); layout.addLayout(actions)
        self.motion = QVariantAnimation(self); self.motion.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.motion.valueChanged.connect(self.animate); self.motion.finished.connect(self.motion_finished)
        self.size_motion = QVariantAnimation(self); self.size_motion.setDuration(140)
        self.size_motion.setEasingCurve(QEasingCurve.Type.OutCubic); self.size_motion.valueChanged.connect(self.resize_height)
        self.focus_timer=QTimer(self);self.focus_timer.setSingleShot(True)
        self.focus_timer.timeout.connect(lambda:self.input.setFocus(Qt.FocusReason.ShortcutFocusReason) if self.isVisible() else None)
        self.activation_timer=QTimer(self);self.activation_timer.setSingleShot(True);self.activation_timer.setInterval(220)
        self.activation_timer.timeout.connect(self.check_activation)
        composer.changed.connect(self.refresh)
        composer.submission_started.connect(self.freeze_submission)
        composer.copy_submitted.connect(lambda *_: self.finish(True))
        self.refresh()

    def refresh(self):
        if self.closing or self.submission_frozen:return
        c = self.composer
        if clean(self.input.text()) != c.text:
            self.input.blockSignals(True); self.input.setText(c.text); self.input.blockSignals(False)
        self.preview.setText(c.result); self.preview.setVisible(bool(c.result))
        detail = c.error or ' · '.join(filter(None, (
            ('Understood: ' + c.expanded) if c.expanded and c.expanded.casefold() != clean(c.text).casefold() else '',
            c.note or (c.status if c.text and not c.result else ''))))
        self.detail.setText(detail); self.detail.setVisible(bool(detail))
        self.body_scroll.setVisible(bool(detail or c.result))
        self.detail.setStyleSheet('color:#e4bd7b;font-size:10px' if c.error else 'color:#aab8ca;font-size:10px')
        self.copy.setEnabled(bool(c.text) and not c.copy_pending)
        self.copy.setText('Translating…' if c.copy_pending else 'Translate && Copy')
        self.fit()

    def fit(self):
        if not self.placement or self.closing or self.submission_frozen:
            return
        x, y, width, maximum = self.placement['box']
        self.ensurePolished()
        self.setFixedWidth(width)
        body_width=max(100,width-26)
        for label in (self.preview,self.detail):label.setMaximumWidth(body_width)
        body_height=sum(label.heightForWidth(body_width) for label in (self.preview,self.detail) if not label.isHidden())
        if not self.preview.isHidden() and not self.detail.isHidden():body_height+=5
        body_budget=maximum-(154 if not self.focus_help.isHidden() else 119)
        self.body_scroll.setFixedHeight(min(max(28,body_height+2),max(28,body_budget)))
        self.panel.layout().activate()
        hint=self.panel.layout().totalHeightForWidth(width)
        height = min(maximum, max(102,hint,self.panel.sizeHint().height(),self.panel.layout().minimumSize().height()))
        bottom = y + maximum
        self.target = QRect(x, bottom - height, width, height)
        self.size_motion.stop()
        if self.isVisible() and not self.closing and not self.reduced and abs(self.height() - height) > 1:
            self.size_motion.blockSignals(True)
            self.size_motion.setStartValue(self.height());self.size_motion.setEndValue(height);self.size_motion.setCurrentTime(0)
            self.size_motion.blockSignals(False);self.size_motion.start()
        else:
            self.resize_height(height)

    def resize_height(self, value):
        height = round(float(value))
        self.resize(self.target.width(), height)
        # Qt may enforce a newly polished layout minimum on the first show.
        # Anchor the actual native height, never the requested pre-polish size.
        self.move(self.target.x(), self.target.bottom() + 1 - self.height() + round((1 - self.level) * 6))
        self.report_box()

    def open_at(self, placement, shortcut, reduced=False):
        self.placement = placement; self.reduced = reduced
        self.shortcut.setText(shortcut)
        self.closing = self.submitting = False
        self.submission_frozen=False
        self.motion.stop(); self.size_motion.stop(); self.panel.setEnabled(True)
        self.panel.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,False);self.input.setReadOnly(False)
        self.level=1.0 if self.reduced else 0.0
        self.setWindowOpacity(self.level)
        self.refresh(); self.show(); self.raise_(); self.activateWindow()
        handle = self.windowHandle()
        if handle is not None:
            handle.requestActivate()
        self.input.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.focus_timer.start(0)
        self.activation_timer.start()
        if self.reduced:
            self.animate(1.0)
        else:
            self.start_fade(1.0,140,QEasingCurve.Type.OutCubic)

    def start_fade(self,target,duration,easing):
        start=self.level
        # Reusing a completed QVariantAnimation otherwise emits intermediate
        # values while duration/easing/range are being reset, causing a flash.
        self.motion.blockSignals(True);self.motion.stop()
        self.motion.setDuration(duration);self.motion.setEasingCurve(easing)
        self.motion.setStartValue(start);self.motion.setEndValue(target);self.motion.setCurrentTime(0)
        self.motion.blockSignals(False);self.animate(start);self.motion.start()

    def animate(self, value):
        self.level = float(value)
        self.setWindowOpacity(self.level)
        self.move(self.target.x(), self.target.bottom() + 1 - self.height() + round((1 - self.level) * 6))
        self.report_box()

    def freeze_submission(self,*_):
        if not self.isVisible() or self.closing:return
        self.submission_frozen=True;self.motion.stop();self.size_motion.stop()
        self.target=QRect(self.x(),self.y()-round((1-self.level)*6),self.width(),self.height())
        self.panel.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True);self.input.setReadOnly(True)

    def finish(self, submitted=False):
        if not self.isVisible():
            return
        if self.closing:
            if not submitted and self.submitting:
                self.submitting=False;self.composer.cancel_copy()
            return
        self.focus_timer.stop()
        self.activation_timer.stop()
        if not submitted:
            self.composer.cancel_copy()
        self.submitting, self.closing = submitted, True
        self.motion.stop(); self.size_motion.stop()
        # Preserve the current polished geometry and enabled colours. Late
        # preview/state updates must not resize or gray the fading surface.
        self.target=QRect(self.x(),self.y()-round((1-self.level)*6),self.width(),self.height())
        self.panel.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True);self.input.setReadOnly(True)
        if self.reduced:
            self.animate(0.0); self.motion_finished()
        else:
            self.start_fade(0.0,180,QEasingCurve.Type.InOutCubic)

    def reject(self):
        self.finish(False)

    def motion_finished(self):
        if self.closing:
            self.hide(); self.report_box(); self.closing = False

    def closeEvent(self, event):
        event.ignore(); self.reject()

    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.ActivationChange,QEvent.Type.WindowStateChange) and hasattr(self,'activation_timer'):
            self.activation_timer.start()

    def check_activation(self):
        if not self.isVisible() or self.closing:return
        active=self.isActiveWindow()
        changed=self.focus_help.isHidden()==(not active)
        self.focus_help.setVisible(not active)
        if changed:self.fit()
        self.report(dict(event='focus',session=self.composer.session,active=active))

    def set_reduced(self,value):
        self.reduced=bool(value)
        if not self.reduced:return
        self.motion.stop();self.size_motion.stop()
        if self.closing:
            self.animate(0.0);self.motion_finished()
        elif self.isVisible():
            self.animate(1.0);self.resize_height(self.target.height())

    def report_box(self):
        if not self.isVisible() and not self.closing:return
        rect = self.geometry()
        if self.size_motion.state() == QVariantAnimation.State.Running:
            rect = rect.united(self.target)
        # Include the entire short entrance/exit path in OCR exclusions.
        if self.isVisible(): rect = rect.united(self.target).adjusted(0, 0, 0, 6)
        self.report(dict(event='layout', session=self.composer.session,
            visible=self.isVisible(), box=list(rect.getRect()) if self.isVisible() else [0, 0, 0, 0]))


class WriterHost(QObject):
    """Helper-side owner, sharing the annotation process but not its canvas."""
    def __init__(self, send, parent=None):
        super().__init__(parent)
        self.send = send
        self.composer = RemoteComposer(send, self)
        self.window = None

    def apply(self, command):
        if not isinstance(command, dict):
            return
        operation = command.get('operation')
        if operation not in ('open', 'state', 'place', 'close'):
            return
        if operation=='close' and command.get('session')==self.composer.session:
            if self.window is not None:self.window.finish(False)
            return
        same_session=command.get('session')==self.composer.session
        if not self.composer.apply(command) and not (same_session and operation=='place'):
            return
        if self.window is not None:
            self.window.shortcut.setText(str(command.get('shortcut',''))[:100])
            if operation!='open':self.window.set_reduced(command.get('reduce_motion'))
        if operation not in ('open', 'place','state'):
            return
        placement = command.get('placement')
        box = placement.get('box') if isinstance(placement, dict) else None
        if not isinstance(box, list) or len(box) != 4 or not all(type(n) is int and abs(n) < 65536 for n in box):
            return
        if not 160 <= box[2] <= 600 or not 200 <= box[3] <= 600:
            return
        if self.window is None:
            self.window = WriterOverlay(self.composer, self.send)
        if operation == 'open':
            self.window.open_at(placement, str(command.get('shortcut', ''))[:100], bool(command.get('reduce_motion')))
        else:
            self.window.placement = placement
            self.window.fit()

