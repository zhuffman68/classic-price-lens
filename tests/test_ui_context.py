"""Exercise real UI context rules with fake pixel/input data and no OS capture."""
import os
from dataclasses import replace
from pathlib import Path
import time
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QImage, QKeySequence, QMouseEvent
from PySide6.QtWidgets import QApplication, QDialog, QKeySequenceEdit, QLabel, QPushButton

from price_lens.domain import Catalog, Quote
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
    area_changed = Signal()
    experience = Signal(dict)

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
        self.auto_active = True
        self.game_area = QRect(0, 0, 800, 800)

    def set_auto_area(self, enabled):
        self.auto_active = enabled

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
    state_changed = Signal()

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.requests = []
        self.catalog_starts = 0
        self.visible = []
        self.hovered_id = None
        self.states = {}

    def start(self):
        self.catalog_starts += 1

    def request(self, item, ttl):
        self.requests.append(item.game_id)

    def observe(self, items, ttl, *, hovered_id=None, identities=(), hovered_identity=None):
        self.visible = [item.game_id for item in items]
        self.hovered_id = hovered_id
        self.requests.extend(self.visible)

    def clear_visible(self):
        self.visible = []

    def state_for(self, item_id):
        return self.states.get(item_id, "")

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
        self.exp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.exp_directory.cleanup)
        self.patchers = [patch("price_lens.ui." + name, replacement) for name, replacement in
                         [("Overlay", FakeOverlay), ("PixelReader", FakeReader),
                          ("PriceService", FakeService), ("QSettings", FakeSettings), ("HotkeyManager", FakeHotkeys),
                          ("data_directory", lambda: Path(self.exp_directory.name))]]
        for patcher in self.patchers:
            patcher.start()
        self.tray_show = patch("price_lens.tray.QSystemTrayIcon.show")
        self.tray_show.start()
        self.window = LensWindow(Path.cwd(), Path("unused-cache"))
        self.window.monitor.setCurrentIndex(1)
        self.window.on_catalog(Catalog({"items": [{"id": 1, "name": "Example Hat"}], "scrolls": []}))
        self.window.mode = "live"
        self.window.last_screen = time.time()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.tray_show.stop()

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

    def test_automatic_game_area_is_enabled_by_default(self):
        self.assertTrue(self.window.auto_area_check.isChecked())
        self.assertTrue(self.window.reader.auto_enabled)

    def test_lost_game_area_hides_labels_and_stops_price_requests(self):
        self.window.on_reading(self.reading(shop_hover=True))
        count=len(self.window.service.requests)
        self.window.reader.game_area=None
        self.window.reader.area_changed.emit()
        self.assertEqual(self.window.rows,[])
        self.assertEqual(self.window.overlay.rows,[])
        self.assertEqual(self.window.status_badge.text(),"Looking for Classic World")
        self.window.on_reading(self.reading(shop_hover=True))
        self.window.tick()
        self.assertEqual(len(self.window.service.requests),count)
        self.assertEqual(self.window.overlay.rows,[])

    def test_auto_area_toggle_is_saved_without_restarting_capture(self):
        self.window.auto_area_check.setChecked(False)
        self.assertFalse(self.window.settings.values["auto-game-area"])
        self.assertFalse(self.window.reader.auto_active)
        self.assertEqual(self.window.reader.starts,0)

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

    def test_empty_or_unknown_tooltip_candidates_never_draw_floating_prices(self):
        self.window.reader.pointer = (100, 100)
        for name in (None, "", "Random scenery OCR"):
            with self.subTest(name=name):
                reading = self.reading(shop_hover=False)
                reading["tooltip"]["found"]["name"] = name
                self.window.on_reading(reading)
                self.assertIsNone(self.window.tooltip_result)
                self.assertEqual(len(self.window.overlay.rows), 1)

    def test_tooltip_without_pointer_or_far_from_it_is_ignored(self):
        self.window.reader.pointer = None
        self.window.on_reading(self.reading(shop_hover=False))
        self.assertIsNone(self.window.tooltip_result)
        self.window.reader.pointer = (1500, 1500)
        self.window.on_reading(self.reading(shop_hover=False))
        self.assertIsNone(self.window.tooltip_result)

    def test_tall_tooltip_name_above_pointer_is_valid(self):
        self.window.reader.pointer = (100, 600)
        self.window.on_reading(self.reading(shop_hover=False))
        self.assertEqual(self.window.tooltip_result["name"], "Example Hat")
        self.assertEqual(len(self.window.overlay.rows), 2)

    def test_named_bandana_and_greater_scroll_use_the_actual_item_name(self):
        self.window.on_catalog(Catalog({"items": [{"id": 1002013, "name": "Blue Bandana", "category": "Equipment"}],
                                       "scrolls": [{"id": 2040002, "name": "Hat Accuracy Scroll: Greater", "tier": "Greater"}]}))
        self.window.reader.pointer = (100, 650)
        for name, expected in [("Blue Bandana", "Blue Bandana"),
                               ("Hat Accuracy Scroll:Greater", "Hat Accuracy Scroll: Greater")]:
            with self.subTest(name=name):
                reading = self.reading(shop_hover=False)
                reading["tooltip"]["found"]["name"] = name
                self.window.on_reading(reading)
                self.assertEqual(self.window.overlay.rows[-1]["name"], expected)

    def test_native_shop_stats_popup_temporarily_hides_market_labels(self):
        reading = self.reading(shop_hover=True)
        reading["hover"]["tooltip"] = {"found": reading["tooltip"]["found"]}
        self.window.on_reading(reading)
        self.assertTrue(self.window.shop_tooltip_active)
        self.assertEqual(self.window.overlay.rows, [])
        self.window.on_reading(self.reading(shop_hover=True))
        self.assertFalse(self.window.shop_tooltip_active)
        self.assertEqual(len(self.window.overlay.rows), 1)

    def test_covered_shop_rows_do_not_draw_unreadable_price_badges(self):
        reading = self.reading(shop_hover=True)
        reading["shop"]["rows"][0].update(name=None, price=None, covered=True)
        self.window.on_reading(reading)
        self.assertEqual(self.window.overlay.rows, [])

    def test_small_cursor_moves_keep_the_identified_price_and_card(self):
        self.window.reader.pointer = (100, 100)
        self.window.on_reading(self.reading(shop_hover=False))
        card = self.window.cards_layout.itemAt(0).widget()
        key = self.window.card_key
        self.window.on_pointer(108, 105)
        self.assertIsNotNone(self.window.tooltip_result)
        self.window.render()
        self.assertIs(self.window.cards_layout.itemAt(0).widget(), card)
        self.assertEqual(self.window.card_key, key)
        hover = self.window.overlay.rows[-1]
        self.assertEqual(hover["follow_pointer"], [100, 100])

    def test_reading_for_a_pointer_that_has_moved_away_is_rejected(self):
        self.window.reader.pointer = (700, 700)
        reading = self.reading(shop_hover=False)
        reading["pointerAtRead"] = [100, 100]
        self.window.on_reading(reading)
        self.assertIsNone(self.window.tooltip_result)

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
            self.assertEqual(fresh.share.text(), "Start reading")
            fresh.share.click()
            self.assertEqual(fresh.reader.starts, 1)
            self.assertFalse(fresh.share.isEnabled())
            self.assertEqual(fresh.share.text(), "Waiting for sharing…")
            fresh.reader.image = QImage(800, 800, QImage.Format.Format_RGBA8888)
            fresh.on_image(fresh.reader.image)
            self.assertTrue(fresh.share.isEnabled())
            self.assertEqual(fresh.share.text(), "Pause reading")
            fresh.share.click()
            self.assertEqual(fresh.mode, "paused")
            self.assertEqual(fresh.share.text(), "Resume reading")
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
        self.assertEqual(self.window.share.text(), "Resume reading")
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
            dialog = self.window.findChild(QDialog, "hotkeyDialog")
            editor = dialog.findChild(QKeySequenceEdit)
            editor.setKeySequence(QKeySequence("Ctrl+Shift+F10"))
            next(button for button in dialog.findChildren(QPushButton) if button.text() == "Set hotkey").click()
            dialog.reject()
        QTimer.singleShot(0, edit)
        self.window.configure_hotkey()
        self.assertEqual(self.window.settings.values["hotkey-sequence"], "Ctrl+Shift+F10")
        self.assertTrue(self.window.settings.values["hotkey-enabled"])

    def test_first_run_display_selection_waits_for_explicit_start(self):
        fresh = LensWindow(Path.cwd(), Path("unused-cache"), auto_capture=True)
        try:
            fresh.monitor.setCurrentIndex(1)
            self.app.processEvents()
            self.assertEqual(fresh.reader.starts, 0)
            self.assertEqual(fresh.mode, "idle")
            self.assertEqual(fresh.status_badge.text(), "Ready to start")
            self.assertIn("Click Start reading", fresh.capture_info.text())
            self.assertFalse(fresh.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        finally:
            fresh.close()
            fresh.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_sharing_setup_can_be_canceled_and_late_readings_are_ignored(self):
        self.window.mode = "idle"
        self.window.start_capture()
        self.assertEqual(self.window.status_badge.text(), "Waiting for screen sharing")
        self.assertFalse(self.window.cancel_setup.isHidden())
        self.window.cancel_setup.click()
        self.window.on_reading(self.reading(shop_hover=True))
        self.assertEqual(self.window.mode, "idle")
        self.assertEqual(self.window.rows, [])
        self.assertEqual(self.window.reader.pauses[-1], False)
        self.assertIn("canceled", self.window.capture_info.text())

    def test_lost_sharing_waits_for_explicit_reconnect(self):
        self.window.show_status("OS capture: user stopped sharing")
        self.assertEqual(self.window.reader.starts, 0)
        self.assertEqual(self.window.status_badge.text(), "Sharing needs attention")
        self.assertFalse(self.window.recovery_button.isHidden())
        self.window.recovery_button.click()
        self.assertEqual(self.window.reader.starts, 1)

    def test_changing_display_stops_the_old_source_without_opening_another_picker(self):
        self.window.monitor.setCurrentIndex(0)
        self.window.monitor.setCurrentIndex(1)
        self.assertEqual(self.window.mode, "idle")
        self.assertEqual(self.window.reader.starts, 0)
        self.assertEqual(self.window.reader.pauses, [False])

    def test_catalog_retry_is_bounded_while_a_request_is_in_progress(self):
        self.window.catalog = None
        self.window.on_error(0, "HTTP Error 503")
        self.assertTrue(self.window.catalog_error)
        for _ in range(500):
            self.window.retry_catalog()
        self.assertEqual(self.window.service.catalog_starts, 2)
        self.assertTrue(self.window.catalog_loading)

    def test_example_preview_needs_neither_capture_nor_price_requests(self):
        self.window.mode = "idle"
        self.window.rows = []
        snapshot = []
        def inspect():
            dialog = self.window.findChild(QDialog, "exampleDialog")
            try:
                snapshot.extend(widget.text() for widget in dialog.findChildren(QLabel))
            finally:
                dialog.reject()
        QTimer.singleShot(0, inspect)
        self.window.preview_examples()
        self.assertIn("EXAMPLE PRICES", snapshot)
        self.assertTrue(any("made-up" in value for value in snapshot))
        self.assertEqual(self.window.reader.starts, 0)
        self.assertEqual(self.window.service.requests, [])

    def test_recognised_item_without_reports_is_not_called_unreadable(self):
        self.window.on_reading(self.reading(shop_hover=True))
        now = time.time()
        self.window.on_quote(1, Quote(1, None, now, None, 0, "Test", "", "24h"))
        content = "\n".join(widget.text() for widget in self.window.cards.findChildren(QLabel))
        self.assertIn("Item name recognised", content)
        self.assertIn("No market reports", content)
        self.assertNotIn("unreadable", content.lower())

    def test_empty_hover_reference_is_not_left_checking_forever(self):
        self.window.reader.pointer = (100, 100)
        self.window.on_reading(self.reading(shop_hover=False))
        self.window.on_quote(1, Quote(1, None, time.time(), None, 0, "Test", "", "24h"))
        self.assertEqual(len(self.window.overlay.rows), 2)
        self.assertEqual(self.window.overlay.rows[-1]["text"], "FM • source has no market data")

    def test_saved_screenshot_is_labeled_even_without_a_display_selected(self):
        self.window.monitor.setCurrentIndex(0)
        self.window.mode = "screenshot"
        self.window.render()
        self.assertEqual(self.window.status_badge.text(), "Saved screenshot")
        self.assertFalse(self.window.share.isEnabled())
        self.assertIn("saved image", self.window.capture_info.text())
        self.assertEqual(self.window.overlay.rows, [])

    def test_first_real_price_offers_optional_hotkey_and_minimize(self):
        self.window.on_reading(self.reading(shop_hover=True))
        now = time.time()
        self.window.on_quote(1, Quote(1, 1000, now, now, 20, "Test", "", "24h"))
        self.assertTrue(self.window.settings.values["first-price-seen"])
        self.assertFalse(self.window.success_frame.isHidden())
        self.assertTrue(any(button.text() == "Minimize panel" for button in self.window.success_frame.findChildren(QPushButton)))
        self.window.dismiss_setup()
        self.assertTrue(self.window.success_frame.isHidden())

    def test_details_remain_open_across_price_card_updates(self):
        self.window.on_reading(self.reading(shop_hover=True))
        details = next(button for button in self.window.cards.findChildren(QPushButton) if button.text() == "Details")
        details.click()
        self.window.card_key = None
        self.window.render()
        self.assertTrue(any(button.text() == "Hide details" for button in self.window.cards.findChildren(QPushButton)))

    def test_expiration_removes_comparison_inside_the_same_age_bucket(self):
        with patch("price_lens.ui.time.time", return_value=1001):
            self.window.last_screen = 1001
            self.window.on_reading(self.reading(shop_hover=True))
            self.window.on_quote(1, Quote(1, 1000, 101.2, 1000, 20, "Test", "", "24h"))
            previous = self.window.card_key
            self.assertTrue(any("below reference" in widget.text() for widget in self.window.cards.findChildren(QLabel)))
        with patch("price_lens.ui.time.time", return_value=1001.3):
            self.window.render()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            self.assertNotEqual(previous, self.window.card_key)
            content = "\n".join(widget.text() for widget in self.window.cards.findChildren(QLabel))
            self.assertIn("Older reference", content)
            self.assertNotIn("below reference", content)
            self.assertTrue(any("refresh needed" in row["text"] for row in self.window.overlay.rows))

    def test_hovered_item_is_the_priority_even_when_shop_rows_are_present(self):
        self.window.on_catalog(Catalog({"items": [{"id": 1, "name": "Example Hat"},
                                                  {"id": 2, "name": "Other Hat"}], "scrolls": []}))
        self.window.reader.pointer = (100, 100)
        reading = self.reading(shop_hover=False)
        reading["tooltip"]["found"]["name"] = "Other Hat"
        self.window.on_reading(reading)
        self.assertEqual(self.window.service.hovered_id, 2)
        self.assertEqual(self.window.service.visible, [2, 1])

    def test_refresh_progress_updates_cards_and_both_overlay_contexts(self):
        self.window.reader.pointer = (100, 100)
        self.window.on_reading(self.reading(shop_hover=False))
        now = time.time()
        self.window.on_quote(1, Quote(1, 1000, now - 1080, now, 20, "Test", "", "24h"))
        self.window.service.states[1] = "refreshing"
        self.window.service.state_changed.emit()
        self.app.processEvents()
        content = "\n".join(widget.text() for widget in self.window.cards.findChildren(QLabel))
        self.assertIn("Refreshing market reference", content)
        self.assertEqual(len(self.window.overlay.rows), 2)
        for row in self.window.overlay.rows:
            self.assertIn("18m old", row["text"])
            self.assertIn("refreshing", row["text"])
            self.assertNotEqual(row["color"], "#86ceac")
        self.window.pause()
        self.assertEqual(self.window.service.visible, [])

    def test_recent_lookup_with_old_reports_explains_the_market_data_age(self):
        self.window.on_reading(self.reading(shop_hover=True))
        now = time.time()
        self.window.on_quote(1, Quote(1, 1000, now, now - 90000, 20, "Test", "", "24h"))
        self.assertIn("old market reports", self.window.overlay.rows[0]["text"])
        self.assertNotIn("EXPIRED", self.window.overlay.rows[0]["text"])

    def test_hidden_labels_can_be_restored_without_reconnecting(self):
        self.window.on_reading(self.reading(shop_hover=True))
        self.window.labels_check.setChecked(False)
        self.window.on_pointer(100, 100)
        self.assertFalse(self.window.reader.tooltip_enabled)
        self.assertIsNone(self.window.reader.pointer)
        self.assertEqual(self.window.overlay.rows, [])
        self.assertEqual(self.window.recovery_button.text(), "Show price labels")
        self.window.recovery_button.click()
        self.assertTrue(self.window.labels_enabled)
        self.assertTrue(self.window.reader.tooltip_enabled)
        self.assertEqual(self.window.reader.starts, 0)

    def test_mismatched_references_never_reach_overlay_or_success_message(self):
        self.window.on_reading(self.reading(shop_hover=True))
        now = time.time()
        valid = Quote(1, 987654, now, now, 20, "Test", "", "24h")
        for change in ({"world": "Other World"}, {"game_id": 2}, {"condition": "scrolled"}, {"per_set": True}):
            with self.subTest(change=change):
                self.window.on_quote(1, replace(valid, **change))
                self.assertFalse(self.window.first_price_seen)
                self.assertNotIn("987,654", "\n".join(row["text"] for row in self.window.overlay.rows))
                self.assertIn("0 market references ready", self.window.summary.text())

    def test_display_diagram_selects_friendly_display_without_starting_capture(self):
        class Screen:
            def __init__(self, number):
                self.number = number

            def name(self):
                return f"DEVICE-{self.number}"

            def geometry(self):
                return QRect(self.number * 1280, 0, 1280, 720)

            def devicePixelRatio(self):
                return 1.5

        with patch("price_lens.ui.QApplication.screens", return_value=[Screen(i) for i in range(3)]):
            fresh = LensWindow(Path.cwd(), Path("unused-cache"))
            try:
                self.assertEqual(fresh.monitor.itemText(2), "Display 2 · Centre · 1920 × 1080")
                fresh.display_map.resize(400, 78)
                fresh.display_map.grab()
                point = fresh.display_map.boxes[1].center()
                event = QMouseEvent(QEvent.Type.MouseButtonPress, point, point,
                                    Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                                    Qt.KeyboardModifier.NoModifier)
                fresh.display_map.mousePressEvent(event)
                self.assertEqual(fresh.screen_index, 1)
                self.assertEqual(fresh.reader.starts, 0)
                self.assertEqual(fresh.settings.values["monitor-name"], "DEVICE-1")
            finally:
                fresh.close()
                fresh.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
