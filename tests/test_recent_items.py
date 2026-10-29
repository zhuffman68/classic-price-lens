"""Session history stays bounded and does not become a price-request queue."""
import tempfile,time,unittest
from PySide6.QtCore import Qt,QCoreApplication,QEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from price_lens.domain import Catalog,Quote
from price_lens.recent_items import RecentItems


class RecentItemsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.catalog=Catalog({'items':[dict(id=n,name=f'Item {n}') for n in range(1,121)]})
        self.panel=RecentItems(limit=100);self.panel.resize(460,350);self.panel.show()
        self.market=type('CachedMarket',(),{'cached':lambda this,item:None})();self.now=time.time()

    def tearDown(self):
        self.panel.close();self.panel.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.app.processEvents()

    def see(self,identity):self.panel.observe([dict(name=f'Item {identity}',price=dict(mesos=1000,quantity=1))],self.catalog,self.now)

    def test_repeated_frames_update_one_entry_and_oldest_entries_are_evicted(self):
        for _ in range(1000):self.see(1)
        self.assertEqual(len(self.panel.entries),1)
        for identity in range(2,121):self.see(identity)
        self.assertEqual(len(self.panel.entries),100);self.assertNotIn(1,self.panel.entries)
        self.panel.observe([],self.catalog,self.now);self.panel.refresh(self.market,900,self.now);self.app.processEvents()
        self.assertEqual(self.panel.rows.count(),100);self.assertLessEqual(len(self.panel.visible_items()),6)

    def test_item_remains_after_leaving_the_screen_and_click_selects_exact_identity(self):
        self.see(1);self.panel.refresh(self.market,900,self.now);self.assertTrue(self.panel.isHidden())
        self.panel.observe([],self.catalog,self.now);self.panel.refresh(self.market,900,self.now);self.app.processEvents()
        self.assertFalse(self.panel.isHidden());self.assertEqual(self.panel.rows.count(),1)
        chosen=[];self.panel.chosen.connect(chosen.append);row=self.panel.rows.item(0)
        QTest.mouseClick(self.panel.rows.viewport(),Qt.MouseButton.LeftButton,pos=self.panel.rows.visualItemRect(row).center())
        self.assertEqual(chosen[0].game_id,1)

    def test_history_is_session_only_and_clear_does_not_leave_hidden_entries(self):
        self.see(1);other=RecentItems();self.assertEqual(len(other.entries),0);other.deleteLater()
        self.panel.clear();self.assertFalse(self.panel.entries);self.assertEqual(self.panel.rows.count(),0)

    def test_latest_reference_repaints_without_moving_rows_or_creating_price_requests(self):
        self.see(1);self.panel.observe([],self.catalog,self.now)
        quote=Quote(1,1000,self.now,self.now,10,'MesoWatch','','24h')
        self.market.cached=lambda item:quote;self.panel.refresh(self.market,900,self.now);row=self.panel.rows.item(0)
        quote=Quote(1,2500,self.now,self.now,20,'MesoWatch','','24h');self.panel.refresh(self.market,900,self.now)
        self.assertIs(self.panel.rows.item(0),row);self.assertEqual(row.data(Qt.ItemDataRole.UserRole+1),2500)
