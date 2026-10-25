"""Exercise real UI context rules with fake pixel/input data and no OS capture."""
import os
from pathlib import Path
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QObject, QRect, Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QPushButton

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

    def close(self, keep_stream=False):
        pass


class FakeService(QObject):
    catalog_ready = Signal(object)
    quote_ready = Signal(int, object)
    error = Signal(int, str)
    identity_ready = Signal(object, object)

    def __init__(self, path, parent=None):
        super().__init__(parent)

    def start(self):
        pass

    def request(self, item, ttl):
        pass

    def close(self):
        pass


class FakeSettings:
    def __init__(self, *args):
        self.values = {}

    def value(self, key, default, type=None):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value


class ContextUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.patchers = [patch("price_lens.ui." + name, replacement) for name, replacement in
                         [("Overlay", FakeOverlay), ("PixelReader", FakeReader),
                          ("PriceService", FakeService), ("QSettings", FakeSettings)]]
        for patcher in self.patchers:
            patcher.start()
        self.window = LensWindow(Path.cwd(), Path("unused-cache"))
        self.window.catalog = Catalog({"items": [{"id": 1, "name": "Example Hat"}], "scrolls": []})
        self.window.mode = "live"
        self.window.last_screen = time.time()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
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
