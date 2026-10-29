"""Short, interruptible QWidget motion; idle and hidden widgets do no animation work."""
import re
from PySide6.QtCore import QEasingCurve,QPoint,Qt,QVariantAnimation,QSize,QRect
from PySide6.QtGui import QPainter, QPalette
from PySide6.QtWidgets import QApplication, QGraphicsOpacityEffect, QLabel, QTabWidget, QWidget,QSizePolicy,QStackedWidget,QStyle,QStyleOption
from .number_motion import NumberRoll
from . import gui_currency


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
        self.number_roll=NumberRoll(gui_currency.visual_text(text))
        self.digits=QVariantAnimation(self);self.digits.setDuration(160)
        self.digits.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.digits.valueChanged.connect(self._digits)

    def _alpha(self, value):
        self.alpha = float(value)
        self.update()

    def _digits(self,value):
        self.number_roll.progress=float(value);self.update()

    def setText(self, value):
        if value == self.text():return
        animate = enabled(self) and not self.property("quietUpdates")
        old=self.text()
        shape=lambda text:re.sub(r'\d+(?:[,.]\d+)*','#',text)
        only_numbers=bool(any(c.isdigit() for c in value) and shape(old)==shape(value)
                          and gui_currency.line_width(value,self.fontMetrics())<=self.contentsRect().width())
        if animate and not value and self.text():fade_away(self)
        self.animation.stop()
        self.digits.stop()
        self.number_roll.set_text(gui_currency.visual_text(value),animate and only_numbers)
        super().setText(value)
        if animate and only_numbers:
            self.alpha=1.0
            self.digits.setStartValue(0.0);self.digits.setEndValue(1.0);self.digits.start()
        elif animate:
            self.animation.setStartValue(.55)
            self.animation.setEndValue(1.0)
            self.animation.start()
        else:self.alpha = 1.0

    def paintEvent(self, event):
        if not enabled(self):
            self.animation.stop();self.digits.stop();self.number_roll.finish();self.alpha=1.0
        # Keep one renderer for a numeric caption at rest and in motion. Native
        # QLabel shaping and per-cell drawing differ in rounding/kerning; swapping
        # between them made the surrounding words move during every roll.
        numeric_line = (any(c.isdigit() for c in self.text()) and '\n' not in self.text()
                        and gui_currency.line_width(self.text(),self.fontMetrics())<=self.contentsRect().width())
        if numeric_line:
            painter=QPainter(self);painter.setFont(self.font())
            painter.setOpacity(self.alpha)
            painter.setPen(self.palette().color(QPalette.ColorRole.WindowText))
            self.number_roll.paint(painter,self.contentsRect(),self.alignment(),gui_currency.paint_icon);return
        if self.property('currencyIcon') is not False and gui_currency.PATTERN.search(self.text()):
            painter=QPainter(self);gui_currency.paint_document(self,painter,self.alpha);return
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
        self.digits.stop();self.number_roll.finish()
        self.alpha = 1.0
        super().hideEvent(event)

    def heightForWidth(self,width):
        if self.wordWrap() and self.property('currencyIcon') is not False and gui_currency.PATTERN.search(self.text()):
            doc=gui_currency.document(self).clone();doc.setTextWidth(width)
            return round(doc.size().height()+self.contentsMargins().top()+self.contentsMargins().bottom())
        return super().heightForWidth(width)


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


class _ContentFrame(QWidget):
    def __init__(self,before,after,parent):
        super().__init__(parent);self.before=before;self.after=after;self.progress=0.0
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self,event):
        painter=QPainter(self);option=QStyleOption();option.initFrom(self)
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_Widget,option,painter,self)
        # Fade through the panel background so old/new text never overlaps.
        painter.setOpacity(abs(2*self.progress-1))
        painter.drawPixmap(0,0,self.before if self.progress<.5 else self.after)


class ContentArea(QWidget):
    """Replace content in one layout, without animating its height."""
    def __init__(self,parent=None):
        super().__init__(parent)
        self.before=None;self.outgoing=None
        self.animation=QVariantAnimation(self);self.animation.setDuration(130)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.animation.valueChanged.connect(self.advance)
        self.animation.finished.connect(self.finish)

    def begin(self):
        pixels=self.grab() if enabled(self) and not self.size().isEmpty() else None
        self.finish();self.before=pixels

    def complete(self):
        pixels=self.before;self.before=None
        if pixels is None or not enabled(self):return
        if self.layout():self.layout().activate()
        self.outgoing=_ContentFrame(pixels,self.grab(),self)
        self.outgoing.setGeometry(self.rect())
        self.outgoing.show();self.outgoing.raise_()
        self.animation.setStartValue(0.0);self.animation.setEndValue(1.0);self.animation.start()

    def advance(self,progress):
        if not enabled(self):self.finish();return
        if self.outgoing:self.outgoing.progress=float(progress);self.outgoing.update()

    def finish(self):
        self.animation.stop();self.before=None
        if self.outgoing:
            self.outgoing.hide();self.outgoing.deleteLater();self.outgoing=None

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if self.outgoing:self.outgoing.setGeometry(self.rect())

    def hideEvent(self,event):
        self.finish();super().hideEvent(event)


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
    animation.setDuration(widget.property('sectionDuration') or 130)
    animation.setStartValue(current)
    animation.setEndValue(target)
    animation.setEasingCurve(QEasingCurve.Type.InOutCubic if widget.property('sectionDuration') else QEasingCurve.Type.OutCubic)
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


