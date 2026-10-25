from pathlib import Path
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
from .domain import DEFAULT_TTL, WORLD, age_text, compare
from .service import PriceService
from .overlay import Overlay
from .hotkeys import HotkeyManager, DEFAULT_HOTKEY, parse_shortcut
from .ui_components import DisplayMap, display_labels, price_card

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
        self.root = Path(root)
        self.setWindowTitle("Classic Price Lens")
        self.resize(480, 650)
        self.setMinimumSize(430, 440)
        self.catalog = None
        self.catalog_loading = True
        self.catalog_error = ""
        self.capture_error = ""
        self.last_diagnostic = ""
        self.setup_notice = ""
        self.first_price_seen = False
        self.starting_at = 0.0
        self.session_available = False
        self.rows = []
        self.quotes = {}
        self.errors = {}
        self.expanded_details = set()
        self.mode = "idle"
        self.snapshot_path = snapshot
        self.last_screen = 0
        self.ocr_ms = None
        self.overlay = Overlay(root, self)
        self.screens = sorted(QApplication.screens(), key=lambda screen: (screen.geometry().x(), screen.geometry().y()))
        self.screen_index = None
        self.capture_starting = False
        self.capture_kind = "kde" if kde_capture else "portal"
        self.keep_capture = False
        self.settings = QSettings("LocalTools", "Classic Price Lens")
        self.first_price_seen = self.settings.value("first-price-seen", False, type=bool)
        self.setup_dismissed = self.settings.value("setup-help-dismissed", False, type=bool)
        self.labels_enabled = self.settings.value("show-prices", True, type=bool)
        self.pinned = self.settings.value("keep-on-top", False, type=bool)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self.pinned)
        self.ttl = self.settings.value("cache-ttl", DEFAULT_TTL, type=int)
        if self.ttl not in (300, 900, 1800, 3600):
            self.ttl = DEFAULT_TTL
        self.hotkey_sequence = self.settings.value("hotkey-sequence", DEFAULT_HOTKEY)
        self.hotkey_description = self.settings.value("hotkey-description", "")
        self.hotkey_status = ""
        self.hotkey_dialog_open = False
        self.hotkeys = HotkeyManager(self)
        self.hotkey_enabled = self.settings.value("hotkey-enabled", not self.hotkeys.portal, type=bool)
        self.hotkeys.activated.connect(self.on_hotkey)
        self.hotkeys.changed.connect(self.on_hotkey_changed)
        self.hotkeys.status.connect(self.on_hotkey_status)
        self.hover_enabled = self.settings.value("tooltip-prices", True, type=bool)
        self.tooltip_result = None
        self.service = PriceService(cache_path, self)
        self.reader = PixelReader(root, self)
        self.reader.tooltip_enabled = self.hover_enabled and self.labels_enabled
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
        layout.setSpacing(10)
        heading = QHBoxLayout()
        mark = QLabel()
        mark.setPixmap(QPixmap(str(self.root / "price_lens/resources/icon.png")).scaled(27, 27, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        heading.addWidget(mark)
        heading.addWidget(label("Classic Price Lens", "font-size: 21px; font-weight: 650; color: #f1e6d5"))
        heading.addStretch()
        self.settings_button = QPushButton("Settings")
        self.settings_button.clicked.connect(self.open_settings)
        heading.addWidget(self.settings_button)
        layout.addLayout(heading)
        layout.addWidget(label("Market prices beside your Classic World items", "color: #a6b1bf; font-size: 11px", True))

        self.setup_frame = QFrame()
        self.setup_frame.setObjectName("setup")
        setup = QVBoxLayout(self.setup_frame)
        setup.setContentsMargins(12, 12, 12, 12)
        setup.setSpacing(8)
        self.status_badge = label("Choose a display", "color: #e4bd7b; font-weight: 650; font-size: 13px")
        setup.addWidget(self.status_badge)
        self.step_label = label("1 Choose a display   ›   2 Share it   ›   3 Open a shop", "color: #a6b1bf; font-size: 10px", True)
        setup.addWidget(self.step_label)
        self.display_map = DisplayMap()
        self.display_map.selected.connect(lambda index: self.monitor.setCurrentIndex(index + 1))
        setup.addWidget(self.display_map)
        self.monitor = QComboBox()
        self.monitor.setAccessibleName("Display containing Classic World")
        self.monitor.addItem("Choose the display containing Classic World…", None)
        selected = self.settings.value("monitor-name", "")
        for index, (screen, description) in enumerate(zip(self.screens, display_labels(self.screens))):
            self.monitor.addItem(description, index)
            self.monitor.setItemData(index + 1, screen.name(), Qt.ItemDataRole.ToolTipRole)
            if selected and selected == screen.name():
                self.screen_index = index
        self.monitor.setCurrentIndex(self.screen_index + 1 if self.screen_index is not None else 0)
        self.monitor.currentIndexChanged.connect(self.set_screen)
        setup.addWidget(self.monitor)
        actions = QHBoxLayout()
        self.share = QPushButton("Start reading")
        self.share.setObjectName("primary")
        self.share.clicked.connect(self.toggle_capture)
        actions.addWidget(self.share, 1)
        self.cancel_setup = QPushButton("Cancel setup")
        self.cancel_setup.clicked.connect(self.cancel_capture_setup)
        self.cancel_setup.setVisible(False)
        actions.addWidget(self.cancel_setup)
        setup.addLayout(actions)
        self.capture_info = label("Choose a display to enable Start reading.", "color: #bbc4cf; font-size: 11px", True)
        setup.addWidget(self.capture_info)
        self.recovery_button = QPushButton()
        self.recovery_button.setObjectName("quiet")
        self.recovery_button.clicked.connect(self.recover)
        self.recovery_button.setVisible(False)
        setup.addWidget(self.recovery_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.setup_frame)

        self.success_frame = QFrame()
        self.success_frame.setObjectName("setup")
        success = QVBoxLayout(self.success_frame)
        success.setContentsMargins(12, 10, 12, 10)
        success.addWidget(label("Your overlay is working", "color: #86ceac; font-weight: 650"))
        success.addWidget(label("Minimize this panel to keep the game clear. Closing the app ends reading and sharing.", "color: #a6b1bf; font-size: 11px", True))
        options = QHBoxLayout()
        shortcut = QPushButton("Set a hotkey…")
        shortcut.clicked.connect(self.configure_hotkey)
        options.addWidget(shortcut)
        minimize = QPushButton("Minimize panel")
        minimize.clicked.connect(self.showMinimized)
        options.addWidget(minimize)
        dismiss = QPushButton("Got it")
        dismiss.setObjectName("quiet")
        dismiss.clicked.connect(self.dismiss_setup)
        options.addWidget(dismiss)
        success.addLayout(options)
        self.success_frame.setVisible(False)
        layout.addWidget(self.success_frame)

        self.summary = label("", "font-size: 12px; color: #dde1e7", True)
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
        footer = QHBoxLayout()
        help_button = QPushButton("Setup help")
        help_button.setObjectName("quiet")
        help_button.clicked.connect(self.setup_help)
        footer.addWidget(help_button)
        footer.addStretch()
        self.demo_button = QPushButton("Preview with examples")
        self.demo_button.setObjectName("quiet")
        self.demo_button.clicked.connect(self.preview_examples)
        footer.addWidget(self.demo_button)
        layout.addLayout(footer)
        self.notice = label("Screen pixels only · equipment assumed unscrolled", "color: #939eac; font-size: 10px", True)
        layout.addWidget(self.notice)
        self.status_label = label("", "color: #939eac; font-size: 10px", True)
        self.status_label.setVisible(False)
        self.setCentralWidget(body)
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #171c25; color: #dce1e8; font-family: 'Noto Sans', sans-serif; font-size: 12px; }
            QLabel { background: transparent; }
            QPushButton, QComboBox, QKeySequenceEdit { background: #252d3b; border: 1px solid #354052; border-radius: 6px; padding: 7px 9px; }
            QPushButton:hover { background: #323c4c; border-color: #927b58; }
            QPushButton:pressed { background: #404655; }
            QPushButton:disabled { background: #202630; border-color: #2c333e; color: #727c8b; }
            QPushButton#primary { background: #d9ad66; color: #231e16; border-color: #d9ad66; font-weight: 650; }
            QPushButton#primary:hover { background: #ebc483; }
            QPushButton#primary:disabled { background: #2b303a; color: #828b97; border-color: #39414e; }
            QPushButton#quiet { background: transparent; border: 0; color: #b1bac7; padding: 5px 2px; text-align: left; }
            QPushButton#quiet:hover { color: #ebc483; }
            QCheckBox { color: #b5bfcc; padding: 3px 0; }
            QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }
            QFrame#card, QFrame#setup { background: #202734; border: 1px solid #303b4b; border-radius: 9px; }
            QFrame#card QLabel, QFrame#setup QLabel, QWidget#cardDetails, QWidget#displayMap { background: transparent; border: none; }
            QScrollBar:vertical { background: #171c25; width: 6px; }
            QScrollBar::handle:vertical { background: #455064; border-radius: 3px; min-height: 20px; }
        """)
        self.build_settings()
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self.service.start()
        if snapshot:
            QTimer.singleShot(300, lambda: self.load_screenshot(snapshot))
        elif (auto_capture or kde_capture) and self.screen_index is not None:
            QTimer.singleShot(500, self.start_kde if kde_capture else self.start_capture)
        self.render()
        QApplication.instance().screenAdded.connect(self.refresh_monitors)
        QApplication.instance().screenRemoved.connect(self.refresh_monitors)
        if QApplication.platformName() != "offscreen":
            QTimer.singleShot(700, self.initialize_hotkey)

    def build_settings(self):
        self.settings_dialog = QDialog(self)
        self.settings_dialog.setWindowTitle("Settings")
        self.settings_dialog.setMinimumWidth(395)
        layout = QVBoxLayout(self.settings_dialog)
        layout.setSpacing(10)
        layout.addWidget(label("Overlay", "font-size: 15px; font-weight: 650"))
        self.labels_check = QCheckBox("Show market prices beside items")
        self.labels_check.setChecked(self.labels_enabled)
        self.labels_check.toggled.connect(self.set_labels)
        layout.addWidget(self.labels_check)
        self.hover_check = QCheckBox("Also show prices when hovering inventory / equipment")
        self.hover_check.setChecked(self.hover_enabled)
        self.hover_check.setEnabled(self.labels_enabled)
        self.hover_check.toggled.connect(self.set_hover)
        layout.addWidget(self.hover_check)
        self.pin_check = QCheckBox("Keep the control panel on top")
        self.pin_check.setChecked(self.pinned)
        self.pin_check.toggled.connect(self.pin)
        layout.addWidget(self.pin_check)
        self.hotkey_button = QPushButton("Keyboard shortcut…")
        self.hotkey_button.clicked.connect(self.configure_hotkey)
        layout.addWidget(self.hotkey_button)
        layout.addWidget(label("Price update interval", "font-size: 13px; font-weight: 650"))
        self.ttl_combo = QComboBox()
        for minutes in (5, 15, 30, 60):
            self.ttl_combo.addItem(f"{minutes} minutes" + (" · recommended" if minutes == 15 else ""), minutes * 60)
        self.ttl_combo.setCurrentIndex((300, 900, 1800, 3600).index(self.ttl))
        self.ttl_combo.currentIndexChanged.connect(lambda index: self.set_ttl(self.ttl_combo.itemData(index)))
        layout.addWidget(self.ttl_combo)
        layout.addWidget(label("A checked price is reused during this interval. Pausing stops new price lookups. Cache age and the latest market report are shown separately.", "font-size: 11px; color: #a6b1bf", True))
        layout.addWidget(label("Troubleshooting", "font-size: 15px; font-weight: 650"))
        self.crop_button = QPushButton("Limit the reading area…")
        self.crop_button.clicked.connect(self.crop)
        layout.addWidget(self.crop_button)
        screenshot = QPushButton("Open a saved screenshot…")
        screenshot.clicked.connect(self.open_screenshot)
        layout.addWidget(screenshot)
        if shutil.which("spectacle"):
            self.kde_button = QPushButton("Try KDE screenshot capture")
            self.kde_button.clicked.connect(self.start_kde)
            layout.addWidget(self.kde_button)
        self.diagnostics_button = QPushButton("Connection details / capture preview…")
        self.diagnostics_button.clicked.connect(self.troubleshoot)
        layout.addWidget(self.diagnostics_button)
        about = QPushButton("About / price sources")
        about.clicked.connect(self.about)
        layout.addWidget(about)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.settings_dialog.reject)
        layout.addWidget(buttons)

    def open_settings(self):
        self.update_capture_controls()
        self.settings_dialog.exec()

    def set_labels(self, enabled):
        self.labels_enabled = enabled
        self.reader.tooltip_enabled = enabled and self.hover_enabled
        self.hover_check.setEnabled(enabled)
        self.settings.setValue("show-prices", enabled)
        self.render()

    def dismiss_setup(self):
        self.setup_dismissed = True
        self.settings.setValue("setup-help-dismissed", True)
        self.success_frame.hide()

    def setup_help(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Getting started")
        dialog.setMinimumWidth(385)
        layout = QVBoxLayout(dialog)
        for title, detail in [
            ("1. Choose your display", "Pick the display containing Classic World. The numbers match the small display diagram."),
            ("2. Start reading", "When the OS sharing chooser appears, select the same display. Full-workspace sharing is also supported."),
            ("3. Open a shop or hover an item", "Keep item names and shop prices visible. References appear beside shop rows or above inventory tooltips."),
            ("Pause, resume and close", "Pause hides labels and keeps sharing ready for Resume. Minimize the panel to keep reading; closing the app ends sharing."),
        ]:
            layout.addWidget(label(title, "font-weight: 650; color: #e8d2ac"))
            layout.addWidget(label(detail, "color: #b6c0cd", True))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()
        dialog.deleteLater()

    def preview_examples(self):
        from .domain import Item, Quote
        dialog = QDialog(self)
        dialog.setObjectName("exampleDialog")
        dialog.setWindowTitle("Example preview")
        dialog.setMinimumWidth(395)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label("Example prices · no screen sharing needed", "font-size: 15px; font-weight: 650", True))
        layout.addWidget(label("These made-up values explain the labels. They are not current market prices.", "color: #e4bd7b", True))
        now = time.time()
        item = Item(1002058, "Green Bamboo Hat", equipment=True)
        quote = Quote(item.game_id, 8000, now - 180, now - 3600, 25, "Example", "", "24h")
        layout.addWidget(price_card(item=item, row={"name": item.name, "price": {"quantity": 1, "mesos": 6000}}, quote=quote, now=now, ttl=DEFAULT_TTL, example=True))
        layout.addWidget(label("The small item name identifies the label. The reference is a meso resale price, including for NX items. Few reports or older data receive no comparison rating.", "color: #b6c0cd", True))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()
        dialog.deleteLater()

    def troubleshoot(self):
        from . import __version__
        dialog = QDialog(self)
        dialog.setWindowTitle("Connection details")
        dialog.setMinimumWidth(400)
        layout = QVBoxLayout(dialog)
        title, description, tone, action = self.connection_state()
        layout.addWidget(label(title, "font-size: 15px; font-weight: 650"))
        layout.addWidget(label(description, wrap=True))
        timing = getattr(self.reader, "latest_latency_ms", None)
        info = f"Version {__version__} · {self.capture_kind} capture\n"
        info += f"Reading delay: {timing:.0f} ms\n" if timing is not None else "No reading timing yet\n"
        info += f"Price update interval: {self.ttl // 60} minutes"
        layout.addWidget(label(info, "color: #a6b1bf", True))
        if not self.reader.image.isNull():
            preview = QLabel()
            preview.setPixmap(QPixmap.fromImage(self.reader.image).scaled(550, 290, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            preview.setToolTip("The existing local capture; opening this preview does not request sharing again")
            layout.addWidget(preview)
        if self.last_diagnostic:
            details = label("Latest technical message: " + self.last_diagnostic, "font-size: 10px; color: #98a3b1", True)
            details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(details)
        retry = QPushButton("Retry item names")
        retry.setEnabled(not self.catalog_loading)
        retry.clicked.connect(lambda: (self.retry_catalog(), dialog.reject()))
        layout.addWidget(retry)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()
        dialog.deleteLater()

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
        dialog.setObjectName("hotkeyDialog")
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
        self.pinned = checked
        self.settings.setValue("keep-on-top", checked)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, checked)
        self.show()

    def selected_display(self):
        if self.screen_index is None or self.screen_index >= len(self.screens):
            return "your display"
        return self.monitor.itemText(self.screen_index + 1).split(" · ")[0]

    def image_matches_screen(self):
        if self.screen_index is None or self.reader.image.isNull():
            return False
        screen = self.screens[self.screen_index]
        geometry, scale = screen.geometry(), screen.devicePixelRatio()
        return (abs(self.reader.image.width() - geometry.width() * scale) <= 2
                and abs(self.reader.image.height() - geometry.height() * scale) <= 2)

    def connection_state(self):
        if self.mode == "screenshot":
            return ("Saved screenshot", "These items come from a saved image. Start reading to follow the game on your display.", "blue", "")
        if self.screen_index is None:
            return ("Choose a display", self.setup_notice or "Choose the display containing Classic World to enable Start reading.", "amber", "")
        display = self.selected_display()
        if self.capture_error:
            return ("Sharing needs attention", self.capture_error, "amber", "Reconnect display")
        if self.capture_starting:
            hint = f"In the OS sharing chooser, select {display}. Full-workspace sharing also works."
            if time.monotonic() - self.starting_at > 10:
                hint += " The chooser may be behind another window; finish it or cancel setup below."
            return ("Waiting for screen sharing", hint, "amber", "")
        if self.mode == "paused":
            return ("Paused", "Labels are hidden and price lookups are paused. Resume reuses your sharing session." if self.session_available else "Labels are hidden. Resume will reconnect your display.", "muted", "")
        if self.mode == "live":
            if not self.last_screen or time.time() - self.last_screen > 8:
                return ("Waiting for a fresh screen", "The last screen is no longer current. References stay visible here, and overlay labels are hidden until reading resumes.", "amber", "Reconnect display")
            if not self.image_matches_screen():
                return ("Share the selected display", f"The shared image does not match {display}. Reconnect and choose that display, or share the full workspace, so labels can line up.", "amber", "Reconnect display")
            if not self.labels_enabled:
                return ("Reading · labels hidden", "Price labels are disabled. Item prices still appear in this panel; enable labels to show them beside the game.", "blue", "Show price labels")
            return ("Reading " + display, "Open a Classic World shop or hover over an inventory / equipment item. Keep names and prices visible.", "green", "")
        return ("Ready to start", self.setup_notice or f"Click Start reading, then choose {display} in the OS sharing chooser. This app reads screen pixels only.", "blue", "")

    def show_status(self, message):
        self.last_diagnostic = message
        if message.startswith(("Screen sharing stopped", "OS capture:", "KDE screen capture failed", "Capture dimensions", "Invalid local capture")):
            self.capture_error = "Screen sharing ended or could not start. Reconnect when ready and select the display containing Classic World."
            self.capture_starting = False
            self.session_available = False
            self.mode = "paused" if self.last_screen else "idle"
            self.reader.pause(keep_stream=False)
        elif message.startswith(("Reader could not start", "Screen reader stopped", "Screen reader timed out")):
            self.capture_error = "The item reader could not start. Open Settings → Connection details, or reinstall the app if the offline self-test fails."
            self.capture_starting = False
            self.session_available = False
            self.mode = "paused" if self.last_screen else "idle"
            self.reader.pause(keep_stream=False)
        if hasattr(self, "status_label"):
            self.status_label.setText(message)
        if hasattr(self, "crop_button"):
            self.render()

    def update_capture_controls(self):
        valid = self.screen_index is not None and 0 <= self.screen_index < len(self.screens)
        self.share.setEnabled(valid and not self.capture_starting)
        self.share.setText("Waiting for sharing…" if self.capture_starting else "Pause reading" if self.mode == "live" else "Resume reading" if self.mode == "paused" and self.session_available else "Start reading")
        self.share.setToolTip("Choose a display first" if not valid else "Toggle reading and price labels")
        self.monitor.setEnabled(not self.capture_starting)
        self.display_map.setEnabled(not self.capture_starting)
        self.display_map.configure(self.screens, self.screen_index)
        self.display_map.setVisible(len(self.screens) > 1 and self.mode == "idle")
        self.step_label.setVisible(not self.first_price_seen and self.mode != "screenshot")
        self.step_label.setText("Step 1 of 3 · Choose where Classic World is running" if not valid else
                                "Step 2 of 3 · Approve screen sharing" if self.capture_starting else
                                "Step 3 of 3 · Open a shop or hover an item" if self.mode == "live" else
                                "Step 2 of 3 · Start reading to share this display")
        self.cancel_setup.setVisible(self.capture_starting)
        title, detail, tone, action = self.connection_state()
        self.status_badge.setText(title)
        self.status_badge.setStyleSheet(f"color: {COLORS[tone]}; font-weight: 650; font-size: 13px")
        self.capture_info.setText(detail)
        self.recovery_button.setVisible(bool(action))
        self.recovery_button.setText(action)
        self.success_frame.setVisible(self.first_price_seen and self.labels_enabled and not self.setup_dismissed and self.mode == "live" and not self.capture_starting and not self.capture_error)
        if hasattr(self, "crop_button"):
            self.crop_button.setEnabled(not self.reader.image.isNull() and self.mode in ("live", "screenshot") and not self.capture_starting)
        if hasattr(self, "kde_button"):
            self.kde_button.setEnabled(valid and not self.capture_starting)

    def cancel_capture_setup(self):
        if not self.capture_starting:
            return
        self.mode = "idle"
        self.capture_starting = False
        self.session_available = False
        self.capture_error = ""
        self.setup_notice = "Sharing setup was canceled. Start reading whenever you are ready."
        self.reader.pause(keep_stream=False)
        self.rows = []
        self.tooltip_result = None
        self.render()

    def recover(self):
        if self.screen_index is None:
            return
        if self.recovery_button.text() == "Show price labels":
            self.labels_check.setChecked(True)
            return
        self.reader.pause(keep_stream=False)
        self.session_available = False
        self.mode = "idle"
        self.capture_error = ""
        self.start_capture()

    def retry_catalog(self):
        if self.catalog_loading:
            return
        self.catalog_loading = True
        self.catalog_error = ""
        self.service.start()
        self.render()

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
        resume = self.mode == "paused" and self.session_available
        self.capture_starting = True
        self.starting_at = time.monotonic()
        self.capture_error = ""
        self.setup_notice = ""
        self.mode = "live"
        self.capture_kind = "portal"
        self.rows = []
        self.tooltip_result = None
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
        selected = self.monitor.itemData(index)
        changed = selected != previous
        if changed and self.mode in ("live", "paused"):
            self.reader.pause(keep_stream=False)
            self.mode = "idle"
            self.session_available = False
            self.capture_starting = False
            self.rows = []
            self.tooltip_result = None
            self.last_screen = 0
        self.screen_index = selected
        if changed:
            self.reader.crop = None
            self.capture_error = ""
            self.setup_notice = ""
        if selected is not None:
            self.settings.setValue("monitor-name", self.screens[selected].name())
        elif changed:
            self.settings.setValue("monitor-name", "")
        self.render()

    def refresh_monitors(self, *args):
        selected_name = self.settings.value("monitor-name", "") if self.screen_index is not None else ""
        was_live = self.mode == "live"
        self.screens = sorted(QApplication.screens(), key=lambda screen: (screen.geometry().x(), screen.geometry().y()))
        self.monitor.blockSignals(True)
        self.monitor.clear()
        self.monitor.addItem("Choose the display containing Classic World…", None)
        chosen = None
        for index, (screen, description) in enumerate(zip(self.screens, display_labels(self.screens))):
            self.monitor.addItem(description, index)
            self.monitor.setItemData(index + 1, screen.name(), Qt.ItemDataRole.ToolTipRole)
            if screen.name() == selected_name and selected_name:
                chosen = index
        self.monitor.setCurrentIndex(chosen + 1 if chosen is not None else 0)
        self.monitor.blockSignals(False)
        self.screen_index = chosen
        if chosen is None and self.mode in ("live", "paused"):
            self.reader.pause(keep_stream=False)
            self.mode = "idle"
            self.capture_starting = self.session_available = False
            self.rows = []
            self.tooltip_result = None
            self.setup_notice = "The selected display is no longer connected. Choose another display to continue."
        elif was_live:
            self.start_kde() if self.capture_kind == "kde" else self.start_capture()
        self.render()

    def start_kde(self):
        if self.screen_index is None:
            return
        resume = self.mode == "paused" and self.session_available
        self.capture_starting = True
        self.starting_at = time.monotonic()
        self.capture_error = ""
        self.setup_notice = ""
        self.mode = "live"
        self.capture_kind = "kde"
        self.rows = []
        self.tooltip_result = None
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
        if self.capture_starting:
            self.cancel_capture_setup()
            return
        self.mode = "paused"
        self.reader.pause(keep_stream=self.capture_kind == "portal")
        self.capture_starting = False
        self.session_available = True
        self.render()

    def set_hover(self, enabled):
        self.hover_enabled = enabled
        self.settings.setValue("tooltip-prices", enabled)
        self.reader.tooltip_enabled = enabled and self.labels_enabled
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
        if not self.labels_enabled or not self.hover_enabled or self.mode != "live" or image.isNull() or not geometry.contains(QPoint(x, y)):
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
        if self.mode not in ("live", "screenshot"):
            return
        was_starting = self.capture_starting
        self.capture_starting = False
        self.session_available = self.mode == "live"
        self.capture_error = ""
        self.last_screen = time.time() - max(0, time.monotonic() - self.reader.last_frame)
        self.update_capture_controls()
        if was_starting:
            self.render()

    def on_reading(self, result):
        if self.mode not in ("live", "screenshot"):
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
        self.catalog_loading = False
        self.catalog_error = ""
        if catalog.warning:
            self.last_diagnostic = catalog.warning
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
        self.last_diagnostic = message
        if not item_id:
            self.catalog_loading = False
            self.catalog_error = "Item names could not be loaded. Check your internet connection, then retry."
        self.update_price_status()
        self.render()

    def update_price_status(self):
        if not self.catalog:
            return
        observations = self.rows + ([self.tooltip_result] if self.tooltip_result else [])
        failed = any((item := self.catalog.resolve(row.get("name"), row.get("tier")))
                     and item.game_id in self.errors for row in observations)
        self.status_label.setText("Some market references are unavailable; cached prices are kept." if failed else "Market references cached locally")

    def tick(self):
        self.render()
        if self.mode in ("live", "screenshot"):
            self.request_prices()

    def set_ttl(self, value):
        self.ttl = value
        self.settings.setValue("cache-ttl", value)
        self.request_prices()
        self.render()

    def set_details_open(self, key, expanded):
        if expanded:
            self.expanded_details.add(key)
        else:
            self.expanded_details.discard(key)

    def quote_for(self, item):
        quote = self.quotes.get(item.game_id) if item else None
        if (quote and quote.game_id == item.game_id and quote.world == WORLD
                and quote.condition == "clean" and quote.per_set == item.per_set):
            return quote
        return None

    def empty_card(self):
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(8)
        if self.mode == "idle":
            title = "Let's find your first price" if not self.first_price_seen else "Ready when you are"
            detail = "Choose a display above, then click Start reading. You can preview the labels with example items below."
        elif self.mode == "paused":
            title, detail = "Reading is paused", "Resume to show price labels again. Existing references remain cached."
        elif self.capture_starting:
            title, detail = "Finish screen sharing", "Use the OS chooser to share the selected display or the full workspace. This panel will update when a screen arrives."
        elif self.catalog_error:
            title, detail = "Item names are unavailable", self.catalog_error
        elif self.catalog_loading:
            title, detail = "Getting item names ready", "The first launch downloads the Classic World item list. Saved item names are reused on later launches."
        elif self.mode == "screenshot":
            title, detail = "No items found in this image", "Use a clear screenshot with full item names and visible prices. Live reading is available from Start reading above."
        else:
            title, detail = "Ready for a shop or inventory item", "Open a Classic World player shop, or hover over an item in inventory / equipment. Keep its name and shop price visible."
        layout.addWidget(label(title, "font-size: 15px; font-weight: 650; color: #e8d2ac", True))
        layout.addWidget(label(detail, "color: #b4bfcc; font-size: 12px", True))
        if self.catalog_error and not self.catalog_loading:
            retry = QPushButton("Retry item names")
            retry.clicked.connect(self.retry_catalog)
            layout.addWidget(retry)
        return frame

    def render(self):
        if not hasattr(self, "cards_layout"):
            return
        self.update_capture_controls()
        now = time.time()
        screen_old = not self.last_screen or now - self.last_screen > 8
        observations = self.rows + ([self.tooltip_result] if self.tooltip_result else [])
        ready = 0
        if self.catalog:
            for row in observations:
                item = self.catalog.resolve(row.get("name"), row.get("tier"))
                quote = self.quote_for(item)
                if quote and quote.price is not None and quote.fresh(now, self.ttl):
                    ready += 1
        count = len(observations)
        if count:
            self.summary.setText(("Last read: " if self.mode == "paused" else "") + f"{count} item{'s' if count != 1 else ''} · {ready} market reference{'s' if ready != 1 else ''} ready")
        else:
            self.summary.setText("")
        # Keep the UI small at rest. Rebuild only when content/state changes or
        # the five-second age bucket changes; screen frames never rebuild cards.
        card_key = (repr(self.rows), repr(self.tooltip_result), repr(self.quotes), repr(self.errors),
                    self.mode, screen_old, self.capture_starting, self.catalog_loading,
                    self.catalog_error, id(self.catalog), self.ttl, int(now // 5), tuple(sorted(map(str, self.expanded_details))),
                    tuple((key, quote.cache_valid(now, self.ttl), quote.fresh(now, self.ttl)) for key, quote in self.quotes.items()))
        if card_key != getattr(self, "card_key", None):
            self.card_key = card_key
            position = self.scroll.verticalScrollBar().value()
            while self.cards_layout.count():
                take = self.cards_layout.takeAt(0)
                if take.widget():
                    take.widget().deleteLater()
            if not observations:
                self.cards_layout.addWidget(self.empty_card())
            card_rows = ([(self.tooltip_result, True)] if self.tooltip_result else []) + [(row, False) for row in self.rows]
            for index, (row, hovered) in enumerate(card_rows):
                item = self.catalog.resolve(row.get("name"), row.get("tier")) if self.catalog else None
                quote = self.quote_for(item)
                key = (index, item.game_id if item else row.get("name"), hovered)
                card = price_card(item=item, row=row, quote=quote, now=now, ttl=self.ttl,
                                  paused=self.mode == "paused", old_capture=self.mode == "live" and screen_old,
                                  lookup_error=bool(item and item.game_id in self.errors), hovered=hovered,
                                  expanded=key in self.expanded_details,
                                  details_changed=lambda expanded, key=key: self.set_details_open(key, expanded),
                                  open_source=self.open_source)
                self.cards_layout.addWidget(card)
            self.cards_layout.addStretch()
            self.scroll.verticalScrollBar().setValue(position)
        self.draw_labels(now, screen_old)

    def draw_labels(self, now, screen_old):
        if self.screen_index is None:
            self.overlay.update([0, 0, 1, 1], [], hover_enabled=False)
            return
        geometry = self.screens[self.screen_index].geometry()
        annotations = []
        ready_price = False
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
                quote = self.quote_for(item)
                price = row.get("price") or {}
                verdict = compare(item, price.get("quantity"), price.get("mesos"), quote, now, self.ttl)
                if quote and quote.price is not None and quote.fresh(now, self.ttl):
                    ready_price = True
                    suffix = f"{verdict.delta:+.0f}%" if verdict.delta is not None else ("listing price unclear" if verdict.label == "Unreadable" else verdict.label)
                    text = f"FM {mesos(quote.price)} • {suffix} • {age_text(now - quote.fetched_at)}"
                    if verdict.label == "Thin data":
                        text = f"FM {mesos(quote.price)} • few reports • {age_text(now - quote.fetched_at)}"
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
        if self.labels_enabled and self.hover_enabled and self.tooltip_result and self.mode == "live" and not screen_old and screen_matches and self.catalog:
            found = self.tooltip_result
            area = found["area"]
            name = found.get("name")
            item = self.catalog.resolve(name) if name else None
            quote = self.quote_for(item)
            sx, sy = geometry.width() / image.width(), geometry.height() / image.height()
            crop = self.reader.crop
            ox, oy = (crop.x(), crop.y()) if crop else (0, 0)
            if quote and quote.price is not None:
                fresh = quote.fresh(now, self.ttl)
                ready_price = ready_price or fresh
                text = f"FM {mesos(quote.price)} mesos • " + (age_text(now - quote.fetched_at) if fresh else "EXPIRED")
                if fresh and quote.sample_count < 5:
                    text += " • few reports"
            else:
                text = "FM • source has no market data" if quote else "FM no price data" if item and item.game_id in self.errors else "FM checking reference…"
                fresh = False
            annotations.append({"name": item.name if item else name or "Unreadable tooltip name",
                                "text": text, "color": COLORS["blue" if fresh else "muted"],
                                "x": round((area["x"] + ox) * sx),
                                "y": max(7, round((area["y"] + oy) * sy) - 40)})
        self.overlay.update(list(geometry.getRect()), annotations, hover_enabled=self.labels_enabled and self.hover_enabled and self.mode == "live")
        if (annotations and ready_price and not self.first_price_seen):
            self.first_price_seen = True
            self.settings.setValue("first-price-seen", True)
            self.update_capture_controls()

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
        self.capture_starting = False
        self.session_available = False
        self.capture_error = ""
        self.rows = []
        self.tooltip_result = None
        self.reader.load_image(path)
        self.render()

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
