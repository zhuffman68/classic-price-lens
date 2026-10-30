from pathlib import Path
import shutil
import time

from PySide6.QtCore import QEvent, QPoint, QRect, Qt, QTimer, QSettings, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QCursor
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from .capture import PixelReader, pointer_in_shop
from .domain import DEFAULT_TTL, WORLD, compare, age_text
from .service import PriceService
from .price_status import reference_status
from .overlay import Overlay
from .hotkeys import HotkeyManager
from .ui_components import display_labels, price_card, mesos
from .tray import TrayController
from .experience_ui import ExperiencePanel
from .platform_paths import data_directory
from .search import PriceSearch
from .motion import AnimatedTabs, ContentArea, CardArea, MotionLabel
from .fonts import interface_family
from .branding import Brand
from .shop_rows import ShopRows
from .tooltip_geometry import description_bounds, still_present, TooltipReference
from .tooltip_names import TooltipNames,name_key
from .chat import ChatTranslation
from .translation_ui import TranslationPanel
from .compose import KoreanComposer
from .composer_ui import ComposerDialog
from .overlay_layout import tracking_rows
from .thumbnails import ThumbnailCache
from .shortcut_defaults import load as load_shortcuts, label as shortcut_label
from . import window_size
from .capture_platform import uses_system_picker
from .window_policy import NormalWindow, is_maximize_message
from .tls import catalog_error_text
from .watchlist import Watchlist, WatchEncounters
from .reference_service import ReferenceService
from .reference_ui import DatabasePanel
from .recent_items import RecentItems,ActiveCards
from .overlay_notice import OverlayNotice
from . import APP_NAME, LEGACY_APP_NAME

COLORS = {"green": "#86ceac", "red": "#ed9394", "amber": "#e4bd7b", "blue": "#9ebde3", "muted": "#98a3b1"}


