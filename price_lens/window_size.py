"""Remember only the normal window size; display changes cannot strand it."""
from PySide6.QtCore import QSize, QTimer
from PySide6.QtWidgets import QApplication


def restore(window, settings):
    screens = QApplication.screens()
    screen = next((s for s in screens if s.name() == settings.value('window-screen', '')),
                  QApplication.primaryScreen())
    available = screen.availableGeometry().size()
    cap = QSize(max(1, available.width()-24), max(1, available.height()-32))
    window.setMinimumSize(min(460, cap.width()), min(560, cap.height()))
    saved = settings.value('window-size', None)
    desired = saved if isinstance(saved, QSize) and saved.isValid() else QSize(460, 960)
    size = desired.expandedTo(window.minimumSize()).boundedTo(cap)
    window.resize(size)
    window._normal_size = size
    window._size_timer = QTimer(window)
    window._size_timer.setSingleShot(True)
    window._size_timer.setInterval(400)
    window._size_timer.timeout.connect(lambda: save(window, settings))


def remember(window):
    if not hasattr(window, '_size_timer') or window.isMaximized() or window.isMinimized() or window.isFullScreen():
        return
    window._normal_size = window.size()
    window._size_timer.start()


def save(window, settings):
    size = getattr(window, '_normal_size', None)
    if size is None:return
    settings.setValue('window-size', size)
    if window.screen():settings.setValue('window-screen', window.screen().name())
