"""Short, interruptible QWidget motion; idle and hidden widgets do no animation work."""
from PySide6.QtCore import QEasingCurve,QPoint,Qt,QVariantAnimation,QSize,QRect
from PySide6.QtGui import QPainter, QPalette
from PySide6.QtWidgets import QApplication, QGraphicsOpacityEffect, QLabel, QTabWidget, QWidget


def enabled(widget):
    app = QApplication.instance()
    return bool(app and not app.property("reduceMotion") and widget.isVisible()
                and not widget.window().isMinimized())


class MotionLabel(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(text,parent)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.alpha = 1.0
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(110)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self._alpha)

    def _alpha(self, value):
        self.alpha = float(value)
        self.update()

    def setText(self, value):
        if value == self.text():return
        animate = bool(self.text()) and enabled(self) and not self.property("quietUpdates")
        self.animation.stop()
        super().setText(value)
        if animate:
            self.animation.setStartValue(.55)
            self.animation.setEndValue(1.0)
            self.animation.start()
        else:self.alpha = 1.0

    def paintEvent(self, event):
        if self.alpha >= .999:
            return super().paintEvent(event)
        painter = QPainter(self)
        painter.setOpacity(self.alpha)
        painter.setFont(self.font())
        painter.setPen(self.palette().color(QPalette.ColorRole.WindowText))
        flags = int(self.alignment()) | int(Qt.TextFlag.TextWordWrap if self.wordWrap() else Qt.TextFlag.TextSingleLine)
        painter.drawText(self.contentsRect(),flags,self.text())

    def hideEvent(self, event):
        self.animation.stop()
        self.alpha = 1.0
        super().hideEvent(event)


def reveal(widget):
    if not enabled(widget):return
    previous = getattr(widget,"_reveal",None)
    if previous:previous.stop();previous.deleteLater()
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    animation = QVariantAnimation(widget)
    widget._reveal = animation
    animation.setDuration(85)
    animation.setStartValue(.80)
    animation.setEndValue(1.0)
    animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    animation.valueChanged.connect(effect.setOpacity)
    def finish():
        if widget._reveal is animation:
            widget._reveal = None
            widget.setGraphicsEffect(None)
        animation.deleteLater()
    animation.finished.connect(finish)
    animation.start()


def fade_away(widget):
    """Keep outgoing pixels visible while their source layout is cleared."""
    if not enabled(widget) or widget.size().isEmpty():return
    host=widget.parentWidget()
    snapshot=QLabel(host);snapshot.setPixmap(widget.grab());snapshot.setGeometry(widget.geometry())
    snapshot.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    effect=QGraphicsOpacityEffect(snapshot);snapshot.setGraphicsEffect(effect)
    animation=QVariantAnimation(snapshot);animation.setDuration(100)
    animation.setStartValue(1.0);animation.setEndValue(0.0);animation.valueChanged.connect(effect.setOpacity)
    animation.finished.connect(snapshot.deleteLater)
    snapshot.show();snapshot.raise_();animation.start()


def visibility(widget, shown):
    """Animate a layout section's height without leaving an invisible input target."""
    if getattr(widget,"_motion_target",not widget.isHidden()) == shown:return
    widget._motion_target = shown
    old = getattr(widget,"_section_animation",None)
    if old:old.stop();old.deleteLater()
    cap = getattr(widget,"_section_cap",widget.maximumHeight())
    widget._section_cap = cap
    if not enabled(widget.parentWidget() or widget):
        widget.setMaximumHeight(cap)
        widget.setVisible(shown)
        return
    current = widget.height() if not widget.isHidden() else 0
    target = min(cap,widget.sizeHint().height()) if shown else 0
    widget.setVisible(True)
    widget.setEnabled(shown)
    animation = QVariantAnimation(widget)
    widget._section_animation = animation
    animation.setDuration(130)
    animation.setStartValue(current)
    animation.setEndValue(target)
    animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    animation.valueChanged.connect(lambda height:widget.setMaximumHeight(round(height)))
    def finish():
        if widget._section_animation is animation:
            widget.setVisible(shown)
            widget.setMaximumHeight(cap)
            widget.setEnabled(True)
            widget._section_animation = None
        animation.deleteLater()
    animation.finished.connect(finish)
    animation.start()


