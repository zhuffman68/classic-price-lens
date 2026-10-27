"""Manual search must stay local until an item is explicitly selected."""
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication,QEvent
from PySide6.QtWidgets import QApplication

from price_lens.domain import Catalog,Item,Quote
from price_lens.search import PriceSearch
from price_lens.service import PriceService


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
        with tempfile.TemporaryDirectory() as directory:
            service=PriceService(Path(directory)/"prices.sqlite")
            calls=[]
            now=time.time()
            def fetch(item):
                calls.append(item.game_id)
                return Quote(item.game_id,500,now,now,20,"NiaMeowDB","","24h")
            service.provider.fetch=fetch
            try:
                service.set_manual(self.catalog.items[0],900)
                deadline=time.monotonic()+3
                while (service.pending or service.identity_pending) and time.monotonic()<deadline:
                    self.app.processEvents();time.sleep(.001)
                self.assertFalse(service.pending)
                for _ in range(500):service.clear_visible()
                self.assertEqual(calls,[1])
                with patch("price_lens.service.time.time",return_value=now+901):
                    service.clear_visible()
                    deadline=time.monotonic()+3
                    while service.pending and time.monotonic()<deadline:
                        self.app.processEvents();time.sleep(.001)
                self.assertEqual(calls,[1,1],"Expired manual prices must refresh without screen demand")
                service.set_manual(None)
                self.assertFalse(service._queued)
            finally:
                service.close();service.pool.shutdown(wait=True)

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

    def test_manual_name_resolution_and_quote_share_the_existing_scheduler(self):
        with tempfile.TemporaryDirectory() as directory:
            service=PriceService(Path(directory)/"prices.sqlite")
            calls=[]
            candidates=(Item(10,"Blue Hawkeye"),Item(20,"Blue Hawkeye"))
            def resolve(name, choices):
                calls.append(('identity',name));return choices[1]
            def fetch(item):
                calls.append(('quote',item.game_id))
                return Quote(item.game_id,500,time.time(),time.time(),20,"NiaMeowDB","","24h")
            service.provider.resolve_name=resolve
            service.provider.fetch=fetch
            service.identity_ready.connect(lambda identity,item:service.set_manual(item))
            try:
                service.set_manual(None,identity=("Blue Hawkeye",None),candidates=candidates)
                deadline=time.monotonic()+3
                while (service.pending or service.identity_pending) and time.monotonic()<deadline:
                    self.app.processEvents();time.sleep(.001)
                self.assertEqual(calls,[('identity','Blue Hawkeye'),('quote',20)])
                for _ in range(500):service.clear_visible()
                self.assertEqual(len(calls),2)
            finally:
                service.close();service.pool.shutdown(wait=True)

    def test_manual_identity_failure_obeys_the_selected_cooldown(self):
        with tempfile.TemporaryDirectory() as directory:
            service=PriceService(Path(directory)/"prices.sqlite")
            calls=[];errors=[]
            def resolve(name, choices):
                calls.append(name);raise ValueError('No unique current match')
            service.provider.resolve_name=resolve
            service.identity_error.connect(lambda identity,message:errors.append(message))
            try:
                service.set_manual(None,identity=("Blue Hawkeye",None),candidates=(Item(10,"Blue Hawkeye"),))
                deadline=time.monotonic()+3
                while (service.pending or service.identity_pending) and time.monotonic()<deadline:
                    self.app.processEvents();time.sleep(.001)
                for _ in range(500):service.clear_visible()
                self.assertEqual(calls,['Blue Hawkeye'])
                self.assertEqual(errors,['No unique current match'])
            finally:
                service.close();service.pool.shutdown(wait=True)


if __name__ == "__main__":unittest.main()