def fading_visibility(widget,shown):
    """Fade small adornments while their retained-size policy holds alignment."""
    if getattr(widget,'_fade_target',not widget.isHidden())==shown:return
    widget._fade_target=shown
    old=getattr(widget,'_presence_animation',None)
    if old:old.stop();old.deleteLater()
    effect=widget.graphicsEffect()
    start=effect.opacity() if isinstance(effect,QGraphicsOpacityEffect) else (0.0 if widget.isHidden() else 1.0)
    if not enabled(widget.parentWidget() or widget):
        widget.setGraphicsEffect(None);widget.setVisible(shown);widget._presence_animation=None;return
    if not isinstance(effect,QGraphicsOpacityEffect):
        effect=QGraphicsOpacityEffect(widget);widget.setGraphicsEffect(effect)
    effect.setOpacity(start);widget.setVisible(True)
    animation=QVariantAnimation(widget);widget._presence_animation=animation
    animation.setDuration(140);animation.setStartValue(start);animation.setEndValue(1.0 if shown else 0.0)
    animation.setEasingCurve(QEasingCurve.Type.OutCubic);animation.valueChanged.connect(effect.setOpacity)
    def finish():
        if widget._presence_animation is animation:
            widget.setVisible(shown);widget.setGraphicsEffect(None);widget._presence_animation=None
        animation.deleteLater()
    animation.finished.connect(finish);animation.start()


class AnimatedTabs(QTabWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.previous_page=None
        self.previous_index=0
        self.sliding=False
        self.scroll=0.0
        self.stack=None
        self.mouse_before={}
        self.animation=QVariantAnimation(self)
        self.animation.setDuration(260)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.animation.valueChanged.connect(self.move_pages)
        self.animation.finished.connect(self.finish_slide)
        self.currentChanged.connect(self.transition)

    def transition(self,index):
        page=self.currentWidget()
        previous=self.previous_page;old_index=self.previous_index
        self.previous_page=page
        self.previous_index=index
        if not page or not previous or not enabled(self):
            self.finish_slide();return
        stack=self.findChild(QStackedWidget,'qt_tabwidget_stackedwidget',Qt.FindChildOption.FindDirectChildrenOnly)
        if stack is None:return
        self.animation.stop()
        if not self.sliding:
            self.stack=stack;self.base=stack.contentsRect();self.slide_width=self.base.width()
            if self.slide_width<=0:return
            self.scroll=float(old_index)
            self.layout_enabled=stack.layout().isEnabled()
            stack.layout().setEnabled(False)
            self.sliding=True
        stack.setUpdatesEnabled(False)
        for i in range(self.count()):
            child=self.widget(i)
            if child not in self.mouse_before:
                self.mouse_before[child]=child.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,child is not page)
            child.resize(self.base.size());child.show()
        self.move_pages(self.scroll)
        page.raise_();stack.setUpdatesEnabled(True)
        self.animation.setStartValue(self.scroll)
        self.animation.setEndValue(float(index))
        self.animation.start()

    def move_pages(self,value):
        if not self.sliding:return
        if not enabled(self):self.finish_slide();return
        self.scroll=float(value)
        for i in range(self.count()):
            self.widget(i).move(self.base.left()+round((i-self.scroll)*self.slide_width),self.base.top())

    def finish_slide(self):
        self.animation.stop()
        if not self.sliding:return
        self.sliding=False;stack=self.stack;current=self.currentWidget()
        stack.setUpdatesEnabled(False)
        for i in range(self.count()):
            child=self.widget(i)
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,self.mouse_before.get(child,False))
            child.setGeometry(stack.contentsRect());child.setVisible(child is current)
        self.mouse_before.clear()
        stack.layout().setEnabled(self.layout_enabled);stack.layout().activate()
        stack.setUpdatesEnabled(True)

    def hideEvent(self,event):
        self.finish_slide();super().hideEvent(event)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if self.sliding:
            # Status text and page layouts can resize the viewport during a tab
            # change. Scroll in page units so the same animation/easing survives.
            self.base=self.stack.contentsRect();self.slide_width=self.base.width()
            if self.slide_width<=0:
                self.finish_slide();return
            self.stack.setUpdatesEnabled(False)
            for i in range(self.count()):self.widget(i).resize(self.base.size())
            self.move_pages(self.scroll)
            self.stack.setUpdatesEnabled(True)


class RollingLabel(QLabel):
    """Clip and roll changed digits only; semantic text updates immediately."""
    def __init__(self,text="",parent=None):
        super().__init__(text,parent)
        self.roll=NumberRoll(gui_currency.visual_text(text))
        self.animation=QVariantAnimation(self);self.animation.setDuration(160)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self.advance)
        self.setMinimumWidth(90)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)

    def sizeHint(self):
        margins=self.contentsMargins()
        reserved=self.property('reserveText')
        width=max(90,self.fontMetrics().horizontalAdvance(reserved)+4) if reserved else 90
        return QSize(width,self.fontMetrics().height()+margins.top()+margins.bottom())

    def minimumSizeHint(self):return self.sizeHint()

    def advance(self,value):self.roll.progress=float(value);self.update()

    def setText(self,text):
        if text==self.text():return
        self.animation.stop()
        super().setText(text)
        if self.roll.set_text(gui_currency.visual_text(text),enabled(self)):
            self.animation.setStartValue(0.0);self.animation.setEndValue(1.0);self.animation.start()

    def paintEvent(self,event):
        painter=QPainter(self);painter.setFont(self.font());painter.setPen(self.palette().color(QPalette.ColorRole.WindowText))
        if not enabled(self):self.roll.finish()
        self.roll.paint(painter,self.contentsRect(),self.alignment(),gui_currency.paint_icon)

    def hideEvent(self,event):
        self.animation.stop();self.roll.finish();super().hideEvent(event)
