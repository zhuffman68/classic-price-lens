"""Exercise real scheduling with controlled workers, clocks and no network."""
from dataclasses import replace
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QApplication

from price_lens.domain import Item, Quote, compare
from price_lens.price_status import reference_status
from price_lens.service import PriceService


class PriceSchedulingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.service = PriceService(Path(self.directory.name) / "prices.sqlite")
        self.items = [Item(1000000 + index, f"Example item {index}") for index in range(100)]
        self.gates = {item.game_id: threading.Event() for item in self.items}
        self.started = []
        self.lock = threading.Lock()
        self.running = self.peak = 0

    def tearDown(self):
        for gate in self.gates.values():
            gate.set()
        self.service.close()
        self.service.pool.shutdown(wait=True)
        self.app.processEvents()
        self.directory.cleanup()

    def until(self, condition):
        deadline = time.monotonic() + 3
        while not condition() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.001)
        self.assertTrue(condition())

    def quote(self, item, fetched=None, **changes):
        now = time.time()
        return replace(Quote(item.game_id, 1000, now if fetched is None else fetched,
                             now, 10, "NiaMeowDB", "", "24h"), **changes)

    def block_workers(self):
        def fetch(item):
            with self.lock:
                self.started.append(item.game_id)
                self.running += 1
                self.peak = max(self.peak, self.running)
            try:
                if not self.gates[item.game_id].wait(3):
                    raise TimeoutError("Test worker was not released")
                return self.quote(item)
            finally:
                with self.lock:
                    self.running -= 1
        self.service.provider.fetch = fetch

    def test_hover_is_started_first_when_an_entire_shop_arrives(self):
        self.block_workers()
        hovered = self.items[12]
        self.service.observe(self.items[:13], 900, hovered_id=hovered.game_id)
        self.until(lambda: len(self.started) == 3)
        self.assertIn(hovered.game_id, self.started[:3])
        self.assertEqual(self.peak, 3)
        for _ in range(500):
            self.service.observe(self.items[:13], 900, hovered_id=hovered.game_id)
        self.assertEqual(len(self.started), 3)
        self.assertEqual(len(self.service.pending), 13)

    def test_new_hover_is_promoted_ahead_of_existing_shop_queue(self):
        self.block_workers()
        visible = self.items[:9]
        hovered = visible[-1]
        self.service.observe(visible, 900)
        self.until(lambda: len(self.started) == 3)
        self.service.observe(visible, 900, hovered_id=hovered.game_id)
        self.gates[self.started[0]].set()
        self.until(lambda: len(self.started) == 4)
        self.assertEqual(self.started[3], hovered.game_id)
        self.assertLessEqual(self.peak, 3)

    def test_leaving_shop_cancels_waiting_work_without_cooling_down_a_revisit(self):
        self.block_workers()
        self.service.observe(self.items[:9], 900)
        self.until(lambda: len(self.started) == 3)
        new = self.items[9]
        self.service.observe([new], 900, hovered_id=new.game_id)
        for item in self.items[3:9]:
            self.assertNotIn(item.game_id, self.service.pending)
            self.assertNotIn(item.game_id, self.service.retry_at)
        self.gates[self.started[0]].set()
        self.until(lambda: len(self.started) == 4)
        self.assertEqual(self.started[3], new.game_id)
        revisit = self.items[4]
        self.service.observe([revisit], 900, hovered_id=revisit.game_id)
        self.gates[self.started[1]].set()
        self.until(lambda: revisit.game_id in self.started)

    def test_pause_cancels_obsolete_running_results_without_retry_cooldown(self):
        self.block_workers()
        self.service.observe(self.items[:12], 900)
        self.until(lambda: len(self.started) == 3)
        self.service.clear_visible()
        for gate in self.gates.values():
            gate.set()
        self.until(lambda: not self.service.pending)
        self.assertEqual(len(self.started), 3)
        self.assertEqual(len(self.service.delivered), 0)
        self.assertEqual(self.service.retry_at,{})

    def test_queue_has_a_hard_bound_and_admits_a_new_hover(self):
        self.block_workers()
        for item in self.items:
            self.service.request(item, 900)
        self.until(lambda: len(self.started) == 3)
        self.assertEqual(len(self.service.pending), self.service.MAX_QUEUED + 3)
        self.service.request(self.items[-1], 900, priority=0)
        self.assertEqual(len(self.service.pending), self.service.MAX_QUEUED + 3)
        self.assertEqual(self.service.state_for(self.items[-1].game_id), "queued")
        self.gates[self.started[0]].set()
        self.until(lambda: len(self.started) == 4)
        self.assertEqual(self.started[3], self.items[-1].game_id)

    def test_stale_quote_is_delivered_before_the_blocked_refresh(self):
        self.block_workers()
        item = self.items[0]
        old = self.quote(item, fetched=time.time() - 901)
        self.service.cache.save_quote(old)
        delivered = []
        self.service.quote_ready.connect(lambda _, quote: delivered.append(quote))
        self.service.observe([item], 900)
        self.assertEqual(delivered, [old])
        self.assertEqual(self.service.state_for(item.game_id), "refreshing")
        self.assertEqual(compare(item, 1, 10, old).label, "Expired")
        self.gates[item.game_id].set()
        self.until(lambda: len(delivered) == 2)
        self.assertEqual(self.service.state_for(item.game_id), "")

    def test_completion_signals_are_delivered_on_the_owning_thread(self):
        owner = threading.get_ident()
        worker_threads, receiver_threads = [], []
        def fetch(item):
            worker_threads.append(threading.get_ident())
            return self.quote(item)
        self.service.provider.fetch = fetch
        self.service.quote_ready.connect(lambda *_: receiver_threads.append(threading.get_ident()))
        self.service.request(self.items[0], 900)
        self.until(lambda: not self.service.pending)
        self.assertNotEqual(worker_threads, [owner])
        self.assertEqual(receiver_threads, [owner])

    def test_only_one_early_refresh_per_cycle_at_each_supported_ttl(self):
        base = time.time()
        for index, ttl in enumerate((300, 900, 1800, 3600)):
            with self.subTest(ttl=ttl):
                item = self.items[index]
                lead = self.service.refresh_lead(item.game_id, ttl)
                self.assertGreaterEqual(lead, min(30, ttl * 0.05) / 2)
                self.assertLessEqual(lead, 30)
                old = self.quote(item, fetched=base - ttl + lead)
                self.service.cache.save_quote(old)
                fetch = Mock(side_effect=lambda value: self.quote(value))
                self.service.provider.fetch = fetch
                with patch("price_lens.service.time.time", return_value=base - 0.01):
                    self.service.observe([item], ttl)
                    fetch.assert_not_called()
                with patch("price_lens.service.time.time", return_value=base + 0.01):
                    for _ in range(500):
                        self.service.observe([item], ttl)
                    self.until(lambda: not self.service.pending)
                    for _ in range(500):
                        self.service.observe([item], ttl)
                    self.assertEqual(fetch.call_count, 1)

    def test_empty_uncertain_thin_and_old_report_results_wait_for_full_ttl(self):
        now = time.time()
        variants = ({"price": None, "observed_at": None, "sample_count": 0},
                    {"uncertain": True}, {"sample_count": 2}, {"observed_at": now - 90000})
        for index, changes in enumerate(variants):
            item = self.items[index]
            quote = self.quote(item, fetched=now - 899, **changes)
            self.service.cache.save_quote(quote)
            self.service.provider.fetch = Mock(return_value=self.quote(item))
            with patch("price_lens.service.time.time", return_value=now):
                for _ in range(100):
                    self.service.observe([item], 900)
                self.service.provider.fetch.assert_not_called()

    def test_failed_early_refresh_retries_at_expiry_then_uses_normal_backoff(self):
        now = time.time()
        item = self.items[0]
        lead = self.service.refresh_lead(item.game_id, 900)
        old = self.quote(item, fetched=now - 900 + lead)
        self.service.cache.save_quote(old)
        self.service.provider.fetch = Mock(side_effect=OSError("offline"))
        with patch("price_lens.service.time.time", return_value=now):
            self.service.observe([item], 900)
            self.until(lambda: not self.service.pending)
            self.assertEqual(self.service.retry_at[item.game_id], old.fetched_at + 900)
            for _ in range(100):
                self.service.observe([item], 900)
            self.assertEqual(self.service.provider.fetch.call_count, 1)
            self.assertEqual(self.service.delivered[item.game_id], old)
        with patch("price_lens.service.time.time", return_value=now + lead):
            self.service.observe([item], 900)
            self.until(lambda: not self.service.pending)
            self.assertEqual(self.service.provider.fetch.call_count, 2)
            self.assertEqual(self.service.retry_at[item.game_id], now + lead + 120)

    def test_identity_resolution_uses_the_same_priority_and_visibility_rules(self):
        self.block_workers()
        self.service.observe(self.items[:3], 900)
        self.until(lambda: len(self.started) == 3)
        identity = ("Ambiguous item", None)
        resolve = Mock(return_value=self.items[5])
        self.service.provider.resolve_name = resolve
        self.service.observe(self.items[:7], 900, identities=[(identity, self.items[5:7])],
                             hovered_identity=identity)
        self.gates[self.started[0]].set()
        self.until(lambda: resolve.call_count == 1)
        self.until(lambda: identity not in self.service.identity_pending)
        self.assertIn(identity, self.service.identity_retry)
        self.service.clear_visible()


class RefreshStatusTests(unittest.TestCase):
    def test_states_keep_the_old_price_age_and_old_reports_distinct(self):
        now = time.time()
        quote = Quote(1, 1000, now - 1080, now, 10, "NiaMeowDB", "", "24h")
        self.assertEqual(reference_status(quote, "refreshing", now, 900), "18m old • refreshing…")
        self.assertIn("refresh queued", reference_status(quote, "queued", now, 900))
        self.assertIn("retry later", reference_status(quote, "retry", now, 900))
        self.assertIn("refresh needed", reference_status(quote, "", now, 900))
        old_reports = replace(quote, fetched_at=now, observed_at=now - 90000)
        self.assertIn("old market reports", reference_status(old_reports, "", now, 900))
        self.assertIn("report age unknown", reference_status(replace(old_reports, observed_at=None), "", now, 900))
        self.assertEqual(reference_status(None, "queued", now, 900), "lookup queued…")


if __name__ == "__main__":
    unittest.main()
