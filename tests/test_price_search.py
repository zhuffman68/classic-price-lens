"""Manual search must stay local until an item is explicitly selected."""
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication,QEvent,QSettings,Qt,QPoint,QObject,Signal
from PySide6.QtGui import QImage,QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from price_lens.domain import Catalog,Item,Quote
from price_lens.search import PriceSearch
from price_lens.service import PriceService
from price_lens.watchlist import Watchlist


class PriceSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.panel = PriceSearch()
        self.catalog = Catalog({"items":[{"id":1,"name":"Work Gloves","category":"Equipment"},
            {"id":2,"name":"Brown Work Gloves","category":"Equipment"},
            {"id":3,"name":"Blue Bandana","category":"Equipment"}],"scrolls":[]})
        self.panel.set_catalog(self.catalog)
        self.requests = []
        self.panel.item_selected.connect(self.requests.append)

    def tearDown(self):
        self.panel.timer.stop()
        self.panel.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def search(self, query):
        self.panel.query.setText(query)
        self.panel.timer.stop()
        self.panel.find_items()

    def test_debounce_keeps_thumbnails_enabled_and_rejects_stale_selection(self):
        self.search('Work');self.assertGreater(self.panel.results.count(),1)
        self.panel.query.setText('Blue')
        self.assertTrue(self.panel.results.isEnabled())
        self.panel.results.setCurrentRow(0)
        self.assertIsNone(self.panel.selected)
        self.assertFalse(any(item for item in self.requests))
        self.panel.timer.stop();self.panel.find_items();self.panel.results.setCurrentRow(0)
        self.assertEqual(self.panel.selected.game_id,3)

    def test_typing_filters_names_without_price_requests(self):
        for query in ("w","wo","work","work gloves"):
            self.search(query)
        self.assertEqual(self.panel.results.count(),2)
        self.assertEqual(self.requests,[])
        self.panel.results.setCurrentRow(0)
        self.assertEqual([item.game_id for item in self.requests],[1])

    def test_empty_query_has_no_instruction_but_search_keeps_match_count(self):
        self.assertEqual(self.panel.hint.text(),'')
        self.search('Work')
        self.assertIn('2 matches',self.panel.hint.text())

    def test_inline_watches_request_only_on_selection_and_remove_without_lookup(self):
        with tempfile.TemporaryDirectory() as directory:
            watches=Watchlist(QSettings(str(Path(directory)/'settings.ini'),QSettings.Format.IniFormat))
            self.panel.set_watchlist(watches)
            watches.toggle(self.catalog.items[0]);watches.toggle(self.catalog.items[2])
            section=self.panel.watched_items
            self.assertEqual(section.rows.count(),2)
            self.assertEqual(self.requests,[])
            self.panel.resize(420,640);self.panel.show();self.app.processEvents()
            row=section.rows.item(0)
            identity=row.data(Qt.ItemDataRole.UserRole)
            point=section.rows.visualItemRect(row).center()
            QTest.mouseClick(section.rows.viewport(),Qt.MouseButton.LeftButton,pos=point)
            self.assertEqual(self.requests[-1].game_id,identity)
            self.assertGreaterEqual(self.panel.price_view.header.indexOf(self.panel.watch_button),0)
            self.assertTrue(self.panel.watch_button.isChecked())
            before=len([r for r in self.requests if r])
            rectangle=section.rows.visualItemRect(row)
            QTest.mouseClick(section.rows.viewport(),Qt.MouseButton.LeftButton,
                             pos=QPoint(rectangle.right()-12,rectangle.center().y()))
            self.assertNotIn(identity,watches.ids)
            self.assertEqual(len([r for r in self.requests if r]),before)
            self.assertEqual(section.rows.count(),1)
            self.assertFalse(self.panel.watch_button.isChecked())

    def test_watched_rows_reuse_cached_thumbnails_without_a_download_signal(self):
        class CachedImages(QObject):
            ready=Signal(int)
            def image(self,identity):
                image=QImage(16,16,QImage.Format.Format_RGBA8888);image.fill(QColor('#d9ad66'));return image
            def observe(self,items):self.items=list(items)
        with tempfile.TemporaryDirectory() as directory:
            watches=Watchlist(QSettings(str(Path(directory)/'settings.ini'),QSettings.Format.IniFormat))
            watches.toggle(self.catalog.items[0]);self.panel.set_watchlist(watches)
            store=CachedImages();self.panel.set_thumbnails(store)
            self.panel.resize(420,640);self.panel.show();self.panel.watched_items.set_expanded(True);self.app.processEvents();self.panel.request_thumbnails()
            image=self.panel.watched_items.rows.item(0).icon().pixmap(28,28).toImage()
            self.assertEqual(image.pixelColor(14,14),QColor('#d9ad66'))
            self.assertEqual(self.requests,[])

    def test_visible_ellipsis_and_hyphens_can_be_used_in_manual_search(self):
        self.panel.set_catalog(Catalog({'items':[{'id':1112223,'name':'Ink-and-Wash Painting Name Tag Ring'},
                                                {'id':1112227,'name':'Ink-and-Wash Thought Bubble Ring'}]}))
        self.search('Ink and Wash Painting N...')
        self.assertEqual(self.panel.results.count(),1)
        self.panel.results.setCurrentRow(0)
        self.assertEqual(self.requests[-1].game_id,1112223)


    def test_new_query_cancels_selection_and_late_quote_cannot_replace_it(self):
        self.search("work")
        self.panel.results.setCurrentRow(0)
        self.search("bandana")
        self.assertIsNone(self.requests[-1])
        self.panel.results.setCurrentRow(0)
        now=time.time()
        self.panel.accept_quote(1,Quote(1,500,now,now,20,"NiaMeowDB","","24h"))
        self.assertEqual(self.panel.selected.game_id,3)
        self.assertIsNone(self.panel.quote)

    def test_search_result_has_price_context_without_inventory_label(self):
        from PySide6.QtWidgets import QLabel
        self.search("bandana")
        self.panel.results.setCurrentRow(0)
        now=time.time()
        quote=Quote(3,500,now,now,20,"NiaMeowDB","","24h")
        self.panel.accept_quote(3,quote)
        labels=[widget.text() for widget in self.panel.detail.findChildren(QLabel)]
        self.assertIn("Classic World · market price",labels)
        self.assertNotIn("Inventory / equipment item",labels)

    def test_manual_demand_survives_no_screen_and_obeys_cache_ttl(self):
        from test_snapshot import document
        with tempfile.TemporaryDirectory() as directory:
            service=PriceService(Path(directory)/'prices.sqlite');now=time.time()
            doc=document(now);doc['items'][0].update(id='basil:00000001',name='Work Gloves')
            service.snapshot.save(doc,now)
            try:
                with patch('price_lens.data.get_json',side_effect=AssertionError('No individual lookups')):
                    service.set_manual(self.catalog.items[0],900)
                    for _ in range(500):service.clear_visible()
                    quote=service.delivered[1]
                    self.assertEqual(quote.price,100)
                    self.assertFalse(quote.cache_valid(now+901,900))
                    service.set_manual(None)
            finally:service.close();service.pool.shutdown(wait=True)

    def test_duplicate_names_resolve_current_item_before_requesting_price(self):
        self.panel.set_catalog(Catalog({"items":[{"id":10,"name":"Blue Hawkeye","category":"Equipment"},
                                                 {"id":20,"name":"Blue Hawkeye","category":"Equipment"}],"scrolls":[]}))
        identities=[]
        self.panel.identity_selected.connect(lambda identity,candidates:identities.append((identity,candidates)))
        self.search("Blue Hawkeye")
        self.assertEqual(self.panel.results.count(),1)
        self.panel.results.setCurrentRow(0)
        self.assertEqual(self.requests,[])
        self.assertEqual(len(identities),1)
        identity,candidates=identities[0]
        self.panel.accept_identity(identity,candidates[1])
        self.assertEqual(self.requests[-1].game_id,20)

    def test_reselecting_failed_name_keeps_error_during_cooldown(self):
        self.panel.set_catalog(Catalog({"items":[{"id":10,"name":"Blue Hawkeye"},{"id":20,"name":"Blue Hawkeye"}],"scrolls":[]}))
        self.search("Blue Hawkeye");self.panel.results.setCurrentRow(0)
        identity=self.panel.pending_identity
        self.panel.identity_error(identity,"No unique current match")
        self.panel.select_result(self.panel.results.item(0))
        self.assertEqual(self.panel.error,"No unique current match")

    def test_manual_name_resolution_and_quote_share_the_existing_snapshot(self):
        from test_snapshot import document
        with tempfile.TemporaryDirectory() as directory:
            service=PriceService(Path(directory)/'prices.sqlite');now=time.time()
            doc=document(now);doc['items'][0].update(id='basil:00000020',name='Blue Hawkeye')
            service.snapshot.save(doc,now)
            service.identity_ready.connect(lambda identity,item:service.set_manual(item))
            try:
                with patch('price_lens.data.get_json',side_effect=AssertionError('No individual lookups')):
                    service.set_manual(None,identity=('Blue Hawkeye',None),candidates=(Item(10,'Blue Hawkeye'),Item(20,'Blue Hawkeye')))
                    self.assertEqual(service.manual_item.game_id,20)
                    self.assertEqual(service.delivered[20].price,100)
            finally:service.close();service.pool.shutdown(wait=True)

    def test_manual_identity_failure_is_reported_once_per_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            service=PriceService(Path(directory)/'prices.sqlite');errors=[]
            service.identity_error.connect(lambda identity,message:errors.append(message))
            try:
                with patch('price_lens.data.get_json',side_effect=AssertionError('No individual lookups')):
                    service.set_manual(None,identity=('Blue Hawkeye',None),candidates=(Item(10,'Blue Hawkeye'),))
                    for _ in range(500):service.clear_visible()
                self.assertEqual(len(errors),1)
            finally:service.close();service.pool.shutdown(wait=True)


if __name__ == "__main__":unittest.main()
