from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QImage

from price_lens.data import Cache, MeowProvider, load_catalog, parse_summary
from price_lens.domain import Catalog, compare
from price_lens.stream import screen_pixels
from price_lens.capture import pointer_in_shop

BASE = {"items": [{"id": 1000001, "name": "Example Hat", "category": "Equipment"}], "scrolls": []}
CASH = {"categories": [{"category": "Coupon", "items": [
    {"id": 5680999, "name": "Example Slot Coupon", "price": 5000, "count": 1, "on_sale": True},
    {"id": 5680998, "name": "Example Slot Coupon Plus", "price": 7000, "on_sale": False},
    {"id": 1000001, "name": "Example Hat", "category": "Equipment", "price": 900, "on_sale": True},
]}]}


class CashTests(unittest.TestCase):
    def test_cash_catalog_adds_nx_items_without_duplicate_game_ids(self):
        catalog = Catalog(BASE, CASH)
        self.assertEqual(len(catalog.items), 3)
        coupon = catalog.resolve("Example Slot Coupon")
        self.assertTrue(coupon.cash)
        self.assertEqual(coupon.nx_price, 5000)
        self.assertEqual(catalog.resolve("Example Hat").game_id, 1000001)
        self.assertTrue(catalog.resolve("Example Hat").cash)

    def test_off_sale_items_remain_identifiable_and_shared_prefix_is_ambiguous(self):
        catalog = Catalog(BASE, CASH)
        self.assertFalse(catalog.resolve("Example Slot Coupon Plus").on_sale)
        self.assertIsNone(catalog.resolve("Example Slot Coup..."))

    def test_preexisting_regular_catalog_cache_still_loads_cash_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Cache(Path(directory) / "prices.sqlite")
            cache.put("catalog", "osms", BASE)
            with patch("price_lens.data.get_json", return_value=CASH) as get:
                catalog = load_catalog(cache)
            self.assertEqual(get.call_count, 1)
            self.assertTrue(catalog.resolve("Example Slot Coupon").cash)
            with patch("price_lens.data.get_json", side_effect=AssertionError("cache should be used")):
                self.assertTrue(load_catalog(cache).resolve("Example Slot Coupon").cash)

    def test_cash_catalog_failure_keeps_regular_items_and_reports_missing_nx(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Cache(Path(directory) / "prices.sqlite")
            cache.put("catalog", "osms", BASE)
            with patch("price_lens.data.get_json", side_effect=OSError("offline")):
                catalog = load_catalog(cache)
            self.assertIsNotNone(catalog.resolve("Example Hat"))
            self.assertIn("NX catalog unavailable", catalog.warning)

    def test_market_mesos_are_not_replaced_by_cash_shop_nx(self):
        item = Catalog(BASE, CASH).resolve("Example Slot Coupon")
        summary = {"itemId": 8, "condition": "clean", "newestPriceAt": "2033-05-18T03:33:20Z",
                   "usual": 40000, "last24h": {"median": 44000, "count": 12}}
        quote = parse_summary(item, summary, 8, 2_000_000_000)
        result = compare(item, 1, 22000, quote, 2_000_000_000)
        self.assertEqual(quote.price, 44000)
        self.assertEqual(item.nx_price, 5000)
        self.assertEqual(result.label, "Below reference")
        self.assertEqual(result.delta, -50)

    def test_cash_provider_still_checks_exact_name_and_game_id(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = MeowProvider(Cache(Path(directory) / "prices.sqlite"))
            item = Catalog(BASE, CASH).resolve("Example Slot Coupon")
            with patch("price_lens.data.get_json", return_value={"items": [
                {"id": 8, "name": item.name, "iconKey": str(item.game_id), "type": "Cash"}
            ]}):
                self.assertEqual(provider.resolve_id(item), 8)

    def test_duplicate_name_is_narrowed_by_one_current_provider_item(self):
        cash = {"categories": [{"items": [
            {"id": 1007001, "name": "Example Uniform"}, {"id": 1007999, "name": "Example Uniform"}
        ]}]}
        catalog = Catalog(BASE, cash)
        self.assertIsNone(catalog.resolve("Example Uniform"))
        with tempfile.TemporaryDirectory() as directory:
            provider = MeowProvider(Cache(Path(directory) / "prices.sqlite"))
            with patch("price_lens.data.get_json", return_value={"hasMore": False, "items": [
                {"id": 7, "name": "Example Uniform", "iconKey": "1007001"}
            ]}):
                item = provider.resolve_name("Example Uniform", catalog.candidates("Example Uniform"))
        catalog.bind_current("Example Uniform", None, item)
        self.assertEqual(catalog.resolve("Example Uniform").game_id, 1007001)

    def test_two_current_provider_versions_are_still_ambiguous(self):
        cash = {"categories": [{"items": [
            {"id": 1007001, "name": "Example Uniform"}, {"id": 1007999, "name": "Example Uniform"}
        ]}]}
        catalog = Catalog(BASE, cash)
        with tempfile.TemporaryDirectory() as directory:
            provider = MeowProvider(Cache(Path(directory) / "prices.sqlite"))
            with patch("price_lens.data.get_json", return_value={"hasMore": False, "items": [
                {"id": 7, "name": "Example Uniform", "iconKey": "1007001"},
                {"id": 8, "name": "Example Uniform", "iconKey": "1007999"}
            ]}):
                with self.assertRaises(ValueError):
                    provider.resolve_name("Example Uniform", catalog.candidates("Example Uniform"))


class CaptureGeometryTests(unittest.TestCase):
    def test_store_listing_hover_has_priority_over_inventory_hover(self):
        listing = QRect(300, 200, 240, 400)
        self.assertTrue(pointer_in_shop((340, 260), listing))
        self.assertFalse(pointer_in_shop((100, 260), listing))
        self.assertFalse(pointer_in_shop((340, 260), None))
        self.assertFalse(pointer_in_shop(None, listing))

    def test_full_workspace_selects_middle_monitor_pixels(self):
        image = QImage(300, 50, QImage.Format.Format_RGB32)
        image.fill(QColor("red"))
        for x in range(100, 200):
            for y in range(50):
                image.setPixelColor(x, y, QColor("blue"))
        cropped = screen_pixels(image, QRect(100, 0, 100, 50), QRect(0, 0, 300, 50))
        self.assertEqual((cropped.width(), cropped.height()), (100, 50))
        self.assertEqual(cropped.pixelColor(5, 5), QColor("blue"))

    def test_negative_desktop_origin_maps_to_correct_pixels(self):
        image = QImage(300, 50, QImage.Format.Format_RGB32)
        image.fill(QColor("green"))
        cropped = screen_pixels(image, QRect(0, 0, 100, 50), QRect(-100, 0, 300, 50))
        self.assertEqual((cropped.width(), cropped.height()), (100, 50))
        self.assertEqual(cropped.pixelColor(5, 5), QColor("green"))

    def test_shared_single_monitor_is_not_cropped_as_workspace(self):
        image = QImage(100, 50, QImage.Format.Format_RGB32)
        cropped = screen_pixels(image, QRect(100, 0, 100, 50), QRect(0, 0, 300, 50))
        self.assertEqual(cropped.size(), image.size())
