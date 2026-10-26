"""Small first-run and price widgets. No capture, network or game access."""
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .domain import age_text, compare, WORLD

COLORS = {"green": "#86ceac", "red": "#ed9394", "amber": "#e4bd7b", "blue": "#9ebde3", "muted": "#98a3b1"}


def text_label(text="", style="", wrap=False):
    widget = QLabel(text)
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


def price_card(*, item, row, quote, now, ttl, paused=False, old_capture=False,
               lookup_error=False, lookup_state="", expanded=False, details_changed=None, open_source=None,
               hovered=False, example=False):
    """Keep identity, availability and age separate; retain conservative domain rules."""
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(14, 12, 14, 12)
    layout.setSpacing(7)
    layout.addWidget(text_label(item.name if item else row.get("name") or "Item name unclear",
                                "font-size: 14px; font-weight: 650", True))
    if example:
        layout.addWidget(text_label("EXAMPLE PRICES", "font-size: 10px; color: #e4bd7b"))
    elif hovered:
        layout.addWidget(text_label("Inventory / equipment item", "font-size: 10px; color: #98a3b1"))
    price = row.get("price") or {}
    verdict = compare(item, price.get("quantity"), price.get("mesos"), quote, now, ttl)
    compatible = bool(item and quote and quote.game_id == item.game_id and quote.world == WORLD
                      and quote.condition == "clean" and quote.per_set == item.per_set)
    fresh = bool(compatible and quote.fresh(now, ttl))
    stale = paused or old_capture
    if not item:
        message, tone = "Item name needs checking", "muted"
    elif stale:
        message, tone = ("Paused · last read item" if paused else "Waiting for a fresh screen"), "muted"
    elif not compatible or quote.price is None:
        message = ("Market price lookup queued…" if lookup_state == "queued" and not quote else
                   "Price lookup unavailable" if lookup_error else "No market reports" if quote else "Checking market price…")
        tone = "muted"
    elif not fresh:
        message = {"refreshing": "Refreshing market reference…", "queued": "Market refresh queued…",
                   "retry": "Refresh unavailable · retry later"}.get(lookup_state,
                   ("Market report age unknown · reference only" if quote.observed_at is None else
                    "Older market reports · reference only") if quote.cache_valid(now, ttl) else "Older reference · refresh needed")
        tone = "muted"
    elif quote.sample_count < 5 or quote.uncertain:
        message, tone = "Few price reports · reference only", "muted"
    elif hovered:
        message, tone = "Market reference", "blue"
    elif verdict.delta is not None:
        direction = "below" if verdict.delta < 0 else "above"
        message = f"{abs(verdict.delta):.0f}% {direction} reference" if verdict.delta else "Near reference"
        if verdict.tone == "blue" and verdict.delta:
            message = "Near reference · " + message
        tone = verdict.tone
    else:
        message, tone = "Store price unclear", "muted"
    layout.addWidget(text_label(message, f"color: {COLORS[tone]}; font-size: 11px", True))
    numbers = QHBoxLayout()
    if not hovered:
        store = QVBoxLayout()
        store.addWidget(text_label("Store price", "color: #98a3b1; font-size: 10px"))
        unit = verdict.unit_price
        store.addWidget(text_label(mesos(unit) + (" mesos" if unit is not None else ""), "font-size: 17px; font-weight: 650"))
        numbers.addLayout(store)
    market = QVBoxLayout()
    market.addWidget(text_label("Market reference", "color: #98a3b1; font-size: 10px"))
    value = quote.price if compatible else None
    market.addWidget(text_label(mesos(value) + (" mesos" if value is not None else ""),
                               f"font-size: 17px; font-weight: 650; color: {'#e8d2ac' if fresh and not stale else '#98a3b1'}"))
    numbers.addLayout(market)
    layout.addLayout(numbers)
    if item:
        unit_text = "Prices are per set" if item.per_set else "Prices are per item"
        if item.cash:
            unit_text += " · resale value in mesos"
        layout.addWidget(text_label(unit_text, "color: #98a3b1; font-size: 10px"))
    if compatible:
        if not example:
            fetched = max(0, now - quote.fetched_at)
            reported = f"{age_text(max(0, now - quote.observed_at))} ago" if quote.observed_at else "unknown"
            layout.addWidget(text_label(f"Price checked {age_text(fetched)} ago · latest market report {reported}",
                                        "font-size: 10px; color: #98a3b1", True))
            if fresh and lookup_state in ("queued", "refreshing", "retry"):
                progress = {"queued": "Background refresh queued", "refreshing": "Refreshing in the background…",
                            "retry": "Last refresh unavailable · retry later"}[lookup_state]
                layout.addWidget(text_label(progress, "font-size: 10px; color: #98a3b1"))
        if value is None:
            layout.addWidget(text_label("Item name recognised. The price source has no market reference for this item.",
                                        "font-size: 11px; color: #aab5c4", True))
    elif lookup_error:
        layout.addWidget(text_label("Item name recognised. Cached prices will be used when available; another lookup will be tried later.",
                                    "font-size: 11px; color: #aab5c4", True))
    elif not item:
        layout.addWidget(text_label("Keep the full item name visible. A shared name or unclear text can prevent a match.",
                                    "font-size: 11px; color: #aab5c4", True))
    if example:
        return frame
    details = QWidget()
    details.setObjectName("cardDetails")
    details_layout = QVBoxLayout(details)
    details_layout.setContentsMargins(0, 2, 0, 0)
    details_layout.setSpacing(6)
    if price:
        quantity, total = price.get("quantity"), price.get("mesos")
        details_layout.addWidget(text_label(f"Listing: {quantity if quantity is not None else '?'} for {mesos(total)} mesos",
                                            "font-size: 11px; color: #aab5c4", True))
    if item and item.equipment:
        details_layout.addWidget(text_label("Equipment is compared as unscrolled. Individual stat rolls are not assessed.", wrap=True))
    if item and item.cash and item.nx_price:
        details_layout.addWidget(text_label(f"Cash Shop retail: {item.nx_price:,} NX" + (f" / pack of {item.nx_count}" if item.nx_count > 1 else "") + ". Market references above are in mesos.", wrap=True))
    if compatible:
        details_layout.addWidget(text_label(f"{quote.source} · {quote.period} median · {quote.sample_count:,} reports\n{quote.basis}", wrap=True))
        remaining = ttl - max(0, now - quote.fetched_at)
        details_layout.addWidget(text_label(f"Next price check in {age_text(remaining)}" if quote.cache_valid(now, ttl) else "Cached reference needs a refresh. Older reports cannot receive a comparison rating.", wrap=True))
        if verdict.net_margin is not None and fresh and not stale:
            details_layout.addWidget(text_label(f"At reference resale: {mesos(verdict.net_margin)} mesos per {'set' if item.per_set else 'item'} after the 3% shop fee.", wrap=True))
        if quote.url and open_source:
            link = QPushButton("View price source ↗")
            link.clicked.connect(lambda: open_source(quote.url))
            details_layout.addWidget(link)
    toggle = QPushButton("Hide details" if expanded else "Details")
    toggle.setObjectName("quiet")
    toggle.setCheckable(True)
    toggle.setChecked(expanded)
    def change(checked):
        details.setVisible(checked)
        toggle.setText("Hide details" if checked else "Details")
        if details_changed:
            details_changed(checked)
    toggle.toggled.connect(change)
    layout.addWidget(toggle, 0, Qt.AlignmentFlag.AlignLeft)
    details.setVisible(expanded)
    layout.addWidget(details)
    return frame
