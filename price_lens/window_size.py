"""Remember only the normal window size; display changes cannot strand it."""
from PySide6.QtCore import QSize, QTimer
from PySide6.QtWidgets import QApplication

DEFAULT_SIZE = QSize(520, 840)
DEFAULT_FRACTIONS = (DEFAULT_SIZE.width()/1920, DEFAULT_SIZE.height()/1080)


def relative_size(screen,fractions=DEFAULT_FRACTIONS):
    # QScreen uses logical coordinates on both platforms: the OS applies DPI
    # once, rather than scaling the application size for a second time.
    geometry=screen.geometry()
    return QSize(round(geometry.width()*fractions[0]),round(geometry.height()*fractions[1]))


def valid_fractions(value):
    return (isinstance(value,(list,tuple)) and len(value)==2
            and all(type(n) in (int,float) and .05<=n<=.94 for n in value))


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
    fractions=settings.value('window-size-fractions',None)
    if valid_fractions(fractions):desired=relative_size(screen,fractions)
    elif isinstance(saved,QSize) and saved.isValid() and saved not in (QSize(509,829),QSize(509,835)):
        desired=saved
    else:desired=relative_size(screen)
    size = desired.expandedTo(window.minimumSize()).boundedTo(cap)
    if fills_work_area(size, screen):
        size = relative_size(screen).expandedTo(window.minimumSize()).boundedTo(cap)
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
    if window.screen():
        screen=window.screen();settings.setValue('window-screen',screen.name())
        geometry=screen.geometry()
        settings.setValue('window-size-fractions',[size.width()/geometry.width(),size.height()/geometry.height()])
