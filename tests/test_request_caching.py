import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import urllib.error

from PySide6.QtWidgets import QApplication

from price_lens.data import MeowProvider
from price_lens.domain import Item, compare
from price_lens.service import PriceService


class RequestCachingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.service = PriceService(Path(self.directory.name) / "cache.sqlite")
        self.item = Item(1000001, "Example Hat", equipment=True)
        self.service.cache.put("meow-id", self.item.game_id, {"id": 42})
        self.summary = {"itemId": 42, "condition": "clean", "usual": 1000, "priceChecks": 20, "finishedTrades": 1,
                        "newestPriceAt": datetime.now(timezone.utc).isoformat(), "last24h": {"median": 1000, "count": 10}}

    def tearDown(self):
        self.service.close()
        self.service.pool.shutdown(wait=True)
        self.directory.cleanup()

    def settle(self):
        end = time.monotonic() + 2
        while self.service.pending and time.monotonic() < end:
            self.app.processEvents()
            time.sleep(0.001)
        self.assertFalse(self.service.pending)

    def test_hundreds_of_unchanged_reads_make_one_request_until_ttl(self):
        with patch("price_lens.data.get_json", return_value=self.summary) as http:
            self.service.request(self.item, 900)
            self.settle()
            fetched = self.service.delivered[self.item.game_id].fetched_at
            with patch("price_lens.service.time.time", return_value=fetched + 899):
                for _ in range(500):
                    self.service.request(self.item, 900)
            self.assertEqual(http.call_count, 1)
            with patch("price_lens.service.time.time", return_value=fetched + 900):
                for _ in range(100):
                    self.service.request(self.item, 900)
                self.settle()
            self.assertEqual(http.call_count, 2)

    def test_recent_empty_response_is_cached_without_repeated_requests(self):
        self.summary.update(usual=None, newestPriceAt=None, last24h={"median": None, "count": 0}, priceChecks=0, finishedTrades=0)
        with patch("price_lens.data.get_json", return_value=self.summary) as http:
            self.service.request(self.item, 900)
            self.settle()
            fetched = self.service.delivered[self.item.game_id].fetched_at
            with patch("price_lens.service.time.time", return_value=fetched + 300):
                for _ in range(500):
                    self.service.request(self.item, 900)
            self.assertEqual(http.call_count, 1)

    def test_old_market_reports_do_not_defeat_the_http_cache(self):
        self.summary["newestPriceAt"] = datetime.fromtimestamp(time.time() - 3 * 86400, timezone.utc).isoformat()
        with patch("price_lens.data.get_json", return_value=self.summary) as http:
            self.service.request(self.item, 900)
            self.settle()
            quote = self.service.delivered[self.item.game_id]
            self.assertFalse(quote.fresh())
            for _ in range(500):
                self.service.request(self.item, 900)
            self.assertEqual(http.call_count, 1)

    def test_known_400_coverage_rejection_becomes_a_cached_item_result(self):
        error = urllib.error.HTTPError("https://example.org", 400, "Bad Request", {},
                                       io.BytesIO(json.dumps({"code": "fm_not_tradeable", "error": "Not tradeable"}).encode()))
        with patch("price_lens.data.get_json", side_effect=error) as http:
            self.service.request(self.item, 900)
            self.settle()
            quote = self.service.delivered[self.item.game_id]
            self.assertIsNone(quote.price)
            self.assertIn("does not cover", quote.basis)
            for _ in range(500):
                self.service.request(self.item, 900)
            self.assertEqual(http.call_count, 1)
            self.assertEqual(compare(self.item, 1, 100, quote).label, "No reference")
