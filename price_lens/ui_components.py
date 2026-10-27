"""Small first-run and price widgets. No capture, network or game access."""
from PySide6.QtCore import Qt

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
    return f"{value:,.0f}"


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


def price_card(**data):
    from .price_widgets import PriceCard
    return PriceCard(**data)
