"""Read an OS display through Qt's Windows desktop capture, without game handles."""
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QImage


class WindowsDesktopCapture(QObject):
    image_ready = Signal(QImage)
    errorOccurred = Signal(object, str)

    def __init__(self, app, can_capture=lambda: True, parent=None):
        super().__init__(parent)
        self.app = app
        self.can_capture = can_capture
        self.screen = None
        self.active = False
        self.paused = False
        self.failure = ""
        self.failures = 0
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.grab)

    def setScreen(self, screen):
        self.screen = screen

    def setMaximumFrameRate(self, rate):
        self.timer.setInterval(round(1000 / max(1, min(10, rate))))

    def setPaused(self, paused):
        self.paused = paused
        if paused:self.timer.stop()
        elif self.active:self.timer.start()

    def isActive(self):
        return self.active

    def error(self):
        return int(bool(self.failure))

    def errorString(self):
        return self.failure

    def start(self):
        self.failure = ""
        self.failures = 0
        self.active = True
        if not self.paused:
            self.timer.start()
            QTimer.singleShot(0, self.grab)

    def stop(self):
        self.active = False
        self.timer.stop()

    def grab(self):
        if not self.active or self.paused or not self.can_capture():return
        try:
            if self.screen is None or self.screen not in self.app.screens():
                raise RuntimeError("The selected display is no longer available.")
            # Zero means the OS desktop on this QScreen. Never pass a game HWND.
            # Qt's Windows implementation uses the desktop GDI capture path.
            image = self.screen.grabWindow(0).toImage()
            if image.isNull():raise RuntimeError("The selected display did not return an image.")
            self.failures = 0
            self.image_ready.emit(image)
        except RuntimeError as error:
            self.failures += 1
            if self.failures >= 3:
                self.failure = str(error)
                self.stop()
                self.errorOccurred.emit(1, self.failure)
