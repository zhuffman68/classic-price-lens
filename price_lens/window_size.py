"""Remember only the normal window size; display changes cannot strand it."""
from PySide6.QtCore import QSize, QTimer,QCoreApplication,QEvent
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid


def fills_work_area(size, screen):
    """A restored/maximized desktop size is not a useful compact-panel preference."""
    if screen is None or not size.isValid():
        return False
    available = screen.availableGeometry().size()
    return size.width() >= available.width() * .95 and size.height() >= available.height() * .90


def restore(window, settings):
    screens = QApplication.screens()
    screen = next((s for s in screens if s.name() == settings.value('window-screen', '')),
                  QApplication.primaryScreen())
    available = screen.availableGeometry().size()
    cap = QSize(max(1, available.width()-24), max(1, available.height()-32))
    window.setMinimumSize(min(460, cap.width()), min(560, cap.height()))
    saved = settings.value('window-size', None)
    window._fit_default_size = not isinstance(saved,QSize) or not saved.isValid() or fills_work_area(saved,screen)
    desired = saved if isinstance(saved, QSize) and saved.isValid() else QSize(460, 960)
    size = desired.expandedTo(window.minimumSize()).boundedTo(cap)
    if fills_work_area(size, screen):
        size = QSize(460, 960).expandedTo(window.minimumSize()).boundedTo(cap)
    window.resize(size)
    window._normal_size = size
    window._size_timer = QTimer(window)
    window._size_timer.setSingleShot(True)
    window._size_timer.setInterval(400)
    window._size_timer.timeout.connect(lambda: save(window, settings))


def fit_default(window):
    """Measure regular tracking controls at compact width before the first paint."""
    if not isValid(window) or getattr(window,'closing',False) or not getattr(window,'_fit_default_size',False):return
    window._fit_default_size=False
    panel=window.exp_panel;tabs=window.tabs;original=tabs.currentIndex()
    probes=((panel.character,'Character · Level 100'),(panel.map_label,'Training map'),
            (panel.observation,'Measuring pace · 30s of readings remaining'),
            (panel.state,'Paused · elapsed time and gains are held.'),
            (panel.raw_hint,'12,345 EXP/min · 740,700 EXP/hour'))
    previous=[(widget,widget.text(),widget.isHidden()) for widget,_ in probes]
    was_blocked=tabs.blockSignals(True)
    try:
        for widget,text in probes:widget.setText(text);widget.show()
        tabs.setCurrentIndex(window.exp_tab_index)
        window.ensurePolished();window.centralWidget().layout().activate()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.LayoutRequest)
        available=(window.screen() or QApplication.primaryScreen()).availableGeometry().size()
        cap=QSize(available.width()-24,available.height()-32)
        required=window.height()-window.exp_scroll.viewport().height()+panel.layout().sizeHint().height()
        window.resize(min(cap.width(),max(460,window.minimumSizeHint().width())),min(cap.height(),required))
        for _ in range(3):
            QCoreApplication.sendPostedEvents(None,QEvent.Type.LayoutRequest)
            extra=window.exp_scroll.verticalScrollBar().maximum()
            if not extra or window.height()>=cap.height():break
            window.resize(window.width(),min(cap.height(),window.height()+extra))
        window._normal_size=window.size()
    finally:
        for widget,text,hidden in previous:widget.setText(text);widget.setVisible(not hidden)
        tabs.setCurrentIndex(original);tabs.blockSignals(was_blocked)
        window.update_shortcut_footer();window.update_price_layout()


def remember(window):
    if not hasattr(window, '_size_timer') or window.isMaximized() or window.isMinimized() or window.isFullScreen():
        return
    if fills_work_area(window.size(), window.screen()):
        return
    window._normal_size = window.size()
    window._size_timer.start()


def save(window, settings):
    size = getattr(window, '_normal_size', None)
    if size is None or fills_work_area(size, window.screen()):return
    settings.setValue('window-size', size)
    if window.screen():settings.setValue('window-screen', window.screen().name())
