import shutil
import sys
import time

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, QSettings
from PySide6.QtGui import QColor, QImage, QKeySequence, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFrame, QHBoxLayout, QKeySequenceEdit, QLabel, QMainWindow, QMessageBox, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from .capture import PixelReader, pointer_in_shop
from .domain import DEFAULT_TTL, age_text, compare
from .service import PriceService
from .overlay import Overlay
from .hotkeys import HotkeyManager, DEFAULT_HOTKEY, parse_shortcut

COLORS = {"green": "#86ceac", "red": "#ed9394", "amber": "#e4bd7b", "blue": "#9ebde3", "muted": "#98a3b1"}


def mesos(value):
    if value is None:
        return "—"
    return f"{value:,.0f}" if value == int(value) else f"{value:,.2f}"


def label(text="", style="", wrap=False):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(wrap)
    if style:
        widget.setStyleSheet(style)
    return widget


class CropCanvas(QLabel):
    def __init__(self, image):
        super().__init__()
        self.original = image
        self.preview = QPixmap.fromImage(image).scaled(1000, 650, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.setFixedSize(self.preview.size())
        self.begin = None
        self.end = None

    def mousePressEvent(self, event):
        self.begin = event.position().toPoint()
        self.end = self.begin
        self.update()

    def mouseMoveEvent(self, event):
        if self.begin is not None:
            self.end = event.position().toPoint()
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self.preview)
        if self.begin is not None and self.end is not None:
            painter.setPen(QPen(QColor("#f2c982"), 2))
            painter.setBrush(QColor(242, 201, 130, 35))
            painter.drawRect(QRect(self.begin, self.end).normalized())

    def selection(self):
        if self.begin is None or self.end is None:
            return None
        rect = QRect(self.begin, self.end).normalized().intersected(self.rect())
        if rect.width() < 25 or rect.height() < 25:
            return None
        ratio_x, ratio_y = self.original.width() / self.width(), self.original.height() / self.height()
        return QRect(int(rect.x() * ratio_x), int(rect.y() * ratio_y), int(rect.width() * ratio_x), int(rect.height() * ratio_y))


