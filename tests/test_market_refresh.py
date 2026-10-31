"""Expiry deadlines and queued market updates using only isolated local fixtures."""
from copy import deepcopy
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication

from price_lens.annotations import AnnotationWindow
from price_lens.data import Cache
from price_lens.domain import Item, Quote
from price_lens.price_status import reference_status
from price_lens.service import PriceService
from price_lens.snapshot import SnapshotStore
from price_lens.snapshot_updater import SnapshotUpdater
from test_snapshot import document, iso


class MarketDeadlineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.store = SnapshotStore(Cache(Path(folder.name)/'prices.sqlite'))
        self.updater = SnapshotUpdater(self.store)
        self.addCleanup(self.updater.close)
        self.updater.enabled = True
        self.updater.interval = 3600
        self.now = 2_000_000_000
        self.enterContext(patch('price_lens.snapshot_updater.time.time', side_effect=lambda: self.now))
        self.fetch = self.enterContext(patch.object(self.updater.fetcher, 'start'))
        self.item = Item(4010000, 'Bronze Ore')

    def test_hourly_refresh_uses_publication_expiry_instead_of_another_whole_hour(self):
        doc = document(self.now)
        doc['generated_at'] = iso(self.now-720)
        self.updater.accept(doc)
        self.assertEqual(self.updater.timer.interval(), 2_880_000)
        self.now += 120
        self.updater.set_interval(1800)
        self.assertEqual(self.updater.timer.interval(), 1_680_000)
        self.updater.set_interval(3600)
        self.assertEqual(self.updater.timer.interval(), 2_760_000)
        self.assertEqual(self.fetch.call_count, 0)

    def test_submillisecond_expiry_never_becomes_an_immediate_or_early_timer(self):
        doc = document(self.now)
        doc['generated_at'] = iso(self.now-3600+.0004)
        self.updater.accept(doc)
        self.assertEqual(self.updater.timer.interval(), 1)
        self.assertEqual(self.updater.timer.timerType(), Qt.TimerType.PreciseTimer)

    def test_interval_changes_cannot_postpone_the_immediate_launch_check(self):
        self.store.save(document(self.now), self.now)
        self.updater.enabled = False
        self.updater.set_enabled(True)
        self.updater.set_interval(3600)
        self.assertEqual(self.updater.timer.interval(), 0)
        self.app.processEvents()
        self.assertEqual(self.fetch.call_count, 1)
        self.updater.refresh()
        self.assertEqual(self.fetch.call_count, 1)

    def test_unchanged_expired_publication_retries_with_a_separate_bounded_backoff(self):
        doc = document(self.now)
        doc['generated_at'] = iso(self.now-3601)
        published = self.now-3601
        for delay in (60, 300, 900, 900):
            self.updater.accept(doc)
            self.assertEqual(self.updater.timer.interval(), delay*1000)
            quote = self.store.quote(self.item)
            self.assertEqual(quote.published_at, published)
            self.assertEqual(quote.fetched_at, self.now)
            self.assertFalse(quote.cache_valid(self.now, 3600))
            self.assertEqual(self.updater.failures, 0)
            self.assertIn('source snapshot old', self.updater.summary())
            self.now += delay
            self.updater.refresh()
        self.assertEqual(self.fetch.call_count, 4)

    def test_stale_backoff_respects_a_shorter_selected_interval(self):
        self.updater.interval = 300
        doc = document(self.now)
        doc['generated_at'] = iso(self.now-3601)
        for delay in (60, 300, 300):
            self.updater.accept(doc)
            self.assertEqual(self.updater.timer.interval(), delay*1000)
            self.now += delay

    def test_interval_changes_preserve_pending_source_retry_instead_of_looping(self):
        doc = document(self.now)
        doc['generated_at'] = iso(self.now-3601)
        self.updater.accept(doc)
        self.now += 10
        self.updater.set_interval(1800)
        self.assertEqual(self.updater.timer.interval(), 50_000)
        self.assertEqual(self.fetch.call_count, 0)

    def test_source_and_transport_backoffs_do_not_change_each_others_counters(self):
        doc = document(self.now)
        doc['generated_at'] = iso(self.now-3601)
        self.updater.accept(doc)
        self.now += 60
        self.updater.refresh()
        self.updater.failed('Offline')
        self.assertEqual(self.updater.timer.interval(), 300_000)
        self.assertEqual((self.updater.failures, self.updater.stale_checks), (1, 1))
        self.now += 300
        self.updater.refresh()
        self.updater.accept(doc)
        self.assertEqual(self.updater.timer.interval(), 300_000)
        self.assertEqual((self.updater.failures, self.updater.stale_checks), (0, 2))
        self.assertEqual(self.updater.error, '')

    def test_newer_publication_resets_source_backoff_without_faking_freshness(self):
        doc = document(self.now)
        doc['generated_at'] = iso(self.now-3601)
        for delay in (60, 300):
            self.updater.accept(doc)
            self.now += delay
        newer = document(self.now)
        newer['generated_at'] = iso(self.now-3601)
        self.updater.accept(newer)
        self.assertEqual((self.updater.stale_checks, self.updater.timer.interval()), (1, 60_000))
        self.assertFalse(self.store.quote(self.item).fresh(self.now, 3600))
        self.updater.accept(document(self.now))
        self.assertEqual((self.updater.stale_checks, self.updater.stale_publication), (0, None))
        self.assertIsNone(self.updater.retry_at)
        self.assertEqual(self.updater.timer.interval(), 3_540_000)
        self.assertTrue(self.store.quote(self.item).fresh(self.now, 3600))

    def test_status_distinguishes_old_publication_from_an_overdue_check(self):
        quote = Quote(4010000, 100, self.now, self.now-120, 9, 'MesoWatch', '', '24h',
                      published_at=self.now-3601)
        self.assertIn('source snapshot old', reference_status(quote, '', self.now, 3600))
        self.assertIn('refreshing', reference_status(quote, 'refreshing', self.now, 3600))
        self.assertIn('retry later', reference_status(quote, 'retry', self.now, 3600))
        overdue = replace(quote, fetched_at=self.now-901, published_at=self.now-961)
        self.assertIn('refresh needed', reference_status(overdue, '', self.now, 900))


class MarketRefreshPropagationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        cls.app = QApplication.instance() or QApplication([])

    def test_same_price_expired_to_fresh_reaches_the_actual_annotation_without_input(self):
        # Reuse the established isolated UI fixture, replacing its fake price
        # service and drawing receiver. No subprocess or network is started.
        import test_ui_context as ui_fixtures
        fixture = ui_fixtures.ContextUiTests()
        fixture.app = self.app
        self.addCleanup(fixture.doCleanups)
        self.enterContext(patch.object(PriceService, 'start'))
        fetch = self.enterContext(patch('price_lens.snapshot_updater.SnapshotFetcher.start'))
        self.enterContext(patch('price_lens.data.get_json', side_effect=AssertionError('No price HTTP calls')))
        self.enterContext(patch('price_lens.annotations.QCursor.pos', return_value=QPoint(340, 240)))

        class ReceivingOverlay(ui_fixtures.FakeOverlay):
            def __init__(self, root, parent=None):
                super().__init__(root, parent)
                self.receiver = AnnotationWindow(start_listener=False)

            def update(self, geometry, rows, hover_enabled=False):
                super().update(geometry, rows, hover_enabled)
                self.receiver.read_command(json.dumps(dict(geometry=geometry, rows=rows,
                    hover_enabled=hover_enabled, reduce_motion=getattr(self, 'reduce_motion', False))))
                self.receiver.pointer_timer.stop()

            def close(self):
                self.receiver.pointer_timer.stop()
                self.receiver.watchdog.stop()
                self.receiver.close()
                self.receiver.deleteLater()

        def isolated_service(path, parent=None):
            return PriceService(Path(fixture.exp_directory.name)/'market.sqlite', parent)

        with patch.object(ui_fixtures, 'FakeService', isolated_service), \
                patch.object(ui_fixtures, 'FakeOverlay', ReceivingOverlay):
            fixture.setUp()
        self.addCleanup(fixture.tearDown)
        window = fixture.window
        window.timer.stop()
        service = window.service
        now = time.time()

        def hat_document(at):
            doc = document(at)
            doc['items'][0].update(id='basil:00000001', name='Example Hat')
            return doc

        service.snapshot.save(hat_document(now-901), now-901)
        window.on_reading(fixture.reading(shop_hover=True))
        receiver = window.overlay.receiver
        active = receiver.rows[0]
        key, content, color = active['key'], deepcopy(active['content_id']), active['color']
        self.assertIn('refresh needed', active['text'])
        rows, pointer, sequence = deepcopy(window.rows), window.reader.pointer, window.reader.image_sequence
        states = []
        service.state_changed.connect(lambda: states.append(True), Qt.ConnectionType.QueuedConnection)
        service.set_snapshot_enabled(True)
        for _ in range(4):
            self.app.processEvents()
        self.assertTrue(service.snapshot_updater.busy)
        self.assertIn('refreshing', active['text'])
        self.assertEqual(fetch.call_count, 1)
        before = len(states)
        service.snapshot_updater.accept(hat_document(now))
        self.assertEqual(len(states), before)  # Production state callbacks are queued.
        for _ in range(4):
            self.app.processEvents()
        self.assertGreater(len(states), before)
        self.assertEqual(window.quote_generation, service.snapshot.meta['checked_at'])
        self.assertIs(receiver.rows[0], active)
        self.assertEqual((active['key'], active['content_id']), (key, content))
        self.assertNotIn('refresh needed', active['text'])
        self.assertNotIn('refreshing', active['text'])
        self.assertNotIn('source snapshot old', active['text'])
        self.assertNotEqual(active['color'], color)
        self.assertEqual(service.delivered[1].price, 100)
        self.assertTrue(service.delivered[1].fresh(time.time(), window.ttl))
        self.assertEqual((window.rows, window.reader.pointer, window.reader.image_sequence), (rows, pointer, sequence))
        self.assertEqual((fetch.call_count, window.reader.starts), (1, 0))
