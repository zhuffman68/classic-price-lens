"""GUI-side startup monitor, separate from the installer's Qt-free receipt reader."""
from contextlib import suppress
import time

from PySide6.QtCore import QObject, QTimer


class StartupMonitor(QObject):
    """Receipt requires a responsive GUI event loop and our helper's versioned IPC."""
    def __init__(self, receipt, window, parent=None, *, timeout=15, clock=time.monotonic):
        super().__init__(parent or window)
        self.receipt, self.window, self.clock = receipt, window, clock
        self.deadline = clock() + timeout
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.check)
        self.timer.start()

    def check(self):
        if self.receipt.sent:
            self.timer.stop()
            return
        timely=self.clock()<self.deadline
        ready = bool(timely and not self.window.closing and getattr(self.window.overlay, 'ready', False))
        if not ready and timely:
            return
        with suppress(OSError):
            self.receipt.report(ready, 'startup-timeout' if not timely and getattr(self.window.overlay, 'ready', False) else 'overlay-unavailable')
        self.timer.stop()
