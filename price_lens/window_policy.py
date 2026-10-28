"""Keep Lupin resizable and minimizable, without a maximized window state."""
import sys

from PySide6.QtCore import QEvent, QObject, Qt, QTimer


class NormalWindow(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.restoring = False
        self.window = window
        self.handle = None
        self.normal_size = window.size()
        self.size_timer = QTimer(self)
        self.size_timer.setSingleShot(True)
        self.size_timer.setInterval(75)
        self.size_timer.timeout.connect(self.remember_size)
        flags = window.windowFlags()
        flags |= (Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint
                  | Qt.WindowType.WindowSystemMenuHint | Qt.WindowType.WindowMinimizeButtonHint
                  | Qt.WindowType.WindowCloseButtonHint)
        window.setWindowFlags(flags & ~Qt.WindowType.WindowMaximizeButtonHint)
        window.installEventFilter(self)

    def remember_size(self):
        if not (self.window.isMaximized() or self.window.isMinimized()):
            self.normal_size = self.window.size()

    def native_state_changed(self, state):
        if state == Qt.WindowState.WindowMaximized:
            self.restore_normal()

    def restore_normal(self):
        if self.restoring:return
        self.restoring = True
        try:
            size = self.window.normalGeometry().size() if self.window.isMaximized() else self.normal_size
            if self.handle is not None:self.handle.setWindowState(Qt.WindowState.WindowNoState)
            self.window.setWindowState(self.window.windowState() & ~Qt.WindowState.WindowMaximized)
            if size.isValid():self.window.resize(size)
        finally:
            self.restoring = False

    def eventFilter(self, window, event):
        if event.type() in (QEvent.Type.Show, QEvent.Type.WinIdChange):
            handle = window.windowHandle()
            if handle is not None and handle is not self.handle:
                self.handle = handle
                handle.windowStateChanged.connect(self.native_state_changed)
            self.size_timer.start()
        elif event.type() == QEvent.Type.Resize and not self.restoring:
            self.size_timer.start()
        if event.type() == QEvent.Type.WindowStateChange and not self.restoring:
            state = window.windowState()
            if state & Qt.WindowState.WindowMaximized and not state & Qt.WindowState.WindowMinimized:
                self.restore_normal()
                return True
        return False


def is_maximize_message(message):
    """Called only by our own QWidget's nativeEvent; no global event hooks."""
    if sys.platform != "win32":
        return False
    from ctypes import wintypes
    native = wintypes.MSG.from_address(int(message))
    return native.message == 0x0112 and native.wParam & 0xFFF0 == 0xF030
