"""Remember only the normal window size; display changes cannot strand it."""
from PySide6.QtCore import QSize, QTimer
from PySide6.QtWidgets import QApplication

DEFAULT_SIZE = QSize(509, 829)


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
    desired = saved if isinstance(saved, QSize) and saved.isValid() else DEFAULT_SIZE
    size = desired.expandedTo(window.minimumSize()).boundedTo(cap)
    if fills_work_area(size, screen):
        size = DEFAULT_SIZE.expandedTo(window.minimumSize()).boundedTo(cap)
    window.resize(size)
    window._normal_size = size
    window._size_timer = QTimer(window)
    window._size_timer.setSingleShot(True)
    window._size_timer.setInterval(400)
    window._size_timer.timeout.connect(lambda: save(window, settings))


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
