"""Exercise real UI context rules with fake pixel/input data and no OS capture."""
import os
from pathlib import Path
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QRect, QTimer, Signal
from PySide6.QtGui import QImage, QKeySequence
from PySide6.QtWidgets import QApplication, QDialog, QKeySequenceEdit, QPushButton

from price_lens.domain import Catalog
from price_lens.ui import LensWindow


class FakeOverlay(QObject):
    pointer = Signal(int, int)

    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.rows = []

    def update(self, geometry, rows, hover_enabled=False):
        self.rows = rows

    def close(self):
        pass


class FakeReader(QObject):
    reading = Signal(dict)
    status = Signal(str)
    image_ready = Signal(QImage)

    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.image = QImage(800, 800, QImage.Format.Format_RGBA8888)
        self.crop = None
        self.pointer = (340, 240)
        self.shop_context = QRect(300, 200, 240, 300)
        self.latest_latency_ms = 30
        self.image_sequence = 0
        self.last_frame = time.monotonic()
        self.starts = 0
        self.pauses = []

    def start(self, *args):
        self.starts += 1

    def pause(self, keep_stream=False):
        self.pauses.append(keep_stream)

    def close(self, keep_stream=False):
        pass


class FakeService(QObject):
    catalog_ready = Signal(object)
    quote_ready = Signal(int, object)
    error = Signal(int, str)
    identity_ready = Signal(object, object)

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.requests = []

    def start(self):
        pass

    def request(self, item, ttl):
        self.requests.append(item.game_id)

    def close(self):
        pass


class FakeSettings:
    def __init__(self, *args):
        self.values = {}

    def value(self, key, default, type=None):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value


class FakeHotkeys(QObject):
    activated = Signal()
    changed = Signal(str)
    status = Signal(str)
    portal = False

    def start(self, text):
        self.changed.emit(text)
        return True

    def close(self):
        pass


class ContextUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.patchers = [patch("price_lens.ui." + name, replacement) for name, replacement in
                         [("Overlay", FakeOverlay), ("PixelReader", FakeReader),
                          ("PriceService", FakeService), ("QSettings", FakeSettings), ("HotkeyManager", FakeHotkeys)]]
        for patcher in self.patchers:
            patcher.start()
        self.window = LensWindow(Path.cwd(), Path("unused-cache"))
        self.window.monitor.setCurrentIndex(1)
        self.window.catalog = Catalog({"items": [{"id": 1, "name": "Example Hat"}], "scrolls": []})
        self.window.mode = "live"
        self.window.last_screen = time.time()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        for patcher in reversed(self.patchers):
            patcher.stop()

    def reading(self, shop_hover):
        return {"atMs": 123, "shop": {"area": {"x": 300, "y": 200, "width": 240, "height": 300},
                "rows": [{"name": "Example Hat", "price": {"quantity": 1, "mesos": 100},
                          "area": {"x": 340, "y": 220, "width": 180, "height": 40}}]},
                "hover": {"pointer": {"x": 340, "y": 240}} if shop_hover else None,
                "tooltip": {"found": {"name": "Example Hat", "area": {"x": 100, "y": 100, "width": 180, "height": 20}}}}

    def test_hover_is_on_by_default_and_the_import_button_is_gone(self):
        self.assertTrue(self.window.hover_check.isChecked())
        self.assertTrue(self.window.reader.tooltip_enabled)
        self.assertFalse(any("Import MesoWatch" in button.text() for button in self.window.findChildren(QPushButton)))

    def test_store_hover_never_draws_a_duplicate_inventory_label(self):
        self.window.on_reading(self.reading(shop_hover=True))
        self.assertIsNone(self.window.tooltip_result)
        self.assertEqual(len(self.window.overlay.rows), 1)

    def test_inventory_hover_outside_store_list_can_show_its_price(self):
        self.window.reader.pointer = (100, 100)
        self.window.on_reading(self.reading(shop_hover=False))
        self.assertEqual(self.window.tooltip_result["name"], "Example Hat")
        self.assertEqual(len(self.window.overlay.rows), 2)

    def test_disabling_setting_stops_tooltip_processing_and_clears_label(self):
        self.window.reader.pointer = (100, 100)
        self.window.on_reading(self.reading(shop_hover=False))
        self.window.set_hover(False)
        self.assertIsNone(self.window.tooltip_result)
        self.assertFalse(self.window.reader.tooltip_enabled)
        self.assertFalse(self.window.settings.values["tooltip-prices"])

    def test_error_for_a_previous_store_is_not_left_on_the_status_line(self):
        self.window.status_label.setText("Price lookup: old item: HTTP Error 400")
        self.window.errors[999] = "HTTP Error 400"
        self.window.on_reading(self.reading(shop_hover=True))
        self.assertNotIn("400", self.window.status_label.text())

    def test_one_button_covers_monitor_selection_start_pause_and_resume(self):
        fresh = LensWindow(Path.cwd(), Path("unused-cache"))
        try:
            self.assertIsNone(fresh.screen_index)
            self.assertFalse(fresh.share.isEnabled())
            self.assertFalse(fresh.crop_button.isEnabled())
            fresh.toggle_capture()
            self.assertEqual(fresh.reader.starts, 0)
            fresh.monitor.setCurrentIndex(1)
            self.assertTrue(fresh.share.isEnabled())
            self.assertEqual(fresh.share.text(), "Start")
            fresh.share.click()
            self.assertEqual(fresh.reader.starts, 1)
            self.assertFalse(fresh.share.isEnabled())
            self.assertEqual(fresh.share.text(), "Starting…")
            fresh.reader.image = QImage(800, 800, QImage.Format.Format_RGBA8888)
            fresh.on_image(fresh.reader.image)
            self.assertTrue(fresh.share.isEnabled())
            self.assertEqual(fresh.share.text(), "Pause")
            fresh.share.click()
            self.assertEqual(fresh.mode, "paused")
            self.assertEqual(fresh.share.text(), "Resume")
            self.assertEqual(fresh.reader.pauses, [True])
            self.assertEqual(fresh.overlay.rows, [])
            fresh.share.click()
            self.assertEqual(fresh.reader.starts, 2)
        finally:
            fresh.close()
            fresh.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_hotkey_and_button_share_the_same_toggle(self):
        self.window.hotkeys.activated.emit()
        self.assertEqual(self.window.mode, "paused")
        self.assertEqual(self.window.share.text(), "Resume")
        self.window.hotkeys.activated.emit()
        self.assertEqual(self.window.mode, "live")
        self.assertEqual(self.window.reader.starts, 1)

    def test_pause_ignores_pending_readings_and_does_not_refresh_prices(self):
        self.window.on_reading(self.reading(shop_hover=True))
        count = len(self.window.service.requests)
        self.window.pause()
        self.window.on_reading(self.reading(shop_hover=False))
        self.window.tick()
        self.assertIsNone(self.window.tooltip_result)
        self.assertEqual(len(self.window.service.requests), count)
        self.assertFalse(self.window.overlay.rows)

    def test_key_combination_is_configurable_and_saved(self):
        def edit():
            dialog = self.window.findChild(QDialog)
            editor = dialog.findChild(QKeySequenceEdit)
            editor.setKeySequence(QKeySequence("Ctrl+Shift+F10"))
            next(button for button in dialog.findChildren(QPushButton) if button.text() == "Set hotkey").click()
            dialog.reject()
        QTimer.singleShot(0, edit)
        self.window.configure_hotkey()
        self.assertEqual(self.window.settings.values["hotkey-sequence"], "Ctrl+Shift+F10")
        self.assertTrue(self.window.settings.values["hotkey-enabled"])