class LensWindow(QMainWindow):
    def __init__(self, root, cache_path, snapshot=None, auto_capture=False, kde_capture=False):
        super().__init__()
        self.setWindowTitle("Classic Price Lens")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.resize(460, 740)
        self.setMinimumSize(410, 400)
        self.catalog = None
        self.rows = []
        self.quotes = {}
        self.errors = {}
        self.mode = "idle"
        self.snapshot_path = snapshot
        self.last_screen = 0
        self.ocr_ms = None
        self.ttl = DEFAULT_TTL
        self.overlay = Overlay(root, self)
        self.labels_enabled = True
        self.screens = sorted(QApplication.screens(), key=lambda screen: screen.geometry().x())
        self.screen_index = None
        self.capture_starting = False
        self.auto_capture_pending = auto_capture
        self.capture_kind = "portal"
        self.keep_capture = False
        self.settings = QSettings("LocalTools", "Classic Price Lens")
        self.hotkey_sequence = self.settings.value("hotkey-sequence", DEFAULT_HOTKEY)
        self.hotkey_description = self.settings.value("hotkey-description", "")
        self.hotkey_status = ""
        self.hotkey_dialog_open = False
        self.hotkeys = HotkeyManager(self)
        # A Wayland portal may show a consent dialog. Let users request that once
        # through Hotkey… instead of opening two OS dialogs during first capture.
        self.hotkey_enabled = self.settings.value("hotkey-enabled", not self.hotkeys.portal, type=bool)
        self.hotkeys.activated.connect(self.on_hotkey)
        self.hotkeys.changed.connect(self.on_hotkey_changed)
        self.hotkeys.status.connect(self.on_hotkey_status)
        self.hover_enabled = self.settings.value("tooltip-prices", True, type=bool)
        self.tooltip_result = None
        self.service = PriceService(cache_path, self)
        self.reader = PixelReader(root, self)
        self.reader.tooltip_enabled = self.hover_enabled
        self.overlay.pointer.connect(self.on_pointer)
        self.reader.reading.connect(self.on_reading)
        self.reader.status.connect(self.show_status)
        self.reader.image_ready.connect(self.on_image)
        self.service.catalog_ready.connect(self.on_catalog)
        self.service.quote_ready.connect(self.on_quote)
        self.service.error.connect(self.on_error)
        self.service.identity_ready.connect(self.on_identity)

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(18, 18, 18, 12)
        layout.setSpacing(12)
        heading = QHBoxLayout()
        mark = QLabel()
        mark.setPixmap(QPixmap(str(root / "price_lens/resources/icon.png")).scaled(24, 24, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        heading.addWidget(mark)
        heading.addWidget(label("Classic Price Lens", "font-size: 21px; font-weight: 650; color: #f1e6d5"))
        heading.addStretch()
        pin = QCheckBox("Pin")
        pin.setChecked(True)
        pin.toggled.connect(self.pin)
        heading.addWidget(pin)
        layout.addLayout(heading)
        layout.addWidget(label("CLASSIC WORLD  ·  SCREEN PIXELS ONLY", "color: #c7a978; font-size: 10px; letter-spacing: 1px"))

        controls = QHBoxLayout()
        self.share = QPushButton("Start")
        self.share.setEnabled(False)
        self.share.clicked.connect(self.toggle_capture)
        controls.addWidget(self.share)
        self.hotkey_button = QPushButton("Hotkey…")
        self.hotkey_button.clicked.connect(self.configure_hotkey)
        controls.addWidget(self.hotkey_button)
        self.crop_button = QPushButton("Crop…")
        self.crop_button.setEnabled(False)
        self.crop_button.clicked.connect(self.crop)
        controls.addWidget(self.crop_button)
        layout.addLayout(controls)
        display_controls = QHBoxLayout()
        self.labels_check = QCheckBox("Prices beside items")
        self.labels_check.setChecked(True)
        self.labels_check.toggled.connect(lambda enabled: (setattr(self, "labels_enabled", enabled), self.render()))
        display_controls.addWidget(self.labels_check)
        self.monitor = QComboBox()
        self.monitor.addItem("Select monitor…", None)
        selected = self.settings.value("monitor-name", "")
        for index, screen in enumerate(self.screens):
            self.monitor.addItem(screen.name(), index)
            if selected and selected == screen.name():
                self.screen_index = index
        self.monitor.setCurrentIndex(self.screen_index + 1 if self.screen_index is not None else 0)
        self.monitor.currentIndexChanged.connect(self.set_screen)
        display_controls.addWidget(self.monitor)
        if shutil.which("spectacle"):
            self.kde_button = QPushButton("KDE capture")
            self.kde_button.clicked.connect(self.start_kde)
            display_controls.addWidget(self.kde_button)
        layout.addLayout(display_controls)
        self.hover_check = QCheckBox("Inventory / equipment tooltip prices")
        self.hover_check.setChecked(self.hover_enabled)
        self.hover_check.toggled.connect(self.set_hover)
        layout.addWidget(self.hover_check)
        second = QHBoxLayout()
        screenshot = QPushButton("Open screenshot…")
        screenshot.clicked.connect(self.open_screenshot)
        second.addWidget(screenshot)
        second.addStretch()
        second.addWidget(label("Cache"))
        ttl = QComboBox()
        for minutes in (5, 15, 30, 60):
            ttl.addItem(f"{minutes} min", minutes * 60)
        ttl.setCurrentIndex(1)
        ttl.currentIndexChanged.connect(lambda index: self.set_ttl(ttl.itemData(index)))
        second.addWidget(ttl)
        layout.addLayout(second)
        self.capture_info = label("Select a monitor to enable reading, or open a screenshot", "color: #a6b1bf; font-size: 11px", True)
        layout.addWidget(self.capture_info)
        self.summary = label("Loading Classic World item names…", "font-size: 12px; color: #dde1e7", True)
        layout.addWidget(self.summary)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.cards = QWidget()
        self.cards_layout = QVBoxLayout(self.cards)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(10)
        self.scroll.setWidget(self.cards)
        layout.addWidget(self.scroll, 1)
        self.notice = label("Assumes unscrolled equipment. References include asking and reported sold prices. Resale estimates deduct the 3% shop fee.", "color: #939eac; font-size: 10px", True)
        layout.addWidget(self.notice)
        footer = QHBoxLayout()
        footer.addStretch()
        help_button = QPushButton("About")
        help_button.clicked.connect(self.about)
        footer.addWidget(help_button)
        layout.addLayout(footer)
        self.status_label = label("Ready", "color: #939eac; font-size: 10px", True)
        layout.addWidget(self.status_label)
        self.setCentralWidget(body)
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #171c25; color: #dce1e8; font-family: 'Noto Sans', sans-serif; font-size: 12px; }
            QPushButton, QComboBox, QKeySequenceEdit { background: #252d3b; border: 1px solid #354052; border-radius: 6px; padding: 7px 9px; }
            QPushButton:hover { background: #323c4c; border-color: #927b58; }
            QPushButton:pressed { background: #404655; }
            QPushButton:disabled { background: #202630; border-color: #2c333e; color: #626c7a; }
            QCheckBox { color: #aab4c2; }
            QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }
            QFrame#card { background: #202734; border: 1px solid #303b4b; border-radius: 9px; }
            QFrame#card QLabel { background: transparent; border: none; }
            QScrollBar:vertical { background: #171c25; width: 6px; }
            QScrollBar::handle:vertical { background: #455064; border-radius: 3px; min-height: 20px; }
        """)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self.service.start()
        if snapshot:
            QTimer.singleShot(300, lambda: self.load_screenshot(snapshot))
        elif kde_capture:
            QTimer.singleShot(500, self.start_kde)
        elif auto_capture and self.screen_index is not None:
            QTimer.singleShot(500, self.start_capture)
        self.update_capture_controls()
        QApplication.instance().screenAdded.connect(self.refresh_monitors)
        QApplication.instance().screenRemoved.connect(self.refresh_monitors)
        if QApplication.platformName() != "offscreen":
            QTimer.singleShot(700, self.initialize_hotkey)

    def initialize_hotkey(self):
        if self.hotkey_enabled:
            self.hotkeys.start(self.hotkey_sequence)

    def on_hotkey(self):
        if not self.hotkey_dialog_open:
            self.toggle_capture()

    def on_hotkey_changed(self, description):
        self.hotkey_description = description
        self.hotkey_status = ""
        self.settings.setValue("hotkey-description", description)
        self.hotkey_button.setToolTip("Pause / resume: " + description)

    def on_hotkey_status(self, message):
        self.hotkey_status = message
        self.hotkey_button.setToolTip(message)
        self.status_label.setText(message)

    def configure_hotkey(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Keyboard shortcut")
        dialog.setMinimumWidth(360)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label("Toggle reading and price labels while any window is focused.", wrap=True))
        enabled = QCheckBox("Enable global hotkey")
        enabled.setChecked(self.hotkey_enabled)
        layout.addWidget(enabled)
        details = label(self.hotkey_status or self.hotkey_description or "Default: " + self.hotkey_sequence, wrap=True)
        layout.addWidget(details)
        self.hotkey_dialog_open = True
        if not self.hotkeys.portal:
            # Let the key editor receive a chord already registered by this app.
            self.hotkeys.close()
        def set_enabled(checked):
            self.hotkey_enabled = checked
            self.settings.setValue("hotkey-enabled", checked)
            if not checked:
                self.hotkeys.close()
                details.setText("Hotkey disabled")
            elif self.hotkeys.portal:
                self.initialize_hotkey()
        enabled.toggled.connect(set_enabled)
        if self.hotkeys.portal:
            choose = QPushButton("Choose shortcut in desktop settings…")
            def choose_shortcut():
                enabled.setChecked(True)
                set_enabled(True)
                self.hotkeys.configure()
            choose.clicked.connect(choose_shortcut)
            layout.addWidget(choose)
            layout.addWidget(label("The desktop confirms and saves the key combination. On older desktops, assign classic-price-lens --toggle in system keyboard shortcuts.", wrap=True))
        else:
            editor = QKeySequenceEdit(QKeySequence(self.hotkey_sequence))
            editor.setMaximumSequenceLength(1)
            layout.addWidget(editor)
            apply = QPushButton("Set hotkey")
            def apply_shortcut():
                try:
                    spec = parse_shortcut(editor.keySequence().toString(QKeySequence.SequenceFormat.PortableText))
                except ValueError as error:
                    details.setText(str(error))
                    return
                enabled.setChecked(True)
                set_enabled(True)
                if self.hotkeys.start(spec.text):
                    self.hotkey_sequence = spec.text
                    self.settings.setValue("hotkey-sequence", spec.text)
                    details.setText("Shortcut saved: " + spec.text)
                else:
                    details.setText(self.hotkey_status)
            apply.clicked.connect(apply_shortcut)
            layout.addWidget(apply)
            layout.addWidget(label("Press a key combination, then Set hotkey. Function keys can also be used alone.", wrap=True))
        self.hotkeys.changed.connect(details.setText)
        self.hotkeys.status.connect(details.setText)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        try:
            dialog.exec()
        finally:
            self.hotkeys.changed.disconnect(details.setText)
            self.hotkeys.status.disconnect(details.setText)
            self.hotkey_dialog_open = False
            if self.hotkey_enabled and not self.hotkeys.portal:
                self.initialize_hotkey()
            dialog.deleteLater()

    def pin(self, checked):
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, checked)
        self.show()

    def show_status(self, message):
        self.status_label.setText(message)
        if message.startswith(("Screen sharing stopped", "OS capture:")) and self.mode == "live":
            self.mode = "paused"
            self.capture_starting = False
            self.reader.pause(keep_stream=True)
        self.update_capture_controls()

    def update_capture_controls(self):
        valid = self.screen_index is not None and 0 <= self.screen_index < len(self.screens)
        self.share.setEnabled(valid and not self.capture_starting)
        self.share.setText("Starting…" if self.capture_starting else "Pause" if self.mode == "live" else "Resume" if self.mode == "paused" else "Start")
        self.share.setToolTip("Select a monitor first" if not valid else "Toggle reading and the overlay")
        self.crop_button.setEnabled(not self.reader.image.isNull() and self.mode in ("live", "screenshot"))
        if hasattr(self, "kde_button"):
            self.kde_button.setEnabled(valid and not self.capture_starting)

    def toggle_capture(self):
        if self.screen_index is None or self.capture_starting:
            return
        if self.mode == "live":
            self.pause()
        elif self.capture_kind == "kde":
            self.start_kde()
        else:
            self.start_capture()

    def start_capture(self):
        if self.screen_index is None:
            return
        resume = self.mode == "paused"
        self.auto_capture_pending = False
        self.capture_starting = True
        self.mode = "live"
        self.capture_kind = "portal"
        self.rows = []
        self.last_screen = 0
        if not resume:
            self.reader.crop = None
        self.reader.image = QImage()
        desktop = QRect()
        for screen in self.screens:
            desktop = desktop.united(screen.geometry())
        self.reader.start(self.screens[self.screen_index].geometry(), desktop)
        self.render()

    def set_screen(self, index):
        previous = self.screen_index
        self.screen_index = self.monitor.itemData(index)
        if self.screen_index != previous:
            self.reader.crop = None
        if self.screen_index is None:
            self.settings.setValue("monitor-name", "")
            if self.mode == "live":
                self.pause()
            self.update_capture_controls()
            return
        self.settings.setValue("monitor-name", self.screens[self.screen_index].name())
        if self.mode == "live" and self.capture_kind == "kde":
            self.start_kde()
        elif self.mode == "live":
            self.start_capture()
        elif self.auto_capture_pending:
            self.start_capture()
        self.render()

    def refresh_monitors(self, *args):
        selected = self.monitor.currentText() if self.screen_index is not None else ""
        self.screens = sorted(QApplication.screens(), key=lambda screen: screen.geometry().x())
        self.monitor.blockSignals(True)
        self.monitor.clear()
        self.monitor.addItem("Select monitor…", None)
        chosen = 0
        for index, screen in enumerate(self.screens):
            self.monitor.addItem(screen.name(), index)
            if screen.name() == selected:
                chosen = index + 1
        self.monitor.setCurrentIndex(chosen)
        self.monitor.blockSignals(False)
        self.set_screen(chosen)

    def start_kde(self):
        if self.screen_index is None:
            return
        resume = self.mode == "paused"
        self.auto_capture_pending = False
        self.capture_starting = True
        self.mode = "live"
        self.capture_kind = "kde"
        self.rows = []
        self.last_screen = 0
        self.reader.image = QImage()
        if not resume:
            self.reader.crop = None
        desktop = QRect()
        for screen in self.screens:
            desktop = desktop.united(screen.geometry())
        self.reader.start_kde(self.screens[self.screen_index].geometry(), desktop)
        self.render()

    def pause(self):
        self.reader.pause(keep_stream=self.capture_kind == "portal")
        self.mode = "paused"
        self.capture_starting = False
        self.show_status("Paused • labels hidden; sharing session kept for quick resume")
        self.render()

    def set_hover(self, enabled):
        self.hover_enabled = enabled
        self.settings.setValue("tooltip-prices", enabled)
        self.reader.tooltip_enabled = enabled
        self.reader.tooltip_rect = None
        self.reader.tooltip_fingerprint = None
        self.reader.shop_fingerprint = None
        self.tooltip_result = None
        self.reader.image_sequence += 1
        self.render()

    def on_pointer(self, x, y):
        if self.screen_index is None:
            self.reader.pointer = None
            return
        geometry = self.screens[self.screen_index].geometry()
        image = self.reader.image
        if not self.hover_enabled or self.mode != "live" or image.isNull() or not geometry.contains(QPoint(x, y)):
            self.reader.pointer = None
            if self.tooltip_result:
                self.tooltip_result = None
                self.render()
            return
        point = (round((x - geometry.x()) * image.width() / geometry.width()),
                 round((y - geometry.y()) * image.height() / geometry.height()))
        if point != self.reader.pointer:
            self.reader.pointer = point
            had_tooltip = self.tooltip_result is not None
            self.tooltip_result = None
            self.reader.image_sequence += 1
            if had_tooltip:
                self.render()

    def on_image(self, image):
        if self.mode == "paused":
            return
        self.capture_starting = False
        self.last_screen = time.time() - max(0, time.monotonic() - self.reader.last_frame)
        self.update_capture_controls()

    def on_reading(self, result):
        if self.mode == "paused":
            return
        self.ocr_ms = result.get("atMs")
        rows = (result.get("shop") or {}).get("rows", [])
        tooltip = result.get("tooltip")
        found = tooltip.get("found") if isinstance(tooltip, dict) else None
        pointer = self.reader.pointer
        if pointer and self.reader.crop:
            pointer = (pointer[0] - self.reader.crop.x(), pointer[1] - self.reader.crop.y())
        found = found if self.hover_enabled and not result.get("hover") and not pointer_in_shop(pointer, self.reader.shop_context) else None
        changed = rows != self.rows or found != self.tooltip_result
        self.tooltip_result = found
        self.rows = rows
        self.request_prices()
        self.update_price_status()
        if changed:
            self.render()

    def on_identity(self, identity, item):
        if self.catalog:
            self.catalog.bind_current(identity[0], identity[1], item)
            self.request_prices()
            self.render()

    def on_catalog(self, catalog):
        self.catalog = catalog
        if catalog.warning:
            self.show_status(catalog.warning)
        self.request_prices()
        self.render()

    def request_prices(self):
        if not self.catalog or self.mode in ("paused", "idle"):
            return
        observations = self.rows + ([self.tooltip_result] if self.tooltip_result else [])
        for row in observations:
            item = self.catalog.resolve(row.get("name"), row.get("tier"))
            if item:
                self.service.request(item, self.ttl)
            else:
                candidates = self.catalog.candidates(row.get("name"), row.get("tier"))
                if len(candidates) > 1:
                    self.service.resolve_identity((row.get("name"), row.get("tier")), candidates, self.ttl)

    def on_quote(self, item_id, quote):
        self.quotes[item_id] = quote
        self.errors.pop(item_id, None)
        self.update_price_status()
        self.render()

    def on_error(self, item_id, message):
        self.errors[item_id] = message
        if item_id:
            self.update_price_status()
        else:
            self.show_status(message)
        self.render()

    def update_price_status(self):
        if not self.catalog:
            return
        observations = self.rows + ([self.tooltip_result] if self.tooltip_result else [])
        for row in observations:
            item = self.catalog.resolve(row.get("name"), row.get("tier"))
            if item and item.game_id in self.errors:
                self.status_label.setText(f"Price lookup: {item.name}: {self.errors[item.game_id]}")
                return
        if self.status_label.text().startswith("Price lookup:"):
            self.status_label.setText("Market references cached locally")

    def tick(self):
        self.render()
        if self.mode in ("live", "screenshot"):
            self.request_prices()

    def set_ttl(self, value):
        self.ttl = value
        self.request_prices()
        self.render()

    def render(self):
        if not hasattr(self, "cards_layout"):
            return
        self.update_capture_controls()
        now = time.time()
        screen_old = not self.last_screen or now - self.last_screen > 8
        if self.mode == "screenshot":
            self.capture_info.setText("SCREENSHOT MODE • saved pixels, not a live shop")
        elif self.mode == "live":
            timing = f" • {self.reader.latest_latency_ms:.0f} ms reading delay" if self.reader.latest_latency_ms is not None else ""
            self.capture_info.setText("OS screen sharing • " + (f"last frame {age_text(now - self.last_screen)} ago{timing}" if self.last_screen else "waiting for selection"))
        elif self.mode == "paused":
            self.capture_info.setText("PAUSED • last captured rows, not live")
        self.summary.setText((f"{len(self.rows)} active listing{'s' if len(self.rows) != 1 else ''} • sold rows excluded" if self.rows else ("Inventory / equipment tooltip" if self.tooltip_result else "No readable player shop in this capture")) if self.catalog else "Loading Classic World item names…")
        # Cards are few (<10); preserve scroll position when the ages tick.
        position = self.scroll.verticalScrollBar().value()
        while self.cards_layout.count():
            take = self.cards_layout.takeAt(0)
            if take.widget():
                take.widget().deleteLater()
        if self.tooltip_result and self.tooltip_result.get("name"):
            name = self.tooltip_result["name"]
            item = self.catalog.resolve(name) if self.catalog else None
            quote = self.quotes.get(item.game_id) if item else None
            self.cards_layout.addWidget(label("Hovered: " + (item.name if item else name), "font-weight: 600; color: #e4bd7b", True))
            if quote:
                state = f"cached {age_text(now - quote.fetched_at)} ago" if quote.fresh(now, self.ttl) else "EXPIRED"
                self.cards_layout.addWidget(label(f"Market {mesos(quote.price)} mesos • {quote.source}\n{quote.period} median • {quote.sample_count} samples • {state}", "color: #aab5c4; font-size: 11px", True))
            else:
                self.cards_layout.addWidget(label("Looking up a Classic World market reference…", "color: #aab5c4; font-size: 11px", True))
        if not self.rows and not self.tooltip_result:
            self.cards_layout.addWidget(label("Open a player shop. Share its window, or crop the shared screen to the game. Only visible listings are read.", "color: #98a3b1; padding: 18px 4px", True))
        for row in self.rows:
            item = self.catalog.resolve(row.get("name"), row.get("tier")) if self.catalog else None
            price = row.get("price") or {}
            quote = self.quotes.get(item.game_id) if item else None
            verdict = compare(item, price.get("quantity"), price.get("mesos"), quote, now, self.ttl)
            stale_capture = self.mode == "paused" or (self.mode == "live" and screen_old)
            frame = QFrame()
            frame.setObjectName("card")
            card = QVBoxLayout(frame)
            card.setContentsMargins(13, 12, 13, 12)
            card.setSpacing(6)
            card.addWidget(label(item.name if item else row.get("name") or "Covered / unreadable item", "font-size: 13px; font-weight: 600", True))
            heading = QHBoxLayout()
            heading.addWidget(label(("Capture paused" if self.mode == "paused" else "Waiting for screen") if stale_capture else verdict.label,
                                    "font-size: 11px; color: " + COLORS["muted" if stale_capture else verdict.tone]))
            heading.addStretch()
            if verdict.unit_price is not None:
                heading.addWidget(label(mesos(verdict.unit_price) + (" / set" if item.per_set else " / each"), "font-size: 14px; font-weight: 650"))
            card.addLayout(heading)
            if price:
                card.addWidget(label(f"Listed: {price.get('quantity', '?'):,} for {mesos(price.get('mesos'))} mesos", "color: #aab5c4; font-size: 11px"))
            if item and item.cash:
                retail = f"Cash Shop: {item.nx_price:,} NX" if item.nx_price else "NX / cash item"
                if item.nx_count > 1:
                    retail += f" / pack of {item.nx_count}"
                if item.on_sale is False:
                    retail += " • not currently on sale"
                card.addWidget(label(retail + " • FM reference below is in mesos", "color: #c7a978; font-size: 10px", True))
            card.addWidget(label(verdict.detail if not stale_capture else "Resume capture before judging this listing", "color: #b7c0cc; font-size: 11px", True))
            if quote:
                reference = f"Reference {mesos(quote.price)} • {quote.period} median • {quote.sample_count:,} samples" if quote.price is not None else "No market reference supplied by this source"
                card.addWidget(label(reference, "color: #c5cbd5; font-size: 11px", True))
                cache_age = now - quote.fetched_at
                fresh = quote.fresh(now, self.ttl)
                cache_valid = quote.cache_valid(now, self.ttl)
                expiration = f"expires in {age_text(self.ttl - cache_age)}" if cache_valid else "EXPIRED • no deal rating"
                card.addWidget(label(f"Cached {age_text(cache_age)} ago • {expiration}", f"font-size: 10px; color: {COLORS['muted'] if fresh else COLORS['amber']}", True))
                data_age = f"latest report {age_text(now - quote.observed_at)} ago" if quote.observed_at else "report time unknown"
                card.addWidget(label(f"{quote.source} • {data_age}\n{quote.basis}", "font-size: 10px; color: #96a4b6", True))
                if quote.lowest_ask:
                    card.addWidget(label(f"Lowest listed ask: {mesos(quote.lowest_ask)} (may be old)", "font-size: 10px; color: #96a4b6", True))
                if verdict.net_margin is not None and fresh and not stale_capture:
                    card.addWidget(label(f"At reference resale: {mesos(verdict.net_margin)} / {'set' if item.per_set else 'each'} after 3% fee", "font-size: 10px; color: #96a4b6", True))
                link = QPushButton("View source ↗")
                link.setCursor(Qt.CursorShape.PointingHandCursor)
                link.clicked.connect(lambda checked=False, url=quote.url: self.open_source(url))
                card.addWidget(link)
            elif item:
                card.addWidget(label("Lookup unavailable • retrying later" if item.game_id in self.errors else "Fetching Classic World reference…", "font-size: 10px; color: #96a4b6", True))
            self.cards_layout.addWidget(frame)
        self.cards_layout.addStretch()
        self.scroll.verticalScrollBar().setValue(position)
        self.draw_labels(now, screen_old)

    def draw_labels(self, now, screen_old):
        if self.screen_index is None:
            self.overlay.update([0, 0, 1, 1], [], hover_enabled=False)
            return
        geometry = self.screens[self.screen_index].geometry()
        annotations = []
        # Whole-screen pixels establish an unambiguous coordinate space. A shared
        # window alone has no globally readable position under Wayland.
        image = self.reader.image
        dpr = self.screens[self.screen_index].devicePixelRatio()
        screen_matches = (not image.isNull() and abs(image.width() - geometry.width() * dpr) <= 2
                          and abs(image.height() - geometry.height() * dpr) <= 2)
        if self.labels_enabled and self.mode == "live" and not screen_old and screen_matches and self.catalog:
            sx, sy = geometry.width() / image.width(), geometry.height() / image.height()
            crop = self.reader.crop
            offset_x, offset_y = (crop.x(), crop.y()) if crop else (0, 0)
            for row in self.rows:
                area = row["area"]
                item = self.catalog.resolve(row.get("name"), row.get("tier"))
                quote = self.quotes.get(item.game_id) if item else None
                price = row.get("price") or {}
                verdict = compare(item, price.get("quantity"), price.get("mesos"), quote, now, self.ttl)
                if quote and quote.price is not None and quote.fresh(now, self.ttl):
                    suffix = f"{verdict.delta:+.0f}%" if verdict.delta is not None else ("listing price unclear" if verdict.label == "Unreadable" else verdict.label)
                    text = f"FM {mesos(quote.price)} • {suffix} • {age_text(now - quote.fetched_at)}"
                    if verdict.label == "Thin data":
                        text = f"FM {mesos(quote.price)} • thin data • {age_text(now - quote.fetched_at)}"
                elif quote and quote.price is None:
                    text = "FM • source has no market data"
                elif quote:
                    text = f"FM {mesos(quote.price)} • EXPIRED"
                elif item:
                    text = "FM unavailable" if item.game_id in self.errors else "FM checking…"
                else:
                    text = "FM • checking item version" if item is None and row.get("name") else "FM • name unreadable"
                annotations.append({"x": round((area["x"] + area["width"] + offset_x) * sx) + 9,
                                    "y": round((area["y"] + offset_y + area["height"] / 2) * sy) - 12,
                                    "name": item.name if item else row.get("name") or "Unresolved item",
                                    "text": text, "color": COLORS[verdict.tone]})
        if self.hover_enabled and self.tooltip_result and self.mode == "live" and not screen_old and screen_matches and self.catalog:
            found = self.tooltip_result
            area = found["area"]
            name = found.get("name")
            item = self.catalog.resolve(name) if name else None
            quote = self.quotes.get(item.game_id) if item else None
            sx, sy = geometry.width() / image.width(), geometry.height() / image.height()
            crop = self.reader.crop
            ox, oy = (crop.x(), crop.y()) if crop else (0, 0)
            if quote and quote.price is not None:
                fresh = quote.fresh(now, self.ttl)
                text = f"FM {mesos(quote.price)} mesos • " + (age_text(now - quote.fetched_at) if fresh else "EXPIRED")
                if fresh and quote.sample_count < 5:
                    text += " • thin data"
            else:
                text = "FM no price data" if item and item.game_id in self.errors else "FM checking reference…"
                fresh = False
            annotations.append({"name": item.name if item else name or "Unreadable tooltip name",
                                "text": text, "color": COLORS["blue" if fresh else "muted"],
                                "x": round((area["x"] + ox) * sx),
                                "y": max(7, round((area["y"] + oy) * sy) - 40)})
        self.overlay.update(list(geometry.getRect()), annotations, hover_enabled=self.hover_enabled and self.mode == "live")

    def open_source(self, url):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl(url))

    def open_screenshot(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open a Classic World shop screenshot", "", "Images (*.png *.jpg *.jpeg)")
        if path:
            self.load_screenshot(path)

    def load_screenshot(self, path):
        self.mode = "screenshot"
        self.reader.load_image(path)

    def crop(self):
        if self.reader.image.isNull():
            self.show_status("Share a screen or open a screenshot first")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Crop captured pixels")
        layout = QVBoxLayout(dialog)
        layout.addWidget(label("Drag around the game in this preview. This selects pixels in our app.", wrap=True))
        canvas = CropCanvas(self.reader.image)
        layout.addWidget(canvas)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Reset)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        buttons.button(QDialogButtonBox.StandardButton.Reset).clicked.connect(lambda: (setattr(self.reader, "crop", None), dialog.reject()))
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.reader.crop = canvas.selection()
            self.rows = []
            self.reader.image_sequence += 1
            self.reader.scan()

    def about(self):
        QMessageBox.information(self, "Classic Price Lens", "Reads OS-shared pixels and draws this independent window.\n\nNo game hooks, memory, files, messages, input or packet access. Screenshots remain local. Only item names/IDs go to public price sources.\n\nOCR: Minerva (MIT), pinned at 7e1aa7d. OCR model: ocrs, CC BY-SA 4.0. Catalog: OSMS Data Explorer. Prices: NiaMeowDB Classic World.\n\n24h median with at least 5 samples, otherwise the site's longer window. These are reported prices, not guaranteed trades. Equipment is assumed unscrolled, as requested. Its actual stats are not assessed.\n\nCache defaults to 15 minutes. Expired data has no deal rating; latest reports over 24h old also have no rating.\n\nPrices and requests are cached locally. No telemetry or screenshot uploads.")

    def closeEvent(self, event):
        self.timer.stop()
        self.hotkeys.close()
        self.reader.close(keep_stream=self.keep_capture)
        self.service.close()
        self.overlay.close()
        event.accept()
