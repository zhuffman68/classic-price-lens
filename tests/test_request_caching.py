"""Repeated item reads cannot create price HTTP requests, including cache misses."""
import os,time,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from price_lens.domain import Item
from price_lens.service import PriceService
from test_snapshot import document

class RequestCachingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen');cls.app=QApplication.instance() or QApplication([])
    def test_missing_empty_old_and_unchanged_reads_make_no_item_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            service=PriceService(Path(directory)/'prices.sqlite');now=time.time();replies=[]
            service.quote_ready.connect(lambda identity,quote:replies.append(identity))
            try:
                service.snapshot.save(document(now),now)
                with patch('price_lens.data.get_json',side_effect=AssertionError('Individual price request')):
                    for _ in range(1000):
                        service.request(Item(4010000,'Bronze Ore'),300)
                        service.request(Item(9999999,'Missing'),300)
                self.assertEqual(service.delivered[4010000].price,100)
                self.assertIsNone(service.delivered[9999999].price)
                self.assertEqual(replies,[4010000,9999999])
            finally:service.close();service.pool.shutdown(wait=True)
