"""Static image caching against an isolated HTTP server; no public network calls."""
from collections import Counter
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import os,tempfile,threading,time,unittest
from PySide6.QtCore import QBuffer,QIODevice
from PySide6.QtGui import QImage,QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from price_lens.domain import Item
from price_lens.thumbnails import ThumbnailCache,decode,source_url


class ThumbnailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen');cls.app=QApplication.instance() or QApplication([])
        image=QImage(32,32,QImage.Format.Format_RGBA8888);image.fill(QColor('#d9ad66'))
        buffer=QBuffer();buffer.open(QIODevice.OpenModeFlag.WriteOnly);image.save(buffer,'PNG');cls.png=bytes(buffer.data())

    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.calls=Counter();calls=self.calls;png=self.png
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                calls[self.path]+=1
                data=png if not self.path.endswith('00000009.png') else b'not found'
                self.send_response(200 if data==png else 404);self.end_headers()
                try:self.wfile.write(data)
                except BrokenPipeError:pass
            def log_message(self,*args):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.cache=ThumbnailCache(Path(self.folder.name),base_url=f'http://127.0.0.1:{self.server.server_port}/')

    def tearDown(self):
        self.cache.close();self.cache.deleteLater();self.app.processEvents()
        self.server.shutdown();self.server.server_close();self.thread.join();self.folder.cleanup()

    def wait(self,predicate):
        deadline=time.monotonic()+5
        while not predicate():
            self.assertLess(time.monotonic(),deadline);QTest.qWait(5)

    def test_exact_game_id_cache_avoids_repeated_or_restart_requests(self):
        item=Item(1302000,'Sword');self.cache.observe([item]);self.wait(lambda:not self.cache.active)
        self.assertFalse(self.cache.image(item.game_id).isNull())
        for _ in range(100):self.cache.observe([item])
        self.assertEqual(sum(self.calls.values()),1)
        other=ThumbnailCache(Path(self.folder.name),base_url=f'http://127.0.0.1:{self.server.server_port}/')
        try:
            other.observe([item]);self.assertFalse(other.image(item.game_id).isNull());self.assertFalse(other.active)
            self.assertEqual(sum(self.calls.values()),1)
        finally:other.close();other.deleteLater()

    def test_missing_images_keep_the_negative_cache_for_its_full_interval(self):
        item=Item(9,'Missing');self.cache.observe([item]);self.wait(lambda:not self.cache.active)
        for _ in range(100):self.cache.observe([item])
        self.assertEqual(sum(self.calls.values()),1);self.assertTrue(self.cache.image(9).isNull())

    def test_only_two_requests_run_and_a_changed_query_discards_queued_images(self):
        self.cache.observe([Item(i,str(i)) for i in range(1,11)])
        self.assertEqual(len(self.cache.active),2)
        self.cache.observe([]);self.assertFalse(self.cache.queue)
        self.wait(lambda:not self.cache.active);self.assertEqual(sum(self.calls.values()),2)

    def test_source_and_decoder_reject_non_item_ids_and_oversize_inputs(self):
        self.assertEqual(source_url(1302000),'https://osmsdataexplorer.com/data/current/images/items/01302000.png')
        for value in (-1,True,'1302000'):
            with self.assertRaises(ValueError):source_url(value)
        self.assertTrue(decode(b'<svg>not an item</svg>').isNull())
        huge=bytearray(self.png);huge[16:20]=(4000).to_bytes(4,'big');self.assertTrue(decode(huge).isNull())
