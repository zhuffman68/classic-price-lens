"""Independent, input-transparent OS window. Only receives our own drawing commands."""
import json
import sys
import threading

from PySide6.QtCore import QObject, Signal, Qt, QRect, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QCursor
from PySide6.QtWidgets import QApplication, QWidget


class CommandPipe(QObject):
    command = Signal(bytes)
    closed = Signal()

    def listen(self):
        for line in sys.stdin.buffer:
            self.command.emit(line)
        self.closed.emit()


class AnnotationWindow(QWidget):
    def __init__(self):
        flags = (Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                 | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowTransparentForInput
                 | Qt.WindowType.WindowDoesNotAcceptFocus)
        if sys.platform.startswith("linux"):
            # Keep the compositor from shifting a full-screen tool window below
            # KDE's top panel. This flag applies only to our own XWayland window.
            flags |= Qt.WindowType.X11BypassWindowManagerHint
        super().__init__(None, flags)
        self.setWindowTitle("Classic Price Lens — screen labels")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.rows = []
        self.last_command = 0
        self.last_pointer = None
        self.pointer_timer = QTimer(self)
        self.pointer_timer.setInterval(100)
        self.pointer_timer.timeout.connect(self.report_pointer)
        self.pipe = CommandPipe(self)
        self.pipe.command.connect(self.read_command)
        self.pipe.closed.connect(QApplication.quit)
        self.listener = threading.Thread(target=self.pipe.listen, name="drawing-commands", daemon=True)
        self.listener.start()
        self.watchdog = QTimer(self)
        self.watchdog.setInterval(2000)
        self.watchdog.timeout.connect(self.expire)
        self.watchdog.start()

    def read_command(self, line):
        import time
        try:
            state = json.loads(line)
            if state.get("quit"):
                QApplication.quit()
                return
            self.last_command = time.monotonic()
            if state.get("hover_enabled") and not self.pointer_timer.isActive():
                self.last_pointer = None
                self.pointer_timer.start()
            elif not state.get("hover_enabled"):
                self.pointer_timer.stop()
            self.rows = state.get("rows", [])[:12]
            geometry = state.get("geometry")
            if geometry:
                self.setGeometry(*geometry)
            if self.rows:
                self.show()
                self.raise_()
            else:
                self.hide()
            self.update()
        except (ValueError, TypeError):
            self.rows = []
            self.hide()

    def expire(self):
        import time
        if time.monotonic() - self.last_command > 5:
            self.hide()

    def report_pointer(self):
        point = QCursor.pos()  # OS position only; no event hook or input injection.
        coordinates = (point.x(), point.y())
        if coordinates != self.last_pointer:
            self.last_pointer = coordinates
            try:
                print(json.dumps({"pointer": coordinates}), flush=True)
            except BrokenPipeError:
                QApplication.quit()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for row in self.rows:
            x, y = int(row["x"]), int(row["y"])
            font = QFont("Noto Sans")
            font.setPixelSize(12)
            painter.setFont(font)
            width = min(330, max(230, painter.fontMetrics().horizontalAdvance(row["text"]) + 20))
            x = min(max(2, x), self.width() - width - 2)
            box = QRect(x, y - 5, width, 36)
            painter.setPen(QPen(QColor(92, 103, 119, 160), 1))
            painter.setBrush(QColor(22, 28, 38, 247))
            painter.drawRoundedRect(box, 5, 5)
            name_font = QFont("Noto Sans")
            name_font.setPixelSize(10)
            painter.setFont(name_font)
            painter.setPen(QColor("#c4cbd6"))
            name = painter.fontMetrics().elidedText(row.get("name", "Unresolved item"), Qt.TextElideMode.ElideRight, width - 18)
            painter.drawText(QRect(x + 9, y - 3, width - 18, 14), Qt.AlignmentFlag.AlignVCenter, name)
            painter.setFont(font)
            painter.setPen(QColor(row.get("color", "#dce1e8")))
            painter.drawText(QRect(x + 9, y + 10, width - 18, 18), Qt.AlignmentFlag.AlignVCenter, row["text"])


def main():
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Classic Price Lens labels")
    window = AnnotationWindow()
    app._annotation_window = window
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
