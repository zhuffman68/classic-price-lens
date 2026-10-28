"""Bulk market scheduling: no individual lookups, including missing/expired items."""
import os,time,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from price_lens.domain import Item,compare
from price_lens.service import PriceService
from test_snapshot import document


class PriceSchedulingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen');cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.service=PriceService(Path(self.directory.name)/'prices.sqlite')
        self.now=time.time();self.item=Item(4010000,'Bronze Ore');self.service.snapshot.save(document(self.now),self.now)
    def tearDown(self):
        self.service.close();self.service.pool.shutdown(wait=True);self.app.processEvents();self.directory.cleanup()
    def until(self,condition):
        end=time.monotonic()+3
        while not condition() and time.monotonic()<end:self.app.processEvents();time.sleep(.001)
        self.assertTrue(condition())

    def test_launch_and_expiry_refresh_one_generation_without_item_calls(self):
        with patch('price_lens.service.load_catalog',return_value=object()),patch('price_lens.snapshot_updater.SnapshotFetcher.start') as browser,patch('price_lens.data.get_json',side_effect=AssertionError('Individual HTTP call')):
            self.service.refresh_snapshot=True;self.service.set_refresh_interval(300);self.service.start()
            self.until(lambda:browser.call_count==1)
            self.service.snapshot_updater.accept(document(self.now))
            for _ in range(500):self.service.observe([self.item,Item(9999999,'Missing item')],300)
            self.assertEqual(browser.call_count,1)
            self.assertEqual(self.service.delivered[self.item.game_id].price,100)
            self.assertIsNone(self.service.delivered[9999999].price)
            self.assertEqual(self.service.snapshot_updater.timer.interval(),300000)
            self.service.snapshot_updater.timer.timeout.emit()
            self.assertEqual(browser.call_count,2)
            self.service.snapshot_updater.refresh();self.assertEqual(browser.call_count,2)

    def test_expired_prices_cannot_gain_freshness_from_repeated_views(self):
        quote=self.service.cached(self.item)
        with patch('price_lens.service.time.time',return_value=self.now+901),patch('price_lens.data.get_json',side_effect=AssertionError('Individual HTTP call')):
            for _ in range(500):self.service.observe([self.item],900)
        shown=self.service.delivered[self.item.game_id]
        self.assertEqual(shown.fetched_at,quote.fetched_at)
        self.assertFalse(shown.cache_valid(self.now+901,900))
        self.assertEqual(compare(self.item,1,10,shown,self.now+901,900).tone,'muted')

    def test_manual_search_and_saved_watch_references_share_the_snapshot(self):
        with patch('price_lens.data.get_json',side_effect=AssertionError('Individual HTTP call')):
            self.service.set_manual(self.item,900);self.service.clear_visible()
            self.assertEqual(self.service.delivered[self.item.game_id],self.service.cached(self.item))
            self.service.set_manual(None)

    def test_snapshot_identity_is_exact_and_missing_identity_does_not_fetch(self):
        ready=[];errors=[];self.service.identity_ready.connect(lambda identity,item:ready.append(item.game_id))
        self.service.identity_error.connect(lambda *_:errors.append(True))
        candidates=(self.item,Item(4010001,'Bronze Ore'))
        with patch('price_lens.data.get_json',side_effect=AssertionError('Individual HTTP call')):
            self.service.resolve_identity(('Bronze Ore',None),candidates)
            for _ in range(500):self.service.resolve_identity(('Missing',None),(Item(999,'Missing'),))
        self.assertEqual(ready,[self.item.game_id]);self.assertEqual(len(errors),1)

    def test_catalog_transient_failure_retries_once_then_stops_until_manual_retry(self):
        self.service.catalog_retry_timer.setInterval(1)
        errors=[]
        self.service.error.connect(lambda identity,message:errors.append((identity,message)))
        with patch('price_lens.service.load_catalog',side_effect=TimeoutError('temporary')) as fetch:
            self.service.start()
            self.until(lambda:len(errors)==2)
            for _ in range(100):self.app.processEvents();self.service.observe([],900)
            self.assertEqual(fetch.call_count,2)
            self.assertFalse(self.service.catalog_retry_timer.isActive())
            self.service.start()
            self.until(lambda:len(errors)==4)
            self.assertEqual(fetch.call_count,4)

    def test_catalog_retry_can_recover_and_format_errors_are_not_retried(self):
        self.service.catalog_retry_timer.setInterval(1)
        ready=[]
        self.service.catalog_ready.connect(ready.append)
        catalog=object()
        with patch('price_lens.service.load_catalog',side_effect=[TimeoutError('temporary'),catalog]) as fetch:
            self.service.start();self.until(lambda:bool(ready))
            self.assertIs(ready[0],catalog)
            self.assertEqual(fetch.call_count,2)
        errors=[];self.service.error.connect(lambda *_:errors.append(True))
        with patch('price_lens.service.load_catalog',side_effect=ValueError('changed format')) as fetch:
            self.service.start();self.until(lambda:bool(errors))
            self.assertFalse(self.service.catalog_retry_timer.isActive())
            self.assertEqual(fetch.call_count,1)