class AnimatedTabs(QTabWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.previous_page=None
        self.snapshot=None
        self.previous_index=0
        self.currentChanged.connect(self.transition)

    def transition(self,index):
        page=self.currentWidget()
        previous=self.previous_page
        self.previous_page=page
        direction=1 if index>=self.previous_index else -1
        self.previous_index=index
        if self.snapshot:
            self.snapshot.hide();self.snapshot.deleteLater();self.snapshot=None
        if not page or not previous or not enabled(self):return
        snapshot=QWidget(self)
        snapshot.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        snapshot.setGeometry(QRect(page.mapTo(self,QPoint()),page.size()))
        old=QLabel(snapshot);old.setPixmap(previous.grab());old.resize(page.size())
        new=QLabel(snapshot);new.setPixmap(page.grab());new.resize(page.size())
        width=page.width();new.move(direction*width,0)
        animation=QVariantAnimation(snapshot)
        animation.setDuration(350);animation.setStartValue(0.0);animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        def move(value):
            offset=round(value*width)*direction
            old.move(-offset,0);new.move(direction*width-offset,0)
        animation.valueChanged.connect(move)
        self.snapshot=snapshot
        def finish():
            if self.snapshot is snapshot:self.snapshot=None
            snapshot.hide();snapshot.deleteLater()
        animation.finished.connect(finish)
        snapshot.show();snapshot.raise_();animation.start()


class RollingLabel(QLabel):
    """Clip and roll changed digits only; semantic text updates immediately."""
    def __init__(self,text="",parent=None):
        super().__init__(text,parent)
        self.old_text=text;self.progress=1.0
        self.animation=QVariantAnimation(self);self.animation.setDuration(160)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self.advance)
        self.setMinimumWidth(90)

    def advance(self,value):self.progress=float(value);self.update()

    def setText(self,text):
        if text==self.text():return
        self.animation.stop();self.old_text=self.text()
        super().setText(text)
        if enabled(self) and any(c.isdigit() for c in text) and any(c.isdigit() for c in self.old_text):
            self.animation.setStartValue(0.0);self.animation.setEndValue(1.0);self.animation.start()
        else:self.progress=1.0

    def paintEvent(self,event):
        painter=QPainter(self);painter.setFont(self.font());painter.setPen(self.palette().color(QPalette.ColorRole.WindowText))
        metrics=painter.fontMetrics();height=metrics.height();cell=metrics.horizontalAdvance('0')
        old=self.old_text.rjust(len(self.text()));new=self.text().rjust(len(old));old=old.rjust(len(new))
        widths=[cell if c.isdigit() else metrics.horizontalAdvance(c) for c in new]
        width=sum(widths);left=self.width()-width if self.alignment()&Qt.AlignmentFlag.AlignRight else (self.width()-width)//2 if self.alignment()&Qt.AlignmentFlag.AlignHCenter else 0
        y=(self.height()-height)//2
        painter.setClipRect(self.rect())
        for before,after,w in zip(old,new,widths):
            rect=QRect(left,y,w,height);left+=w
            if self.progress>=.999 or before==after or not(after.isdigit() or before.isdigit()):
                painter.drawText(rect,Qt.AlignmentFlag.AlignCenter,after);continue
            painter.save();painter.setClipRect(rect)
            painter.drawText(rect.translated(0,-round(height*self.progress)),Qt.AlignmentFlag.AlignCenter,before)
            painter.drawText(rect.translated(0,round(height*(1-self.progress))),Qt.AlignmentFlag.AlignCenter,after)
            painter.restore()

    def hideEvent(self,event):
        self.animation.stop();self.progress=1.0;super().hideEvent(event)