def label(text="", style="", wrap=False):
    widget = MotionLabel(text)
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
    closed = Signal()

    def __init__(self, root, cache_path, snapshot=None, auto_capture=False, kde_capture=False):
        super().__init__()
        self.root = Path(root)
        self.setWindowTitle(APP_NAME)
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
        self.card_sightings=ActiveCards(self)
        self.card_sightings.changed.connect(self.render)
        self.tooltip_reference=TooltipReference()
        self.tooltip_names=TooltipNames()
        self.shop_rows = ShopRows(self.shop_identity)
        self.shop_open = False
        self.shop_tooltip_rect = None
        self.quotes = {}
        self.quote_generation = None
        self.errors = {}
        self.mode = "idle"
        self.snapshot_path = snapshot
        self.last_screen = 0
        self.last_identified_at=0.0
        self.ocr_ms = None
        self.overlay = Overlay(root, self)
        self.screens = sorted(QApplication.screens(), key=lambda screen: (screen.geometry().x(), screen.geometry().y()))
        self.screen_index = None
        self.capture_starting = False
        self.capture_kind = "kde" if kde_capture else "portal"
        self.keep_capture = False
        self.closing = False
        self.settings = QSettings("LocalTools", LEGACY_APP_NAME)
        self.watchlist = Watchlist(self.settings, self)
        self.watch_encounters = WatchEncounters()
        window_size.restore(self, self.settings)
        self.normal_window = NormalWindow(self)
        shortcuts=load_shortcuts(self.settings)
        self.first_price_seen = self.settings.value("first-price-seen", False, type=bool)
        self.labels_enabled = self.settings.value("show-prices", True, type=bool)
        self.settings.setValue("keep-on-top", False)
        self.minimize_to_tray = self.settings.value("minimize-to-tray", True, type=bool)
        self.auto_game_area = self.settings.value("auto-game-area", True, type=bool)
        self.exp_enabled = False
        self.exp_overlay = self.settings.value("exp-overlay", True, type=bool)
        self.meso_overlay = self.settings.value('meso-overlay',self.exp_overlay,type=bool)
        self.settings.setValue('meso-overlay',self.meso_overlay)
        self.exp_display = self.settings.value("exp-display", "percent")
        if self.exp_display not in ("percent","raw","both"):self.exp_display = "percent"
        self.reduce_motion = self.settings.value("reduce-motion", False, type=bool)
        QApplication.instance().setProperty("reduceMotion", self.reduce_motion)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)
        self.ttl = self.settings.value("cache-ttl", DEFAULT_TTL, type=int)
        if self.ttl not in (300, 900, 1800, 3600):
            self.ttl = DEFAULT_TTL
        self.hotkey_sequence = shortcuts['prices']
        self.hotkey_description = self.settings.value("hotkey-description", "")
        self.hotkey_status = ""
        self.hotkey_dialog_open = False
        self.hotkeys = HotkeyManager(self)
        self.hotkey_enabled = self.settings.value("hotkey-enabled", True, type=bool)
        self.hotkeys.activated.connect(self.on_hotkey)
        self.hotkeys.changed.connect(self.on_hotkey_changed)
        self.hotkeys.status.connect(self.on_hotkey_status)
        self.chat_enabled=self.settings.value("korean-chat",False,type=bool)
        self.chat=ChatTranslation(self.root,self)
        self.chat.configure(self.settings.value('chat-scan-seconds',4.0,type=float),self.settings.value('chat-linger-seconds',1.5,type=float))
        self.chat.changed.connect(self.on_chat_changed)
        self.chat.status.connect(self.on_chat_status)
        self.chat.frame_requested.connect(self.submit_chat_frame)
        self.chat_hotkeys=HotkeyManager(self)
        self.chat_hotkeys.activated.connect(self.translate_chat)
        self.chat_sequence=shortcuts['chat']
        self.exp_sequence=shortcuts['exp']
        self.exp_hotkey_description=self.settings.value("exp-hotkey-description",self.exp_sequence)
        self.exp_hotkeys=HotkeyManager(self)
        self.exp_hotkeys.activated.connect(self.on_exp_hotkey)
        self.exp_hotkeys.changed.connect(self.on_exp_hotkey_changed)
        self.exp_hotkeys.status.connect(self.on_hotkey_status)
        self.prices_enabled=True
        self.pending_exp_start=False
        self.hotkeys.action='toggle-prices'
        self.exp_hotkeys.action='toggle-exp'
        self.chat_hotkeys.action='translate-text'
        if self.hotkeys.portal:
            self.hotkeys.actions={
                'toggle-prices':{'key':self.hotkey_sequence,'description':'Pause or resume Lupin prices','activate':self.on_hotkey,'changed':self.on_hotkey_changed},
                'toggle-exp':{'key':self.exp_sequence,'description':'Start, pause or resume EXP tracking','activate':self.on_exp_hotkey,'changed':self.on_exp_hotkey_changed},
                'translate-text':{'key':self.chat_sequence,'description':'Translate Korean text in the Classic World window','activate':self.translate_chat,'changed':self.on_chat_hotkey_changed}}

        self.chat_hotkey_description=shortcut_label(self.chat_sequence)
        self.chat_hotkeys.changed.connect(self.on_chat_hotkey_changed)
        self.chat_hotkeys.status.connect(self.on_chat_status)
        self.composer=KoreanComposer(self.root,self)
        self.write_notice=OverlayNotice();self.write_pending_identity=None
        self.composer.copy_submitted.connect(self.on_translation_submitted)
        self.composer.changed.connect(self.on_writer_changed)
        self.composer.copied.connect(self.on_translation_copied)
        self.composer_dialog=None
        self.write_sequence=shortcuts['write']
        self.write_hotkey_description=self.settings.value('write-hotkey-description',self.write_sequence)
        self.write_hotkeys=HotkeyManager(self);self.write_hotkeys.action='compose-korean'
        self.write_activation_token=''
        self.write_hotkeys.activation_token.connect(self.on_write_activation_token)
        self.write_hotkeys.activated.connect(self.open_composer)
        self.write_hotkeys.changed.connect(self.on_write_hotkey_changed)
        self.write_hotkeys.status.connect(self.on_hotkey_status)
        if self.hotkeys.portal:
            # Portal callbacks run on its D-Bus thread. Emit Qt signals so every
            # feature action and description update arrives on the GUI thread.
            for identity,manager in [('toggle-prices',self.hotkeys),('toggle-exp',self.exp_hotkeys),('translate-text',self.chat_hotkeys)]:
                self.hotkeys.actions[identity]['activate']=manager.activated.emit
                self.hotkeys.actions[identity]['changed']=manager.changed.emit
            self.hotkeys.actions['compose-korean']={'key':self.write_sequence,'description':'Write English and copy a Korean translation',
                'activate':self.write_hotkeys.activated.emit,'changed':self.write_hotkeys.changed.emit,'token':self.write_hotkeys.activation_token.emit}
        self.hover_enabled = self.settings.value("tooltip-prices", True, type=bool)
        self.tooltip_result = None
        self.service = PriceService(cache_path, self)
        self.thumbnails=ThumbnailCache(Path(cache_path).parent/'item-thumbnails-v1',self)
        self.reference=ReferenceService(data_directory()/'reference-v1.sqlite',self)
        self.reference.changed.connect(self.update_database_settings)
        self.service.refresh_snapshot = True
        self.service.set_refresh_interval(self.ttl)
        self.reader = PixelReader(root, self)
        self.reader.exclude_regions=self.pickup_capture_exclusions
        self.reader.auto_enabled = self.auto_game_area
        self.reader.tooltip_enabled = self.hover_enabled and self.labels_enabled and self.prices_enabled
        self.reader.experience_enabled = self.exp_enabled
        self.overlay.pointer.connect(self.on_pointer)
        self.reader.reading.connect(self.on_reading)
        self.reader.status.connect(self.show_status)
        self.reader.image_ready.connect(self.on_image)
        self.reader.area_changed.connect(self.on_area_changed)
        self.reader.experience.connect(self.on_experience)
        self.service.catalog_ready.connect(self.on_catalog)
        self.service.quote_ready.connect(self.on_quote)
        self.service.error.connect(self.on_error)
        self.service.identity_ready.connect(self.on_identity)
        self.service.identity_error.connect(self.on_search_identity_error)
        self.service.state_changed.connect(self.on_price_state, Qt.ConnectionType.QueuedConnection)

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(16, 10, 16, 12)
        layout.setSpacing(10)
        heading = QHBoxLayout()
        self.brand = Brand(self.root,self)
        heading.addWidget(self.brand,1)
        heading.addStretch()
        self.shortcuts_button=QPushButton("Hotkeys…")
        self.shortcuts_button.setObjectName('ghost')
        self.shortcuts_button.clicked.connect(self.configure_shortcuts)
        self.settings_button = QPushButton("Settings")
        self.settings_button.setObjectName('ghost')
        self.settings_button.clicked.connect(self.open_settings)
        corner=QVBoxLayout();corner.setSpacing(4);corner.setContentsMargins(0,0,0,0)
        corner.addWidget(self.settings_button,0,Qt.AlignmentFlag.AlignRight)
        corner.addWidget(self.shortcuts_button,0,Qt.AlignmentFlag.AlignRight)
        corner.addStretch();heading.addLayout(corner)
        layout.addLayout(heading)
        layout.addWidget(label("Tools for MapleStory Classic World", "color: #a6b1bf; font-size: 11px", True))

        self.setup_frame = QFrame()
        self.setup_frame.setObjectName("setup")
        setup = QVBoxLayout(self.setup_frame)
        setup.setContentsMargins(12, 12, 12, 12)
        setup.setSpacing(8)
        self.status_badge = label("Choose a display", "color: #e4bd7b; font-weight: 650; font-size: 13px")
        self.status_badge.setWordWrap(True)
        self.status_badge.setMinimumHeight(36)
        capture_header = QHBoxLayout()
        capture_header.addWidget(self.status_badge,1)
        setup.addLayout(capture_header)
        self.setup_details = QWidget()
        setup_details = QVBoxLayout(self.setup_details)
        setup_details.setContentsMargins(0,4,0,0)
        setup_details.setSpacing(8)
        self.monitor = QComboBox()
        self.monitor.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.monitor.setMinimumContentsLength(12)
        self.monitor.setAccessibleName("Display containing Classic World")
        selected = self.settings.value("monitor-name", "")
        saved_screen_selected = False
        primary = QApplication.primaryScreen()
        self.screen_index = self.screens.index(primary) if primary in self.screens else 0 if self.screens else None
        for index, (screen, description) in enumerate(zip(self.screens, display_labels(self.screens))):
            self.monitor.addItem(description, index)
            self.monitor.setItemData(index, screen.name(), Qt.ItemDataRole.ToolTipRole)
            if selected and selected == screen.name():
                self.screen_index = index
                saved_screen_selected = True
        self.monitor.setCurrentIndex(self.screen_index if self.screen_index is not None else -1)
        self.monitor.setPlaceholderText("No displays available")
        self.monitor.currentIndexChanged.connect(self.set_screen)
        capture_header.addWidget(self.monitor,1)
        actions = QHBoxLayout()
        self.share = QPushButton("Start reading")
        self.share.setObjectName("captureToggle")
        self.share.clicked.connect(self.toggle_capture)
        actions.addWidget(self.share, 1)
        self.cancel_setup = QPushButton("Cancel setup")
        self.cancel_setup.clicked.connect(self.cancel_capture_setup)
        self.cancel_setup.setVisible(False)
        actions.addWidget(self.cancel_setup)
        setup.addLayout(actions)
        self.capture_info = label("Choose a display to enable Start reading.", "color: #bbc4cf; font-size: 11px", True)
        setup_details.addWidget(self.capture_info)
        self.recovery_button = QPushButton()
        self.recovery_button.setObjectName("quiet")
        self.recovery_button.clicked.connect(self.recover)
        self.recovery_button.setVisible(False)
        setup_details.addWidget(self.recovery_button, 0, Qt.AlignmentFlag.AlignLeft)
        setup.addWidget(self.setup_details)
        layout.addWidget(self.setup_frame)

        self.summary = label("", "font-size: 12px; color: #dde1e7", True)
        self.summary.setFixedHeight(20)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.cards = QWidget()
        self.cards_stack=QVBoxLayout(self.cards)
        self.cards_stack.setContentsMargins(0,0,0,0);self.cards_stack.setSpacing(0)
        self.card_area=CardArea(self.cards)
        card_content=QVBoxLayout(self.card_area.content);card_content.setContentsMargins(0,0,0,0);card_content.setSpacing(8)
        card_content.addWidget(self.summary)
        self.card_list=QWidget(self.card_area.content);card_content.addWidget(self.card_list)
        self.cards_layout = QVBoxLayout(self.card_list)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(10)
        self.cards_stack.addWidget(self.card_area)
        self.recent_items=RecentItems(self.cards)
        self.cards_stack.addWidget(self.recent_items)
        self.cards_stack.addStretch()
        self.scroll.setWidget(self.cards)
        self.exp_panel = ExperiencePanel(data_directory()/"exp-sessions.sqlite",parent=self)
        self.exp_panel.enabled_changed.connect(self.set_exp_enabled)
        self.exp_panel.changed.connect(self.on_experience_changed)
        self.exp_panel.overlay_changed.connect(self.set_exp_overlay)
        self.exp_panel.meso_overlay_changed.connect(self.set_meso_overlay)
        self.exp_panel.overlay_check.blockSignals(True)
        self.exp_panel.overlay_check.setChecked(self.exp_overlay)
        self.exp_panel.overlay_check.blockSignals(False)
        self.exp_panel.meso_overlay_check.blockSignals(True)
        self.exp_panel.meso_overlay_check.setChecked(self.meso_overlay)
        self.exp_panel.meso_overlay_check.blockSignals(False)
        self.tabs = AnimatedTabs()
        self.prices_page = QWidget()
        prices_layout = QVBoxLayout(self.prices_page)
        prices_layout.setContentsMargins(0,0,0,0)
        prices_layout.setSpacing(8)
        self.card_views = {}
        self.tabs.addTab(self.prices_page, "Prices")
        self.search_panel = PriceSearch(self,inline_detail=False)
        self.recent_items.chosen.connect(self.search_panel.select_recent)
        self.recent_items.changed.connect(self.update_shop_thumbnails)
        self.recent_items.clear_button.clicked.connect(self.render)
        self.search_panel.set_watchlist(self.watchlist)
        self.watchlist.changed.connect(self.on_watchlist_changed)
        self.search_panel.ttl = self.ttl
        self.search_panel.item_selected.connect(self.on_search_item)
        self.search_panel.identity_selected.connect(self.on_search_identity)
        self.search_panel.source_requested.connect(self.open_source)
        self.search_panel.set_thumbnails(self.thumbnails)
        self.thumbnails.ready.connect(self.on_shop_thumbnail)
        self.search_panel.catalog_retry.connect(self.retry_catalog)
        self.prices_layout=prices_layout
        prices_layout.addWidget(self.search_panel)
        self.price_content=ContentArea()
        self.price_content_layout=QVBoxLayout(self.price_content)
        self.price_content_layout.setContentsMargins(0,0,0,0)
        self.price_content_layout.setSpacing(8)
        self.price_content_layout.addWidget(self.search_panel.detail_scroll,1)
        self.search_panel.detail_scroll.hide()
        self.onscreen_button=QPushButton("On-screen items")
        self.onscreen_button.setCheckable(True);self.onscreen_button.toggled.connect(self.update_price_layout)
        self.price_content_layout.addWidget(self.onscreen_button)
        self.price_content_layout.addWidget(self.scroll,1)
        prices_layout.addWidget(self.price_content,1)
        self.search_panel.detail_changing.connect(self.price_content.begin)
        self.search_panel.active_changed.connect(self.update_price_layout)
        self.search_panel.watched_items.visible_changed.connect(self.update_price_layout)
        self.search_tab_index=0
        self.exp_scroll = QScrollArea()
        self.exp_scroll.setWidgetResizable(True)
        self.exp_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.exp_scroll.setWidget(self.exp_panel)
        self.exp_tab_index = self.tabs.addTab(self.exp_scroll, "EXP/Meso Tracking")
        self.translation_panel=TranslationPanel(self.chat_enabled,self,composer=self.composer,
            compose_shortcut=self.write_hotkey_description,configure_compose=self.configure_write_hotkey,
            scan_seconds=self.chat.scan_seconds,linger_seconds=self.chat.linger_seconds)
        self.translation_panel.timing_changed.connect(self.set_chat_timing)
        self.translation_panel.enabled_changed.connect(self.set_chat_enabled)
        self.translation_panel.translate_requested.connect(self.translate_chat)
        self.translation_panel.clear_requested.connect(self.chat.clear)
        self.chat_check=self.translation_panel.enabled_check
        self.chat_status_label=self.translation_panel.status_label
        self.translation_tab_index=self.tabs.addTab(self.translation_panel,"Translation")
        self.database_panel=DatabasePanel(self.reference,data_directory()/'reference-images-v1',self)
        self.database_panel.set_watchlist(self.watchlist)
        self.database_panel.set_market(self.service,self.ttl)
        self.database_panel.source_requested.connect(self.open_source)
        self.database_panel.return_requested.connect(lambda:self.tabs.setCurrentIndex(self.search_tab_index))
        self.database_tab_index=self.tabs.addTab(self.database_panel,'Database')
        self.reference_catalog_signature=None
        self.search_panel.set_reference(self.reference,self.database_panel.media,self.service)
        self.search_panel.reference_requested.connect(self.open_reference_entry)
        self.search_panel.reference_changed.connect(self.update_reference_context)
        self.database_panel.external_demand=self.search_panel.reference_demand
        self.reference.updated.connect(self.on_reference_data)
        self.tabs.currentChanged.connect(self.on_tab_changed)
        layout.addWidget(self.tabs, 1)
        self.shortcut_footer = label('', 'color:#a6b1bf;font-size:11px')
        self.shortcut_footer.setMinimumHeight(24)
        self.shortcut_footer.setAccessibleName('Current tab keyboard shortcut')
        layout.addWidget(self.shortcut_footer)
        self.translation_panel.modes.currentChanged.connect(self.update_shortcut_footer)
        self.update_shortcut_footer()
        self.notice = label("");self.notice.hide()
        prices_layout.addWidget(self.notice)
        self.status_label = label("", "color: #939eac; font-size: 10px", True)
        self.status_label.setVisible(False)
        self.setCentralWidget(body)
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #171c25; color: #dce1e8; font-family: 'INTERFACE_FONT'; font-size: 12px; }
            QLabel { background: transparent; }
            QPushButton { background:#252e3d;border:1px solid #3a475b;border-radius:7px;padding:7px 12px;min-height:16px;font-weight:500; }
            QComboBox, QKeySequenceEdit { background: #252d3b; border: 1px solid #354052; border-radius: 6px; padding: 7px 9px; }
            QPushButton:hover { background: #323c4c; border-color: #927b58; }
            QPushButton:pressed { background: #404655; }
            QPushButton:disabled { background: #202630; border-color: #2c333e; color: #727c8b; }
            QPushButton#primary { background: #d9ad66; color: #231e16; border-color: #d9ad66; font-weight: 650; }
            QPushButton#primary:hover { background: #ebc483; }
            QPushButton#primary:disabled { background: #2b303a; color: #828b97; border-color: #39414e; }
            QPushButton#captureToggle { background: #d9ad66; color: #231e16; border-color: #d9ad66; font-weight:650; }
            QPushButton#captureToggle:hover { background: #ebc483; }
            QPushButton#captureToggle:disabled { background:#2b303a; color:#828b97; border-color:#39414e; }
            QPushButton#quiet { background: transparent; border: 0; color: #b1bac7; padding: 5px 2px; text-align: left; }
            QPushButton#quiet:hover { color: #ebc483; }
            QPushButton#ghost { background:transparent;border-color:transparent;color:#b4c0d0;padding:5px 8px; }
            QPushButton#ghost:hover { background:#273244;border-color:#3c4a60;color:#edcf9e; }
            QCheckBox { color: #b5bfcc; padding: 3px 0; }
            QCheckBox:hover, QCheckBox:checked { color:#f0deb9; }
            QCheckBox::indicator { width:16px;height:16px;border:1px solid #687991;border-radius:4px;background:#1b2534; }
            QCheckBox::indicator:hover { border-color:#e2b66d;background:#303748; }
            QCheckBox::indicator:checked { background:#d9ad66;border-color:#f0ca8d;image:url(CHECK_ICON); }
            QCheckBox::indicator:checked:hover { background:#edc482; }
            QCheckBox::indicator:disabled { background:#242c37;border-color:#3e4856; }
            QCheckBox::indicator:checked:disabled { background:#746447;border-color:#9b8358; }
            QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }
            QFrame#card, QFrame#setup { background: #202734; border: 1px solid #303b4b; border-radius: 9px; }
            QFrame#card QLabel, QFrame#setup QLabel, QWidget#displayMap { background: transparent; border: none; }
            QScrollBar:vertical { background: #171c25; width: 6px; }
            QScrollBar::handle:vertical { background: #455064; border-radius: 3px; min-height: 20px; }
            QTabWidget::pane { border: 0; padding-top: 6px; }
            QTabBar::tab { background: transparent; color: #96a4b8; border: 0; border-radius: 6px; padding: 8px 18px; margin: 0 4px 3px 0; }
            QTabWidget::tab-bar { alignment: center; }
            QTabBar::tab:selected { background: #303d51; color: #f1e1c6; }
            QTabBar::tab:hover:!selected { background: #222d3d; color: #dce4ef; }
        """)
        self.setStyleSheet(self.styleSheet().replace('INTERFACE_FONT',interface_family()).replace('CHECK_ICON',str(Path(__file__).parent/'resources/check.svg').replace('\\','/')))
        self.exp_panel.set_display(self.exp_display)
        self.overlay.reduce_motion = self.reduce_motion
        self.build_settings()
        self.tray = TrayController(self)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self.service.start()
        self.reference.start()
        if snapshot:
            QTimer.singleShot(300, lambda: self.load_screenshot(snapshot))
        elif (auto_capture or kde_capture) and saved_screen_selected and self.screen_index is not None:
            QTimer.singleShot(500, self.start_kde if kde_capture else self.start_capture)
        self.render()
        QApplication.instance().screenAdded.connect(self.refresh_monitors)
        QApplication.instance().screenRemoved.connect(self.refresh_monitors)
        self.watch_display_geometry()
        if QApplication.platformName() != "offscreen":
            QTimer.singleShot(700, self.initialize_hotkey)
        if self.chat_enabled:
            QTimer.singleShot(800,lambda:self.set_chat_enabled(True))

    def build_settings(self):
        self.settings_dialog = QDialog(self)
        self.settings_dialog.setWindowTitle("Settings")
        self.settings_dialog.setMinimumSize(430, 300)
        height = max(300, min(720, QApplication.primaryScreen().availableGeometry().height()-64))
        self.settings_dialog.resize(480, height)
        outer = QVBoxLayout(self.settings_dialog)
        settings_scroll = QScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setFrameShape(QFrame.Shape.NoFrame)
        contents = QWidget()
        layout = QVBoxLayout(contents)
        settings_scroll.setWidget(contents)
        outer.addWidget(settings_scroll)
        layout.setSpacing(10)
        layout.addWidget(label("Overlay", "font-size: 15px; font-weight: 650"))
        self.auto_area_check = QCheckBox("Automatically find the Classic World area")
        self.auto_area_check.setChecked(self.auto_game_area)
        self.auto_area_check.setToolTip("Finds visible Classic UI in the shared pixels. A manually selected area takes priority until reset.")
        self.auto_area_check.toggled.connect(self.set_auto_area)
        layout.addWidget(self.auto_area_check)
        self.labels_check = QCheckBox("Show market prices beside items")
        self.labels_check.setChecked(self.labels_enabled)
        self.labels_check.toggled.connect(self.set_labels)
        layout.addWidget(self.labels_check)
        self.hover_check = QCheckBox("Show inventory and equipment prices")
        self.hover_check.setToolTip("Hover an inventory or equipped item, including while a shop is open. Shop listings use their own price labels.")
        self.hover_check.setChecked(self.hover_enabled)
        self.hover_check.setEnabled(self.labels_enabled)
        self.hover_check.toggled.connect(self.set_hover)
        layout.addWidget(self.hover_check)
        self.exp_overlay_check = QCheckBox("Show EXP overlay at the bottom left of the game")
        self.exp_overlay_check.setChecked(self.exp_overlay)
        self.exp_overlay_check.toggled.connect(self.set_exp_overlay)
        layout.addWidget(self.exp_overlay_check)
        self.meso_overlay_check=QCheckBox('Show meso overlay at the bottom left of the game')
        self.meso_overlay_check.setChecked(self.meso_overlay)
        self.meso_overlay_check.toggled.connect(self.set_meso_overlay)
        layout.addWidget(self.meso_overlay_check)
        layout.addWidget(label("EXP rate display", "font-size: 12px; color: #a6b1bf"))
        self.exp_display_combo = QComboBox()
        for value,title in (("percent","Percentage (default)"),("raw","Raw EXP"),("both","Both · percentage first")):
            self.exp_display_combo.addItem(title,value)
        self.exp_display_combo.setCurrentIndex(self.exp_display_combo.findData(self.exp_display))
        self.exp_display_combo.currentIndexChanged.connect(lambda *_:self.set_exp_display(self.exp_display_combo.currentData()))
        layout.addWidget(self.exp_display_combo)
        self.motion_check = QCheckBox("Reduce motion")
        self.motion_check.setChecked(self.reduce_motion)
        self.motion_check.toggled.connect(self.set_reduce_motion)
        layout.addWidget(self.motion_check)
        self.tray_check = QCheckBox("Minimize to the system tray")
        self.tray_check.setChecked(self.minimize_to_tray)
        self.tray_check.toggled.connect(self.set_minimize_to_tray)
        layout.addWidget(self.tray_check)
        self.hotkey_button = QPushButton("Hotkeys…")
        self.hotkey_button.clicked.connect(self.configure_shortcuts)
        layout.addWidget(self.hotkey_button)
        translation_settings=QPushButton("Translation settings…")
        def open_translation():
            self.settings_dialog.close();self.tabs.setCurrentIndex(self.translation_tab_index)
        translation_settings.clicked.connect(open_translation);layout.addWidget(translation_settings)
        layout.addWidget(label("Downloads the full market on launch, then at the interval below. Its system web view closes after each update. Saved references remain available if an update fails.", "font-size: 11px; color: #a6b1bf", True))
        layout.addWidget(label("Refresh all prices every", "font-size: 13px; font-weight: 650"))
        self.ttl_combo = QComboBox()
        for minutes in (5, 15, 30, 60):
            self.ttl_combo.addItem(f"{minutes} minutes" + (" · recommended" if minutes == 15 else ""), minutes * 60)
        self.ttl_combo.setCurrentIndex((300, 900, 1800, 3600).index(self.ttl))
        self.ttl_combo.currentIndexChanged.connect(lambda index: self.set_ttl(self.ttl_combo.itemData(index)))
        layout.addWidget(self.ttl_combo)
        layout.addWidget(label("One shared update supplies the overlay, search and watched items. No individual price lookups. Expired references lose their deal colors until fresh data arrives.", "font-size: 11px; color: #a6b1bf", True))
        layout.addWidget(label('Database','font-size:15px;font-weight:650'))
        self.database_update_button=QPushButton('Check for database updates')
        self.database_update_button.clicked.connect(lambda:self.reference.start())
        layout.addWidget(self.database_update_button)
        self.database_update_status=label('', 'font-size:11px;color:#a6b1bf',True)
        layout.addWidget(self.database_update_status)
        layout.addWidget(label('Checks for changes and downloads only changed reference files. Saved data stays available offline.','font-size:11px;color:#a6b1bf',True))
        self.update_database_settings()
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
        layout.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.settings_dialog.reject)
        outer.addWidget(buttons)

    def open_settings(self):
        self.update_capture_controls()
        self.update_database_settings()
        self.settings_dialog.exec()

    def update_database_settings(self):
        if not hasattr(self,'database_update_button'):return
        reference=self.reference;state=reference.store.metadata();stamp=state.get('checked_at')
        self.database_update_button.setEnabled(not reference.busy)
        if reference.busy:message='Checking for updates…'
        elif reference.error:message='Update check unavailable · saved data kept'
        elif stamp:
            from datetime import datetime
            message=('Database updated' if reference.core_changed else 'Reference data is up to date')+' · checked '+datetime.fromtimestamp(stamp).strftime('%b %d, %H:%M')
        else:message='Not checked yet'
        if reference.availability_error or reference.drop_error:message+=' · some source indexes unavailable'
        self.database_update_status.setText(message)

    def configure_shortcuts(self,focus='prices'):
        if focus not in ('prices','exp','chat','write'):focus='prices'
        if self.hotkeys.portal:
            self.hotkey_enabled=True;self.settings.setValue('hotkey-enabled',True)
            self.initialize_hotkey();self.hotkeys.configure();return
        from .shortcut_ui import edit_shortcuts
        edit_shortcuts(self,focus)

    def update_price_layout(self,*_):
        if not hasattr(self,"onscreen_button"):return
        watching=self.search_panel.watched_items.expanded
        detail=bool(self.search_panel.selected or self.search_panel.pending_identity)
        active=bool(self.search_panel.query.text().strip() or detail or self.search_panel.watch_focus)
        show=not active or self.onscreen_button.isChecked()
        if not self.rows and not detail and not self.search_panel.query.text().strip():show=True
        content_key=(detail,show)
        if content_key!=getattr(self,'price_content_key',None):
            if self.price_content.before is None:self.price_content.begin()
            self.price_content_key=content_key
        self.onscreen_button.setVisible(active and bool(self.rows))
        self.onscreen_button.setText(f"On-screen items · {len(self.rows)}"+ (" ▾" if self.onscreen_button.isChecked() else " ▸"))
        self.search_panel.detail_scroll.setVisible(detail)
        self.scroll.setVisible(show)
        self.scroll.setMaximumHeight(220 if detail else 16777215)
        self.summary.setVisible(bool(self.summary.text()))
        self.price_content_layout.setStretch(self.price_content_layout.indexOf(self.search_panel.detail_scroll),1 if detail else 0)
        self.price_content_layout.setStretch(self.price_content_layout.indexOf(self.scroll),0 if detail else 1)
        self.price_content.complete()
        self.update_shop_thumbnails()
        if watching:self.update_watched_quotes()

    def update_watched_quotes(self):
        section=self.search_panel.watched_items
        if not self.catalog:return
        for identity in section.visible_ids():
            item=next((item for item in self.catalog.items if item.game_id==identity),None)
            quote=self.service.cached(item) if item else None
            section.set_quote(identity,quote,time.time(),self.ttl)

    def update_shop_thumbnails(self):
        if not hasattr(self,'card_views'):return
        items=[]
        if self.tabs.currentIndex()==0 and not self.scroll.isHidden() and self.catalog:
            for card in self.card_views.values():
                identity=card.property('gameItemId')
                if identity:
                    item=next((item for item in self.catalog.items if item.game_id==identity),None)
                    if item:items.append(item)
            recent=self.recent_items.visible_items()
            # Cached images do not emit a download-completed signal. Hydrate
            # new history rows immediately, then observe any missing images.
            for item in recent:self.recent_items.set_image(item.game_id,self.thumbnails.image(item.game_id))
            items+=recent
        self.search_panel.set_screen_items(items)

    def on_shop_thumbnail(self,identity):
        image=self.thumbnails.image(identity)
        self.recent_items.set_image(identity,image)
        for card in self.card_views.values():
            if card.property('gameItemId')==identity:card.thumbnail.set_image(image)

    def on_chat_changed(self):
        if self.closing:return
        if hasattr(self,"translation_panel"):
            self.translation_panel.set_cards(self.chat.history)
            self.translation_panel.set_active(self.chat.active)
        self.draw_labels(time.time(),time.time()-self.last_screen>3)

    def on_chat_hotkey_changed(self,description):
        description=shortcut_label(description)
        self.chat_hotkey_description=description
        self.settings.setValue("chat-hotkey-description",description)
        self.update_shortcut_footer()

    def on_exp_hotkey_changed(self,description):
        description=shortcut_label(description)
        self.exp_hotkey_description=description;self.settings.setValue('exp-hotkey-description',description)
        self.update_shortcut_footer()

    def toggle_prices(self):
        if self.mode!='live':
            self.prices_enabled=True;self.reader.prices_enabled=True;self.toggle_capture();return
        self.prices_enabled=not self.prices_enabled
        self.reader.prices_enabled=self.prices_enabled
        self.reader.image_sequence+=1
        if not self.prices_enabled:self.service.clear_visible()
        self.render()

    def on_exp_hotkey(self):
        if self.hotkey_dialog_open:return
        if self.mode!='live':
            self.pending_exp_start=True
            if self.screen_index is not None:self.toggle_capture()
            else:
                self.tabs.setCurrentIndex(self.exp_tab_index)
                if hasattr(self,'tray'):self.tray.restore()
            return
        self.exp_panel.set_connected(time.time()-self.last_screen<3 and
                                    (not self.reader.auto_active or self.reader.game_area is not None))
        if not self.exp_panel.connected:
            self.pending_exp_start=True;return
        if self.exp_panel.requested:self.exp_panel.toggle_pause()
        else:self.exp_panel.start()

    def configure_write_hotkey(self):self.configure_shortcuts('write')

    def on_write_hotkey_changed(self,description):
        description=shortcut_label(description)
        self.write_hotkey_description=description;self.settings.setValue('write-hotkey-description',description)
        if hasattr(self,'translation_panel') and hasattr(self.translation_panel,'writer'):self.translation_panel.writer.set_shortcut(description)
        if self.composer_dialog:self.composer_dialog.editor.set_shortcut(description)
        self.update_shortcut_footer()

    def open_composer(self):
        if self.hotkey_dialog_open:return
        import os
        token=self.write_activation_token;self.write_activation_token=''
        if token and QApplication.platformName().startswith('wayland'):
            # Qt's own Wayland activation code consumes this token. It applies
            # only to our popup; no other window is inspected or activated.
            os.environ['XDG_ACTIVATION_TOKEN']=token
        if self.composer_dialog is None:
            self.composer_dialog=ComposerDialog(self.composer,self.write_hotkey_description,self.configure_write_hotkey)
            self.composer_dialog.setStyleSheet(self.styleSheet())
        dialog=self.composer_dialog
        if not dialog.isVisible():
            screen=QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
            area=screen.availableGeometry();dialog.move(area.center()-dialog.rect().center())
        dialog.show();dialog.raise_();dialog.activateWindow()
        dialog.editor.input.setFocus(Qt.FocusReason.ShortcutFocusReason)
        if token:
            def clear_token():
                if os.environ.get('XDG_ACTIVATION_TOKEN')==token:os.environ.pop('XDG_ACTIVATION_TOKEN',None)
            QTimer.singleShot(0,clear_token)

    def on_write_activation_token(self,token):
        if isinstance(token,str) and 0<len(token)<4096 and '\x00' not in token:self.write_activation_token=token

    def on_translation_copied(self,*_):
        if self.closing:return
        self.write_pending_identity=None
        self.write_notice.show('Translation copied to clipboard','Paste with Ctrl+V')
        self.draw_labels(time.time(),time.time()-self.last_screen>3)
        QTimer.singleShot(2600,lambda:self.draw_labels(time.time(),time.time()-self.last_screen>3) if not self.closing else None)
        if hasattr(self,'tray') and (self.mode!='live' or self.reader.game_area is None):self.tray.translation_copied()

    def on_translation_submitted(self,identity):
        self.write_pending_identity=identity
        self.write_notice.show('Translating to Korean…','The result will be copied to your clipboard.',seconds=65)
        self.draw_labels(time.time(),time.time()-self.last_screen>3)

    def on_writer_changed(self):
        if self.closing or self.write_pending_identity is None:return
        composer=self.composer
        if composer.identity!=self.write_pending_identity:
            self.write_pending_identity=None;self.write_notice.message=None
        elif composer.error:
            self.write_pending_identity=None
            self.write_notice.show('Translation could not be copied','Open the Korean writer to review the message.',seconds=4,warning=True)
        else:return
        self.draw_labels(time.time(),time.time()-self.last_screen>3)

    def on_chat_status(self,message):
        if hasattr(self,"translation_panel"):self.translation_panel.set_status(message)

    def set_chat_timing(self,scan,linger):
        self.chat.configure(scan,linger)
        self.settings.setValue('chat-scan-seconds',self.chat.scan_seconds)
        self.settings.setValue('chat-linger-seconds',self.chat.linger_seconds)

    def set_chat_enabled(self,enabled):
        self.chat_enabled=enabled;self.settings.setValue("korean-chat",enabled)
        self.chat.enable(enabled)
        if not enabled:
            self.on_chat_status("Disabled · local models unloaded")


    def translate_chat(self,*_):
        if self.hotkey_dialog_open:return
        if self.mode!='live' or self.reader.image.isNull():
            self.chat.announce('Start reading and share a display first.');return
        if not self.chat_enabled:
            self.chat_check.setChecked(True)
        self.chat.start_scan()

    def submit_chat_frame(self):
        if not self.chat.active:return
        image=self.reader.image
        if self.mode!="live" or image.isNull() or time.monotonic()-self.reader.last_frame>1:
            self.chat.abort_scan("Start reading and share a display first. Translation needs a fresh game image.");return
        region=self.reader.game_area if self.reader.auto_active else self.reader.crop
        if region is None:
            self.chat.abort_scan("Keep the Classic World status bar visible, or limit the reading area in Settings.");return
        if self.screen_index is None:return
        geometry=self.screens[self.screen_index].geometry()
        dpr=self.screens[self.screen_index].devicePixelRatio()
        if abs(image.width()-geometry.width()*dpr)>2 or abs(image.height()-geometry.height()*dpr)>2:
            self.chat.abort_scan("Share the selected full display so translation cards can be positioned correctly.");return
        sx,sy=image.width()/geometry.width(),image.height()/geometry.height()
        exclude=[[round(x*sx),round(y*sy),round(w*sx),round(h*sy)] for x,y,w,h in getattr(self.overlay,'layout_boxes',[])]
        for owned in (self,self.composer_dialog):
            if owned is not None and owned.isVisible() and not owned.isMinimized():
                rect=owned.frameGeometry().translated(-geometry.x(),-geometry.y())
                exclude.append([round(rect.x()*sx),round(rect.y()*sy),round(rect.width()*sx),round(rect.height()*sy)])
        self.chat.request(image,region,exclude)

    def pickup_capture_exclusions(self):
        image=self.reader.image
        if self.screen_index is None or image.isNull():return []
        geometry=self.screens[self.screen_index].geometry()
        sx,sy=image.width()/geometry.width(),image.height()/geometry.height()
        regions=[QRect(round(x*sx),round(y*sy),round(w*sx),round(h*sy)) for x,y,w,h in getattr(self.overlay,'layout_boxes',[])]
        for owned in (self,self.composer_dialog):
            if owned is not None and owned.isVisible() and not owned.isMinimized():
                rect=owned.frameGeometry().translated(-geometry.x(),-geometry.y())
                regions.append(QRect(round(rect.x()*sx),round(rect.y()*sy),round(rect.width()*sx),round(rect.height()*sy)))
        offset=self.reader.crop.topLeft() if self.reader.crop else QPoint()
        for rect in (self.reader.shop_context,self.shop_tooltip_rect):
            if rect:regions.append(rect.translated(offset))
        return regions

    def set_exp_enabled(self, enabled):
        self.exp_enabled = enabled
        self.reader.experience_enabled = enabled
        self.reader.last_experience = 0
        self.render()

    def on_tab_changed(self, index):
        if hasattr(self,'database_panel'):self.database_panel.set_active(index==self.database_tab_index)
        self.update_reference_context()
        self.update_shortcut_footer()
        self.update_price_layout()
        if hasattr(self,"search_panel"):
            panel = self.search_panel
            self.service.set_manual(panel.selected if index == self.search_tab_index else None,self.ttl,
                                    identity=panel.pending_identity if index == self.search_tab_index else None,
                                    candidates=panel.pending_candidates)
        self.update_capture_controls()

    def update_shortcut_footer(self, *_):
        if not hasattr(self, 'shortcut_footer'):return
        index = self.tabs.currentIndex()
        if index == self.exp_tab_index:
            chord, action = self.exp_hotkey_description, 'Start / pause / resume tracking'
        elif index == self.translation_tab_index:
            writing = self.translation_panel.modes.currentIndex() == 1
            chord = self.write_hotkey_description if writing else self.chat_hotkey_description
            action = 'Open Korean writer' if writing else 'Scan Korean text'
        elif index == self.database_tab_index:
            chord,action='Ctrl+F','Search database'
        else:
            chord, action = self.hotkey_description or shortcut_label(self.hotkey_sequence), 'Pause / resume prices'
        self.shortcut_footer.setText(f'{shortcut_label(chord)}  ·  {action}')

    def open_reference_entry(self,key):
        self.tabs.setCurrentIndex(self.database_tab_index);self.database_panel.open_external(tuple(key))

    def update_reference_context(self):
        if not hasattr(self,'database_panel') or self.closing:return
        if self.tabs.currentIndex()==self.search_tab_index:
            entry=self.search_panel.reference_entry()
            self.reference.extra.select(entry);self.reference.sources.select(entry)
        self.database_panel.observe_media()

    def on_reference_data(self):
        if self.closing or not hasattr(self,'database_panel'):return
        self.reference.observe_market(self.catalog,getattr(self.service,'snapshot',None),notify=False)
        state=self.reference.store.metadata();count=self.reference.store.released_counts()['items']
        signature=(id(self.catalog),state.get('manifest'),count)
        if signature!=self.reference_catalog_signature:
            self.reference_catalog_signature=signature;catalog=self.reference.store.catalog(self.catalog)
            self.search_panel.set_catalog(catalog,preserve=True);self.database_panel.set_catalog(catalog)
        self.search_panel.refresh_reference();self.update_reference_context()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        window_size.remember(self)

    def on_search_item(self, item):
        if self.tabs.currentIndex() == self.search_tab_index:
            self.service.set_manual(item,self.ttl)
        if item and item.game_id in self.quotes:
            self.search_panel.accept_quote(item.game_id,self.quotes[item.game_id])

    def on_watchlist_changed(self):
        self.draw_labels(time.time(), time.time()-self.last_screen > 3)

    def on_search_identity(self, identity, candidates):
        if self.tabs.currentIndex() == self.search_tab_index:
            self.service.set_manual(None,self.ttl,identity=identity,candidates=candidates)

    def on_search_identity_error(self, identity, message):
        self.last_diagnostic = message
        self.search_panel.identity_error(identity,message)

    def set_exp_overlay(self, enabled):
        self.exp_overlay = enabled
        self.settings.setValue("exp-overlay", enabled)
        for widget in (self.exp_panel.overlay_check,getattr(self,'exp_overlay_check',None)):
            if widget is not None:
                widget.blockSignals(True);widget.setChecked(enabled);widget.blockSignals(False)
        self.render()

    def set_meso_overlay(self,enabled):
        self.meso_overlay=enabled;self.settings.setValue('meso-overlay',enabled)
        for widget in (self.exp_panel.meso_overlay_check,getattr(self,'meso_overlay_check',None)):
            if widget is not None:
                widget.blockSignals(True);widget.setChecked(enabled);widget.blockSignals(False)
        self.render()

    def on_experience(self, result):
        if self.mode == "live" and self.exp_enabled:
            self.exp_panel.set_connected(time.time()-self.last_screen<3 and
                                         (not self.reader.auto_active or self.reader.game_area is not None))
            self.exp_panel.feed(result)

    def on_experience_changed(self):
        self.draw_labels(time.time(), time.time()-self.last_screen > 3)

    def set_exp_display(self, mode):
        self.exp_display = mode
        self.settings.setValue("exp-display", mode)
        self.exp_panel.set_display(mode)
        self.render()

    def set_reduce_motion(self, reduced):
        self.reduce_motion = reduced
        self.settings.setValue("reduce-motion",reduced)
        QApplication.instance().setProperty("reduceMotion",reduced)
        self.overlay.reduce_motion = reduced
        self.brand.sync()
        self.database_panel.sync_motion()
        self.render()

    def set_minimize_to_tray(self, enabled):
        self.minimize_to_tray = enabled
        self.settings.setValue("minimize-to-tray", enabled)

    def set_auto_area(self, enabled):
        self.auto_game_area = enabled
        self.settings.setValue("auto-game-area", enabled)
        self.rows = []
        self.tooltip_result = None
        self.reader.set_auto_area(enabled)
        self.render()

    def on_area_changed(self):
        if self.reader.game_area is not None:self.last_identified_at=time.monotonic()
        if hasattr(self, "exp_panel"):
            self.exp_panel.interrupt_context()
            self.exp_panel.set_connected(False)
        if self.reader.auto_active and self.reader.game_area is None:
            self.rows = []
            self.tooltip_result = None
        elif self.pending_exp_start:
            self.pending_exp_start=False;self.exp_panel.set_connected(True);self.exp_panel.start()
        self.render()

    def changeEvent(self, event):
        super().changeEvent(event)
        if (event.type() == QEvent.Type.WindowStateChange and self.isMinimized()
                and hasattr(self, "tray")):
            self.tray.schedule_minimize()

    def nativeEvent(self, event_type, message):
        if is_maximize_message(message):
            return True, 0
        return super().nativeEvent(event_type, message)

    def set_labels(self, enabled):
        self.labels_enabled = enabled
        self.reader.tooltip_enabled = enabled and self.hover_enabled
        self.hover_check.setEnabled(enabled)
        self.settings.setValue("show-prices", enabled)
        self.render()

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
        updater=getattr(self.service,'snapshot_updater',None)
        failure=updater.fetcher.last_failure if updater else None
        if failure:
            stages=' · '.join(stage+' '+code for stage,code in failure['stages'])
            layout.addWidget(label(f"Last market failure: {failure['kind']} · exit {failure['exit_code']}"+
                                   ('\n'+stages if stages else ''),'font-size:10px;color:#98a3b1',True))
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
            if not self.hotkeys.portal:
                self.exp_hotkeys.start(self.exp_sequence);self.chat_hotkeys.start(self.chat_sequence);self.write_hotkeys.start(self.write_sequence)

    def on_hotkey(self):
        if not self.hotkey_dialog_open:
            self.toggle_prices()

    def on_hotkey_changed(self, description):
        description=shortcut_label(description)
        self.hotkey_description = description
        self.hotkey_status = ""
        self.settings.setValue("hotkey-description", description)
        self.hotkey_button.setToolTip("Pause / resume: " + description)
        self.update_shortcut_footer()

    def on_hotkey_status(self, message):
        self.hotkey_status = message
        self.hotkey_button.setToolTip(message)
        self.status_label.setText(message)

    def selected_display(self):
        if self.screen_index is None or self.screen_index >= len(self.screens):
            return "your display"
        return self.monitor.itemText(self.screen_index).split(" · ")[0]

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
            return ("No display available", "Connect a display to start reading.", "amber", "")
        display = self.selected_display()
        if self.capture_error:
            return ("Screen reading needs attention", self.capture_error, "amber", "Reconnect display")
        if self.capture_starting:
            if uses_system_picker():
                if self.session_available:return ('Resuming reading', 'Reusing the shared display.', 'blue', '')
                hint = f"In the system sharing dialog, select {display}. Full-workspace sharing also works."
                if time.monotonic() - self.starting_at > 10:
                    hint += " The dialog may be behind another window; finish it or cancel setup below."
                return ("Waiting for screen sharing", hint, "amber", "")
            return ("Starting screen reading", f"Connecting to {display}.", "amber", "")
        if self.mode == "paused":
            return ("Paused", "Labels are hidden and price lookups are paused. Resume reuses your sharing session." if self.session_available else "Labels are hidden. Resume will reconnect your display.", "muted", "")
        if self.mode == "live":
            if not self.last_screen or time.time() - self.last_screen > 8:
                return ("Waiting for a fresh screen", "The last screen is no longer current. References stay visible here, and overlay labels are hidden until reading resumes.", "amber", "Reconnect display")
            if not self.image_matches_screen():
                return ("Share the selected display", f"The shared image does not match {display}. Reconnect and choose that display, or share the full workspace, so labels can line up.", "amber", "Reconnect display")
            if self.reader.auto_active and self.reader.game_area is None:
                if time.monotonic()-self.last_identified_at<.6:
                    return ("Classic World identified", "Confirming game visibility…", "green", "")
                return ("Looking for Classic World", "Keep the bottom status bar visible and uncover the game window. The reading area follows it automatically. If needed, choose an area in Settings → Limit the reading area.", "amber", "")
            if not self.labels_enabled:
                return ("Reading · labels hidden", "Price labels are disabled. Item prices still appear in this panel; enable labels to show them beside the game.", "blue", "Show price labels")
            return ("Classic World identified" if self.reader.auto_active else "Reading selected area", "Game area located on " + display + ".", "green", "")
        instruction = (f"Click Start reading, then approve {display} in the system sharing dialog."
                       if uses_system_picker() else f"Click Start reading to read {display}.")
        return ("Ready to start", self.setup_notice or instruction, "blue", "")

    def show_status(self, message):
        self.last_diagnostic = message
        if message.startswith(("Screen sharing stopped", "OS capture:", "KDE screen capture failed", "Capture dimensions", "Invalid local capture")):
            self.capture_error = "Screen capture stopped or could not start. Check the selected display, then reconnect."
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
        self.setup_frame.setVisible(True)
        valid = self.screen_index is not None and 0 <= self.screen_index < len(self.screens)
        display_width = self.monitor.fontMetrics().horizontalAdvance(self.monitor.currentText())+46 if valid else 200
        if self.monitor.minimumWidth()!=display_width:self.monitor.setMinimumWidth(display_width)
        self.monitor.setToolTip(self.monitor.currentText())
        self.share.setEnabled(valid and not self.capture_starting)
        self.share.setText("Starting reading…" if self.capture_starting else "Pause reading" if self.mode == "live" else "Resume reading" if self.mode == "paused" and self.session_available else "Start reading")
        self.share.setToolTip("Choose a display first" if not valid else "Toggle screen reading")
        self.monitor.setEnabled(not self.capture_starting)
        self.monitor.setVisible(True)
        self.cancel_setup.setVisible(self.capture_starting)
        title, detail, tone, action = self.connection_state()
        self.status_badge.setText(title)
        self.status_badge.setToolTip(detail)
        self.status_badge.setStyleSheet(f"color: {COLORS[tone]}; font-weight: 650; font-size: 13px")
        self.capture_info.setText(detail)
        self.capture_info.setVisible(True)
        self.setup_details.setVisible(bool(self.capture_error or self.capture_starting and not self.session_available or action))
        self.recovery_button.setVisible(bool(action))
        self.recovery_button.setText(action)
        if hasattr(self, "crop_button"):
            self.crop_button.setEnabled(not self.reader.image.isNull() and self.mode in ("live", "screenshot") and not self.capture_starting)
        if hasattr(self, "kde_button"):
            self.kde_button.setEnabled(valid and not self.capture_starting)
        if hasattr(self, "tray"):
            self.tray.update()

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
        self.search_panel.catalog_error = ""
        self.search_panel.hint.setText("Getting item names…")
        self.search_panel.retry_button.hide()
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
        self.settings.setValue("monitor-name", self.screens[self.screen_index].name())
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

    def watch_display_geometry(self):
        previous = getattr(self, "geometry_screens", [])
        for screen in self.screens:
            if screen not in previous:screen.geometryChanged.connect(self.refresh_monitors)
        self.geometry_screens = list(self.screens)

    def refresh_monitors(self, *args):
        previously_selected = self.screen_index is not None and 0 <= self.screen_index < len(self.screens)
        selected_name = self.settings.value("monitor-name", "")
        if previously_selected:
            try:selected_name = self.screens[self.screen_index].name()
            except RuntimeError:pass
        was_live = self.mode == "live"
        self.screens = sorted(QApplication.screens(), key=lambda screen: (screen.geometry().x(), screen.geometry().y()))
        self.watch_display_geometry()
        self.monitor.blockSignals(True)
        self.monitor.clear()
        chosen = None
        for index, (screen, description) in enumerate(zip(self.screens, display_labels(self.screens))):
            self.monitor.addItem(description, index)
            self.monitor.setItemData(index, screen.name(), Qt.ItemDataRole.ToolTipRole)
            if screen.name() == selected_name and (previously_selected or selected_name):
                chosen = index
        lost_selection = previously_selected and chosen is None
        if chosen is None:
            primary = QApplication.primaryScreen()
            chosen = self.screens.index(primary) if primary in self.screens else 0 if self.screens else None
        self.monitor.setCurrentIndex(chosen if chosen is not None else -1)
        self.monitor.blockSignals(False)
        self.screen_index = chosen
        if (lost_selection or chosen is None) and self.mode in ("live", "paused"):
            self.reader.pause(keep_stream=False)
            self.mode = "idle"
            self.capture_starting = self.session_available = False
            self.rows = []
            self.tooltip_result = None
            self.setup_notice = "The previous display disconnected. Check the selected display, then click Start reading."
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
        self.exp_panel.set_connected(False)
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
        if not self.labels_enabled or self.mode != "live" or image.isNull() or not geometry.contains(QPoint(x, y)):
            self.reader.pointer = None
            if self.tooltip_result:
                self.tooltip_result = None
                self.render()
            return
        point = (round((x - geometry.x()) * image.width() / geometry.width()),
                 round((y - geometry.y()) * image.height() / geometry.height()))
        if point != self.reader.pointer:
            previous = self.reader.pointer
            context_point = (point[0] - self.reader.crop.x(), point[1] - self.reader.crop.y()) if self.reader.crop else point
            outside = (self.reader.auto_active and
                       (self.reader.game_area is None or not self.reader.game_area.contains(QPoint(*point))))
            jumped = previous is not None and max(abs(point[0] - previous[0]), abs(point[1] - previous[1])) > 64
            clear = outside or (jumped and not (self.tooltip_result or {}).get('pinned')) or pointer_in_shop(context_point, self.reader.shop_context)
            had_tooltip = bool(self.tooltip_result and clear)
            if clear:
                self.tooltip_result = None
            self.reader.pointer = point
            self.reader.image_sequence += 1
            if had_tooltip:
                self.request_prices()
                self.render()

    def on_image(self, image):
        if self.mode not in ("live", "screenshot"):
            return
        was_starting = self.capture_starting
        self.capture_starting = False
        self.session_available = self.mode == "live"
        self.capture_error = ""
        self.last_screen = time.time() - max(0, time.monotonic() - self.reader.last_frame)
        if self.shop_tooltip_rect is not None:
            pixels=image.copy(self.reader.crop) if self.reader.crop else image
            if not still_present(pixels,self.shop_tooltip_rect,self.annotation_exclusions()):
                self.shop_tooltip_rect=None
                # The market identities remain verified. Un-dim those cards
                # immediately; listing amounts still wait for a fresh read.
                self.rows=[{**row,'covered':False} for row in self.rows]
                self.rows=self.shop_rows.restore_visible(pixels,self.rows)
                self.render()
        if self.chat.has_overlay:self.draw_labels(time.time(),False)
        self.update_capture_controls()
        if was_starting:
            self.render()

    def on_reading(self, result):
        if self.mode not in ("live", "screenshot"):
            return
        self.ocr_ms = result.get("atMs")
        shop = result.get("shop")
        image = getattr(self.reader,"submitted_image",self.reader.image)
        if self.reader.crop:image = image.copy(self.reader.crop)
        tooltip=result.get('tooltip')
        tooltip=tooltip if isinstance(tooltip,dict) else {}
        hover=result.get('hover')
        hover=hover if isinstance(hover,dict) else {}
        shop_tooltip=hover.get('tooltip')
        shop_tooltip=shop_tooltip if isinstance(shop_tooltip,dict) else {}
        exclusions=self.annotation_exclusions()
        native = (shop_tooltip or {}).get('found') or ((tooltip or {}).get('found') if shop or self.shop_open else None)
        bounds=description_bounds(image,native.get('area'),exclusions) if native else None
        latest=self.reader.image.copy(self.reader.crop) if self.reader.crop else self.reader.image
        if bounds is not None and not still_present(latest,bounds,exclusions):bounds=None
        if bounds is None and self.shop_open and self.shop_tooltip_rect is not None and still_present(latest,self.shop_tooltip_rect,exclusions):
            bounds=self.shop_tooltip_rect
        if bounds is not None and self.shop_tooltip_rect is not None:
            if all(abs(a-b)<=3 for a,b in zip(bounds.getRect(),self.shop_tooltip_rect.getRect())):
                bounds=self.shop_tooltip_rect
        bounds_changed=bounds!=self.shop_tooltip_rect
        self.shop_tooltip_rect=bounds
        rows = self.shop_rows.observe(shop,image,tooltip=bounds,exclude=exclusions)
        if bounds is None:rows=self.shop_rows.restore_visible(latest,rows)
        self.shop_open = self.shop_rows.active
        found = tooltip.get("found") if isinstance(tooltip, dict) else None
        read_pointer = result.get("pointerAtRead", self.reader.pointer)
        pointer = self.reader.pointer
        if pointer and self.reader.crop:
            pointer = (pointer[0] - self.reader.crop.x(), pointer[1] - self.reader.crop.y())
        eligible = self.hover_enabled and pointer is not None and not result.get("hover") and not pointer_in_shop(pointer, self.reader.shop_context)
        raw_found=found
        found = found if eligible else None
        if found:
            found = self.tooltip_names.resolve(found,image,self.catalog)
            name = found.get("name")
            area = found.get("area") or {}
            read_point = read_pointer
            if read_point is not None and self.reader.crop:
                read_point = (read_point[0] - self.reader.crop.x(), read_point[1] - self.reader.crop.y())
            try:
                box = QRect(int(area["x"]), int(area["y"]), int(area["width"]), int(area["height"]))
                # This is the name line, not the whole tooltip. Tall tooltips
                # can place it well above the pointer near the screen's edge.
                near = read_point is not None and box.adjusted(-640, -640, 640, 640).contains(QPoint(*read_point))
                popup=description_bounds(image,area,exclusions) if found.get('pinned') else None
                pinned=bool(popup and still_present(latest,popup,exclusions))
                moved = read_point is None or max(abs(pointer[0] - read_point[0]), abs(pointer[1] - read_point[1])) > 64
                known = bool(name and (self.catalog is None or self.catalog.candidates(name, found.get("tier"))))
                if not known and near and not moved and not result.get('tooltipRetried') and hasattr(self.reader,'retry_tooltip'):
                    self.reader.retry_tooltip(name_key(found,image))
                if not (known and box.width() >= 40 and box.height() >= 8
                        and (pinned or near and not found.get('pinned')) and (pinned or not moved)):
                    found = None
                else:
                    found = {**found, "_pointer": list(read_pointer)}
            except (KeyError, TypeError, ValueError):
                found = None
        found=self.tooltip_reference.observe(found,image,pointer,allow=eligible and (not raw_found or not raw_found.get('name') or found is not None))
        changed = bounds_changed or rows != self.rows or found != self.tooltip_result
        self.tooltip_result = found
        self.rows = rows
        self.request_prices()
        self.update_price_status()
        if changed:
            self.render()

    def annotation_exclusions(self):
        if self.screen_index is None or self.reader.image.isNull():return []
        geometry=self.screens[self.screen_index].geometry()
        sx,sy=self.reader.image.width()/geometry.width(),self.reader.image.height()/geometry.height()
        ox,oy=(self.reader.crop.x(),self.reader.crop.y()) if self.reader.crop else (0,0)
        return [QRect(round(x*sx)-ox,round(y*sy)-oy,round(w*sx),round(h*sy)) for x,y,w,h in getattr(self.overlay,'layout_boxes',[])]

    def on_identity(self, identity, item):
        self.search_panel.accept_identity(identity,item)
        if self.catalog:
            self.catalog.bind_current(identity[0], identity[1], item)
            self.request_prices()
            self.render()

    def on_catalog(self, catalog):
        self.catalog = catalog
        self.catalog_loading = False
        self.catalog_error = ""
        self.on_reference_data()
        self.composer.set_names(catalog.items)
        if catalog.warning:
            self.last_diagnostic = catalog.warning
        self.request_prices()
        self.render()

    def shop_identity(self,row):
        item=self.catalog.resolve(row.get('name'),row.get('tier')) if self.catalog else None
        return item.game_id if item else None

    def prices_active(self):
        return bool(self.prices_enabled and self.catalog and self.mode in ("live", "screenshot")
                    and (self.mode != "live" or self.last_screen and time.time() - self.last_screen <= 8)
                    and (not self.reader.auto_active or self.reader.game_area is not None))

    def request_prices(self):
        if not self.prices_active():
            self.service.clear_visible()
            return
        observations = ([self.tooltip_result] if self.tooltip_result else []) + self.rows
        items, identities = [], []
        hovered_id = hovered_identity = None
        pointer = self.reader.pointer
        if pointer and self.reader.crop:
            pointer = (pointer[0] - self.reader.crop.x(), pointer[1] - self.reader.crop.y())
        for row in observations:
            if not row.get('name'):
                continue
            area = row.get("area") or {}
            hovered = row is self.tooltip_result or bool(pointer and area and
                      QRect(area["x"], area["y"], area["width"], area["height"]).contains(QPoint(*pointer)))
            item = self.catalog.resolve(row.get("name"), row.get("tier"))
            if item:
                items.append(item)
                if hovered:
                    hovered_id = item.game_id
            else:
                candidates = self.catalog.candidates(row.get("name"), row.get("tier"))
                if len(candidates) > 1:
                    identity = (row.get("name"), row.get("tier"))
                    identities.append((identity, candidates))
                    if hovered:
                        hovered_identity = identity
        self.service.observe(items, self.ttl, hovered_id=hovered_id,
                             identities=identities, hovered_identity=hovered_identity)

    def on_price_state(self):
        if not self.closing:
            self.reference.observe_market(self.catalog,getattr(self.service,'snapshot',None))
            self.database_panel.update_market()
            snapshot=getattr(self.service,'snapshot',None)
            generation=(snapshot.meta or {}).get('checked_at') if snapshot else None
            if self.catalog and generation is not None and generation!=self.quote_generation:
                self.quote_generation=generation
                selected=self.search_panel.selected
                identities=set(self.quotes)
                if selected:identities.add(selected.game_id)
                for item in self.catalog.items:
                    if item.game_id not in identities:continue
                    quote=self.service.reference(item)
                    self.quotes[item.game_id]=quote
                    self.search_panel.accept_quote(item.game_id,quote)
            item = self.search_panel.selected
            self.search_panel.set_state(self.service.state_for(item.game_id) if item else "")
            self.update_price_status()
            self.render()

    def on_quote(self, item_id, quote):
        self.quotes[item_id] = quote
        self.errors.pop(item_id, None)
        self.search_panel.accept_quote(item_id,quote)
        self.database_panel.update_market()
        self.update_price_status()
        self.render()

    def on_error(self, item_id, message):
        self.errors[item_id] = message
        self.last_diagnostic = message
        self.search_panel.accept_error(item_id,message)
        if not item_id:
            retrying = getattr(self.service, "catalog_retrying", False)
            self.catalog_loading = retrying
            self.catalog_error = "" if retrying else catalog_error_text(message)
            self.search_panel.show_catalog_error(message, retrying=retrying)
        self.update_price_status()
        self.render()

    def update_price_status(self):
        if not self.catalog:
            return
        observations = self.rows + ([self.tooltip_result] if self.tooltip_result else [])
        failed = any((item := self.catalog.resolve(row.get("name"), row.get("tier")))
                     and item.game_id in self.errors for row in observations)
        snapshot = self.service.snapshot_summary() if hasattr(self.service, "snapshot_summary") else ""
        updater=getattr(self.service,'snapshot_updater',None)
        self.search_panel.set_market_status(snapshot if updater and (updater.busy or updater.error) else '',bool(updater and updater.error))
        self.status_label.setText("Some market references are unavailable; cached prices are kept." if failed else snapshot or "Market references cached locally")

    def tick(self):
        self.update_price_status()
        self.exp_panel.set_connected(self.mode == "live" and time.time()-self.last_screen < 3
                                     and (not self.reader.auto_active or self.reader.game_area is not None))
        self.render()
        if self.tabs.currentIndex() == self.search_tab_index:
            self.search_panel.render()
        if self.mode in ("live", "screenshot") or self.tabs.currentIndex() == self.search_tab_index:
            self.request_prices()

    def set_ttl(self, value):
        self.ttl = value
        self.settings.setValue("cache-ttl", value)
        self.search_panel.ttl = value
        self.database_panel.ttl=value;self.database_panel.update_market()
        self.service.set_refresh_interval(value)
        if self.tabs.currentIndex() == self.search_tab_index:
            panel = self.search_panel
            self.service.set_manual(panel.selected,value,identity=panel.pending_identity,candidates=panel.pending_candidates)
        self.request_prices()
        self.render()

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
        if not self.prices_enabled:
            title,detail='Prices paused',f'Press {self.hotkey_description or self.hotkey_sequence} to resume prices.'
        elif self.mode == "idle":
            title = "Let's find your first price" if not self.first_price_seen else "Ready when you are"
            detail = "Choose a display above, then click Start reading. You can also search for an item above without screen sharing."
        elif self.mode == "paused":
            title, detail = "Reading is paused", "Resume to show price labels again."
        elif self.capture_starting:
            title, detail = (("Finish screen sharing", "Use the OS chooser to share the selected display or the full workspace.")
                             if uses_system_picker() else ("Connecting to the display", "Waiting for the first image…"))
        elif self.catalog_error:
            title, detail = "Item names are unavailable", self.catalog_error
        elif self.catalog_loading:
            title, detail = "Getting item names ready", "The first launch downloads the Classic World item list. Saved item names are reused on later launches."
        elif self.mode == "live" and self.reader.auto_active and self.reader.game_area is None:
            title, detail = "Waiting for the game area", "Keep the bottom status bar visible. The minimap can be moved or closed. You can also select an area under Settings → Limit the reading area."
        elif self.mode == "screenshot":
            title, detail = "No items found in this image", "Use a clear screenshot with full item names and visible prices. Live reading is available from Start reading above."
        elif self.shop_open and not self.rows:
            title,detail="Shop detected · no listings","Open a populated shop or hover an inventory item to see market prices."
        else:
            title, detail = "Ready to price an item", "Open a Classic World player shop, or hover over an item in inventory / equipment. Keep its name and shop price visible."
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
        if not self.prices_active():
            self.service.clear_visible()
        self.update_capture_controls()
        now = time.time()
        screen_old = not self.last_screen or now - self.last_screen > 8
        observations = self.rows + ([self.tooltip_result] if self.tooltip_result else [])
        card_rows=self.card_sightings.observe(self.rows,self.tooltip_result,
            retain=self.mode=='live' and not screen_old and self.prices_enabled,
            context=(self.screen_index,self.reader.crop.getRect() if self.reader.crop else None),
            page=self.shop_rows.page_revision)
        displayed=[row for row,_ in card_rows]
        active={item.game_id for row in displayed if self.catalog and (item:=self.catalog.resolve(row.get('name'),row.get('tier')))}
        if self.catalog:
            if self.mode in ('live','screenshot') and not screen_old and self.prices_enabled:self.recent_items.observe(observations,self.catalog,now,active=active)
            else:self.recent_items.active=active
            self.recent_items.refresh(self.service,self.ttl,now)
        structure=tuple((hovered,item.game_id if self.catalog and (item:=self.catalog.resolve(row.get('name'),row.get('tier'))) else row.get('name'))
                        for row,hovered in card_rows)
        if not structure:
            structure=('empty',self.mode,self.shop_open,self.capture_starting,self.catalog_error,self.catalog_loading,self.reader.game_area is not None,bool(self.recent_items.rows_by_id))
        previous=getattr(self,'screen_card_structure',None)
        structure_changed=previous!=structure
        if structure_changed:self.card_area.begin()
        self.screen_card_structure=structure
        ready = 0
        if self.catalog:
            for row in displayed:
                item = self.catalog.resolve(row.get("name"), row.get("tier"))
                quote = self.quote_for(item)
                if quote and quote.price is not None and quote.fresh(now, self.ttl):
                    ready += 1
        count = len(displayed)
        if count:
            self.summary.setText(("Last read: " if self.mode == "paused" else "") + f"{count} item{'s' if count != 1 else ''} · {ready} market reference{'s' if ready != 1 else ''} ready")
        else:
            self.summary.clear()
        self.summary.setVisible(bool(self.summary.text()))
        # Keep the UI small at rest. Rebuild only when content/state changes or
        # the five-second age bucket changes; screen frames never rebuild cards.
        visible=[]
        for row,hovered in card_rows:
            item=self.catalog.resolve(row.get('name'),row.get('tier')) if self.catalog else None
            quote=self.quote_for(item);price=row.get('price') or {}
            visible.append((hovered,item.game_id if item else row.get('name'),row.get('tier'),
                            price.get('quantity'),price.get('mesos'),quote,
                            bool(item and item.game_id in self.errors),
                            quote.cache_valid(now,self.ttl) if quote else False,
                            quote.fresh(now,self.ttl) if quote else False,
                            age_text(now-quote.observed_at) if quote and quote.observed_at is not None else '',
                            self.service.state_for(item.game_id) if item else ''))
        card_key = (tuple(visible),
                    self.mode, self.shop_open, screen_old, self.capture_starting, self.catalog_loading,
                    self.catalog_error, id(self.catalog), self.ttl,self.prices_enabled,bool(self.recent_items.rows_by_id),self.reader.game_area is not None)
        if card_key != getattr(self, "card_key", None):
            self.card_key = card_key
            position = self.scroll.verticalScrollBar().value()
            used = set()
            ordered = []
            if structure_changed:self.card_area.setProperty('suppressMotion',True)
            if not displayed and not self.recent_items.rows_by_id:
                key = ("empty",self.mode,self.shop_open,self.capture_starting,self.catalog_error,self.catalog_loading,
                       self.reader.game_area is not None)
                used.add(key)
                if key not in self.card_views:self.card_views[key]=self.empty_card()
                ordered.append(self.card_views[key])
                self.card_views[key].show()
            desired=[];occurrences={}
            for row,hovered in card_rows:
                item=self.catalog.resolve(row.get('name'),row.get('tier')) if self.catalog else None
                identity=(hovered,item.game_id if item else row.get('name'))
                occurrence=occurrences.get(identity,0);occurrences[identity]=occurrence+1
                desired.append((*identity,occurrence))
            replacements={key:card for key,card in self.card_views.items() if key not in desired and hasattr(card,'update_data')}
            occurrences={}
            for index, (row, hovered) in enumerate(card_rows):
                item = self.catalog.resolve(row.get("name"), row.get("tier")) if self.catalog else None
                quote = self.quote_for(item)
                identity=(hovered,item.game_id if item else row.get('name'))
                occurrence=occurrences.get(identity,0);occurrences[identity]=occurrence+1
                key=(*identity,occurrence)
                data = dict(item=item, row=row, quote=quote, now=now, ttl=self.ttl,
                                  paused=self.mode == "paused" or not self.prices_enabled, old_capture=self.mode == "live" and screen_old,
                                  lookup_error=bool(item and item.game_id in self.errors), hovered=hovered,
                                  context_name='Linked item' if hovered and row.get('pinned') else None,
                                  lookup_state=self.service.state_for(item.game_id) if item else "",
                                  open_source=self.open_source)
                used.add(key)
                if key in self.card_views:
                    card = self.card_views[key]
                    card.update_data(**data)
                else:
                    old_key=next((old_key for old_key in replacements if old_key[0] is hovered),None)
                    if old_key is not None:
                        card=replacements.pop(old_key);self.card_views.pop(old_key)
                        card.update_data(**data);self.card_views[key]=card
                    else:card = self.card_views[key] = price_card(watchlist=self.watchlist,**data)
                ordered.append(card)
                card.setProperty('gameItemId',item.game_id if item else None)
                card.thumbnail.setVisible(item is not None)
                if item:card.thumbnail.set_image(self.thumbnails.image(item.game_id))
                card.show()
            for key in list(self.card_views):
                if key not in used:
                    card = self.card_views.pop(key)
                    self.cards_layout.removeWidget(card)
                    card.hide();card.deleteLater()
            for index,card in enumerate(ordered):
                if self.cards_layout.indexOf(card)!=index:self.cards_layout.insertWidget(index,card)
            self.card_area.setProperty('suppressMotion',False)
            self.card_area.complete()
            self.scroll.verticalScrollBar().setValue(position)
        self.update_price_layout()
        self.draw_labels(now, screen_old)

    def draw_labels(self, now, screen_old):
        if self.screen_index is None:
            self.watch_encounters.apply([], self.watchlist.ids)
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
        game_visible = not self.reader.auto_active or self.reader.game_area is not None
        if self.prices_enabled and self.labels_enabled and self.mode == "live" and not screen_old and screen_matches and self.catalog and game_visible:
            sx, sy = geometry.width() / image.width(), geometry.height() / image.height()
            crop = self.reader.crop
            offset_x, offset_y = (crop.x(), crop.y()) if crop else (0, 0)
            for row in self.rows:
                if not row.get('name'):
                    continue
                area = row["area"]
                item = self.catalog.resolve(row.get("name"), row.get("tier"))
                quote = self.quote_for(item)
                state = self.service.state_for(item.game_id) if item else ""
                status = reference_status(quote, state, now, self.ttl)
                price = row.get("price") or {}
                verdict = compare(item, price.get("quantity"), price.get("mesos"), quote, now, self.ttl)
                compatible=bool(item and quote and quote.game_id==item.game_id and quote.world==WORLD
                    and quote.condition=='clean' and quote.per_set==item.per_set and quote.fresh(now,self.ttl))
                quote_key=(self.quote_generation,quote) if compatible else None
                presentation=self.shop_rows.presentation_for(row,quote_key=quote_key) if compatible else None
                presentation_held=bool(presentation and not row.get('price'))
                if presentation_held:
                    verdict=compare(item,presentation.get('quantity'),presentation.get('mesos'),quote,now,self.ttl)
                if quote and quote.price is not None and quote.fresh(now, self.ttl):
                    ready_price = True
                    suffix = "listing covered" if row.get("listing_old") and not presentation_held else "listing price unclear" if verdict.label == "Unreadable" else ""
                    text = f"FM {mesos(quote.price)} • {suffix} • {status}"
                    if not suffix:text = f"FM {mesos(quote.price)} • {status}"
                    if verdict.label == "Thin data":
                        text = f"FM {mesos(quote.price)} • few reports • {status}"
                elif quote and quote.price is None:
                    text = "FM • source has no market data"
                    if state in ("queued", "refreshing"):
                        text += " • " + state
                elif quote:
                    text = f"FM {mesos(quote.price)} • {status}"
                elif item:
                    text = "FM " + (status if state else "unavailable" if item.game_id in self.errors else "checking…")
                else:
                    text = "FM • checking item version" if item is None and row.get("name") else "FM • name unreadable"
                slot=row.get('shop_slot') or self.shop_rows.relative_slot(row)
                if slot is None:continue
                page=row.get('shop_page',self.shop_rows.page_revision)
                annotations.append({"x": round((area["x"] + area["width"] + offset_x) * sx) + 24,
                                    "y": round((area["y"] + offset_y + area["height"] / 2) * sy) - 12,
                                    "name": item.name if item else row.get("name") or "Unresolved item",
                                    "text": text, "color": COLORS[verdict.tone],
                                    "key": f"shop:{page}:{item.game_id if item else row.get('name')}:{tuple(slot)}",
                                    "shop_page":page,"shop_slot":list(slot),"presentation_held":presentation_held,
                                    "item_id": item.game_id if item else None,
                                    "content_id":[item.game_id if item else row.get('name'),quote.price if quote else None],
                                    "animate_move": True,"kind":"shop",
                                    "occlusion": ([round((self.shop_tooltip_rect.x()+offset_x)*sx),
                                                   round((self.shop_tooltip_rect.y()+offset_y)*sy),
                                                   round(self.shop_tooltip_rect.width()*sx),
                                                   round(self.shop_tooltip_rect.height()*sy)] if self.shop_tooltip_rect is not None else None),
                                    "deal_delta":f"{verdict.delta:+.0f}%" if verdict.delta is not None else ""})
        if self.prices_enabled and self.labels_enabled and self.hover_enabled and self.tooltip_result and self.mode == "live" and not screen_old and screen_matches and self.catalog and game_visible:
            found = self.tooltip_result
            area = found["area"]
            name = found.get("name")
            item = self.catalog.resolve(name, found.get('tier')) if name else None
            quote = self.quote_for(item)
            state = self.service.state_for(item.game_id) if item else ""
            status = reference_status(quote, state, now, self.ttl)
            sx, sy = geometry.width() / image.width(), geometry.height() / image.height()
            crop = self.reader.crop
            ox, oy = (crop.x(), crop.y()) if crop else (0, 0)
            if quote and quote.price is not None:
                fresh = quote.fresh(now, self.ttl)
                ready_price = ready_price or fresh
                text = f"FM {mesos(quote.price)} mesos • {status}"
                if fresh and quote.sample_count < 5:
                    text += " • few reports"
            else:
                text = "FM • source has no market data" if quote else "FM " + status
                if quote and state in ("queued", "refreshing"):
                    text += " • " + state
                fresh = False
            # Unreadable/unknown candidates are common on ordinary scenery.
            # Draw a hover reference only after identifying a catalog item.
            point = found.get("_pointer")
            if item and point is not None:
                region = self.reader.game_area if self.reader.auto_active else self.reader.crop or image.rect()
                annotations.append({"name": item.name, "key": item.game_id,
                                    "kind": "item", "item_id": item.game_id,
                                    "content_id":[item.game_id,quote.price if quote else None],
                                    "text": text, "color": COLORS["blue" if fresh else "muted"],
                                    "x": round((area["x"] + ox) * sx),
                                    "y": max(7, round((area["y"] + oy) * sy) - 40),
                                    "follow_pointer": [geometry.x() + round(point[0] * sx), geometry.y() + round(point[1] * sy)],
                                    "pointer_region": [geometry.x() + round(region.x() * sx), geometry.y() + round(region.y() * sy),
                                                       round(region.width() * sx), round(region.height() * sy)]})
                if found.get('pinned'):
                    annotations[-1].pop('follow_pointer');annotations[-1].pop('pointer_region')
                    annotations[-1]['bounds']=[round(region.x()*sx),round(region.y()*sy),
                                                round(region.width()*sx),round(region.height()*sy)]
        if self.exp_enabled and (self.exp_overlay or self.meso_overlay) and self.mode == "live" and game_visible and screen_matches and not screen_old:
            rows=[row for row in self.exp_panel.overlay_rows()
                  if self.exp_overlay and row['key']=='experience' or self.meso_overlay and row['key']=='meso-gain']
            area = self.reader.game_area if self.reader.auto_active else self.reader.crop
            if area:
                sx,sy=geometry.width()/image.width(),geometry.height()/image.height()
                bounds=[round(area.x()*sx),round(area.y()*sy),round(area.width()*sx),round(area.height()*sy)]
                guards=[rect for rect,_ in getattr(self.reader,'game_guards',[])]
                annotations=tracking_rows(rows,bounds,guards,scale_x=sx,scale_y=sy)+annotations
        if self.chat_enabled and self.mode=="live" and game_visible and screen_matches and not screen_old:
            area=self.reader.game_area if self.reader.auto_active else self.reader.crop
            if area:
                sx,sy=geometry.width()/image.width(),geometry.height()/image.height()
                bounds=[round(area.x()*sx),round(area.y()*sy),round(area.width()*sx),round(area.height()*sy)]
                # Shop and EXP references paint above a manually requested chat card.
                annotations=self.chat.annotations(image,sx,sy,bounds,occupied=annotations)+annotations
        if self.mode=='live' and game_visible and screen_matches and not screen_old:
            area=self.reader.game_area if self.reader.auto_active else self.reader.crop
            if area:
                sx,sy=geometry.width()/image.width(),geometry.height()/image.height()
                bounds=[round(area.x()*sx),round(area.y()*sy),round(area.width()*sx),round(area.height()*sy)]
                notice=self.write_notice.row(bounds)
                if notice:annotations.append(notice)
        self.watch_encounters.apply(annotations, self.watchlist.ids, page=self.shop_rows.page_revision)
        self.overlay.update(list(geometry.getRect()), annotations, hover_enabled=self.prices_enabled and self.labels_enabled and self.mode == "live" and game_visible and screen_matches and not screen_old)
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
        def reset():
            self.rows = []
            self.tooltip_result = None
            self.reader.set_crop(None)
            dialog.reject()
            self.render()
        buttons.button(QDialogButtonBox.StandardButton.Reset).clicked.connect(reset)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.rows = []
            self.tooltip_result = None
            self.reader.set_crop(canvas.selection())
            self.render()

    def about(self):
        QMessageBox.information(self, APP_NAME, "Reads OS-shared pixels and draws this independent window.\n\nNo game hooks, memory, files, messages, input or packet access. Screenshots remain local. Only item names/IDs go to public price sources.\n\nOCR: Minerva (MIT), pinned at 7e1aa7d. OCR model: ocrs, CC BY-SA 4.0. Catalog: OSMS Data Explorer. Prices: MesoWatch Classic World full-market snapshot.\n\n24h median with at least 5 samples, otherwise the site's longer window. These are reported prices, not guaranteed trades. Equipment is assumed unscrolled, as requested. Its actual stats are not assessed.\n\nThe full market refreshes on launch and at the selected interval through a short-lived system web view, then closes that helper. No browser installation is required. Individual price lookups are not used. Expired data has no deal rating; latest reports over 24h old also have no rating.\n\nPrices and requests are cached locally. No telemetry or screenshot uploads.")

    def closeEvent(self, event):
        if self.closing:
            event.accept()
            return
        self.closing = True
        window_size.save(self, self.settings)
        self.timer.stop()
        self.exp_panel.close_session()
        self.hotkeys.close()
        self.exp_hotkeys.close()
        self.chat_hotkeys.close()
        self.write_hotkeys.close()
        if self.composer_dialog:self.composer_dialog.close();self.composer_dialog.deleteLater()
        self.composer.close()
        self.chat.close()
        self.reader.close(keep_stream=self.keep_capture)
        self.service.close()
        self.thumbnails.close()
        self.reference.close();self.database_panel.close()
        self.overlay.close()
        if hasattr(self, "tray"):
            self.tray.close()
        event.accept()
        self.closed.emit()
