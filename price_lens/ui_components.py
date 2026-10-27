"""Small first-run and price widgets. No capture, network or game access."""
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .motion import MotionLabel

COLORS = {"green": "#86ceac", "red": "#ed9394", "amber": "#e4bd7b", "blue": "#9ebde3", "muted": "#98a3b1"}


def text_label(text="", style="", wrap=False):
    widget = MotionLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(wrap)
    if style:
        widget.setStyleSheet(style)
    return widget


def mesos(value):
    if value is None:
        return "—"
    return f"{value:,.0f}" if value == int(value) else f"{value:,.2f}"


def display_labels(screens):
    if not screens:
        return []
    centres = [screen.geometry().center() for screen in screens]
    horizontal = max(p.x() for p in centres) - min(p.x() for p in centres)
    vertical = max(p.y() for p in centres) - min(p.y() for p in centres)
    labels = []
    for index, screen in enumerate(screens):
        if len(screens) == 1:
            position = ""
        elif horizontal >= vertical:
            rank = sorted(range(len(screens)), key=lambda i: centres[i].x()).index(index)
            position = "Left" if rank == 0 else "Right" if rank == len(screens) - 1 else "Centre"
        else:
            rank = sorted(range(len(screens)), key=lambda i: centres[i].y()).index(index)
            position = "Upper" if rank == 0 else "Lower" if rank == len(screens) - 1 else "Middle"
        geometry, scale = screen.geometry(), screen.devicePixelRatio()
        dimensions = f"{round(geometry.width() * scale)} × {round(geometry.height() * scale)}"
        labels.append(f"Display {index + 1}" + (f" · {position}" if position else "") + f" · {dimensions}")
    return labels


class DisplayMap(QWidget):
    selected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.screens = []
        self.current = None
        self.boxes = []
        self.setObjectName("displayMap")
        self.setFixedHeight(78)
        self.setAccessibleName("Display arrangement; choose the display containing Classic World")

    def configure(self, screens, current):
        self.screens, self.current = screens, current
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update()

    def paintEvent(self, event):
        self.boxes = []
        if not self.screens:
            return
        desktop = self.screens[0].geometry()
        for screen in self.screens[1:]:
            desktop = desktop.united(screen.geometry())
        scale = min((self.width() - 20) / max(1, desktop.width()), 64 / max(1, desktop.height()))
        width, height = desktop.width() * scale, desktop.height() * scale
        ox, oy = (self.width() - width) / 2, (self.height() - height) / 2
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for index, screen in enumerate(self.screens):
            geometry = screen.geometry()
            rect = QRectF(ox + (geometry.x() - desktop.x()) * scale + 3,
                          oy + (geometry.y() - desktop.y()) * scale + 3,
                          geometry.width() * scale - 6, geometry.height() * scale - 6)
            self.boxes.append(rect)
            chosen = index == self.current
            painter.setPen(QPen(QColor("#d9ad66" if chosen else "#485467"), 2 if chosen else 1))
            painter.setBrush(QColor("#3a342a" if chosen else "#252d3b"))
            painter.drawRoundedRect(rect, 5, 5)
            painter.setPen(QColor("#f3d49d" if chosen else "#bec7d3"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(index + 1))

    def mousePressEvent(self, event):
        if self.isEnabled():
            for index, rect in enumerate(self.boxes):
                if rect.contains(event.position()):
                    self.selected.emit(index)
                    return


def price_card(**data):
    from .price_widgets import PriceCard
    return PriceCard(**data)
