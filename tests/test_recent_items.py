"""Session history stays bounded and does not become a price-request queue."""
import tempfile,time,unittest
from PySide6.QtCore import Qt,QCoreApplication,QEvent,QPoint,QObject
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
        QTest.qWait(190)
        chosen=[];self.panel.chosen.connect(chosen.append);row=self.panel.rows.item(0)
        QTest.mouseClick(self.panel.rows.viewport(),Qt.MouseButton.LeftButton,pos=self.panel.rows.visualItemRect(row).center())
        self.assertEqual(chosen[0].game_id,1)

    def test_history_is_session_only_and_clear_does_not_leave_hidden_entries(self):
        self.see(1);other=RecentItems();self.assertEqual(len(other.entries),0);other.deleteLater()
        self.panel.clear();self.assertFalse(self.panel.entries);self.assertEqual(self.panel.rows.count(),0)

    def test_partial_shop_and_tooltip_reads_keep_the_last_valid_asking_price(self):
        self.see(1)
        for price in (None,dict(mesos=None,quantity=1),dict(mesos=10,quantity=None)):
            self.panel.observe([dict(name='Item 1',price=price)],self.catalog,self.now+1)
            self.assertEqual(self.panel.entries[1]['price'],dict(mesos=1000,quantity=1))
        self.panel.observe([dict(name='Item 1',price=dict(mesos=1200,quantity=1))],self.catalog,self.now+2)
        self.assertEqual(self.panel.entries[1]['price']['mesos'],1200)

    def test_latest_reference_repaints_without_moving_rows_or_creating_price_requests(self):
        self.see(1);self.panel.observe([],self.catalog,self.now)
        quote=Quote(1,1000,self.now,self.now,10,'MesoWatch','','24h')
        self.market.cached=lambda item:quote;self.panel.refresh(self.market,900,self.now);row=self.panel.rows.item(0)
        quote=Quote(1,2500,self.now,self.now,20,'MesoWatch','','24h');self.panel.refresh(self.market,900,self.now)
        self.assertIs(self.panel.rows.item(0),row);self.assertEqual(row.data(Qt.ItemDataRole.UserRole+1),2500)

    def test_history_row_stays_visible_through_repeated_sightings_and_ocr_misses(self):
        self.see(1);self.panel.observe([],self.catalog,self.now);self.panel.refresh(self.market,900,self.now)
        row=self.panel.rows.item(0)
        for observations in ([{'name':'Item 1'}],[],[{'name':'Item 1'}],[]):
            self.now+=1;self.panel.observe(observations,self.catalog,self.now);self.panel.refresh(self.market,900,self.now)
            self.assertIs(self.panel.rows.item(0),row);self.assertFalse(self.panel.isHidden())

    def test_new_price_animation_does_not_rewind_an_unchanged_history_price(self):
        self.app.setProperty('reduceMotion',False);self.app.processEvents()
        quotes={1:Quote(1,1000,self.now,self.now,10,'MesoWatch','','24h')}
        self.market.cached=lambda item:quotes.get(item.game_id)
        self.see(1);self.panel.observe([],self.catalog,self.now);self.panel.refresh(self.market,900,self.now)
        self.panel.animation.setCurrentTime(160)
        quotes[1]=Quote(1,2500,self.now,self.now,10,'MesoWatch','','24h')
        self.panel.refresh(self.market,900,self.now);self.panel.animation.setCurrentTime(160)
        old=self.panel.rolls[1];self.assertEqual(old.progress,1)
        quotes[2]=Quote(2,3000,self.now,self.now,10,'MesoWatch','','24h')
        self.see(2);self.panel.observe([],self.catalog,self.now);self.panel.refresh(self.market,900,self.now)
        self.panel.animation.setCurrentTime(40)
        self.assertEqual(old.progress,1);self.assertNotIn(1,self.panel.animating)

    def test_inserted_row_fades_in_while_old_rows_slide_and_height_grows(self):
        self.app.setProperty('reduceMotion',False)
        self.see(1);self.panel.observe([],self.catalog,self.now);self.panel.refresh(self.market,900,self.now)
        self.panel.geometry_animation.setCurrentTime(180);self.app.processEvents()
        old=self.panel.rows_by_id[1];start=self.panel.rows.visualItemRect(old).top();height=self.panel.height()
        self.see(2);self.panel.observe([],self.catalog,self.now);self.panel.refresh(self.market,900,self.now)
        new=self.panel.rows_by_id[2]
        self.assertEqual(self.panel.rows.visualItemRect(old).top(),start);self.assertEqual(self.panel.rows.opacity(new),0)
        self.panel.geometry_animation.setCurrentTime(90)
        self.assertTrue(start<self.panel.rows.visualItemRect(old).top()<start+59)
        self.assertTrue(0<self.panel.rows.opacity(new)<1)
        self.assertTrue(height<self.panel.height()<height+59)
        self.panel.geometry_animation.setCurrentTime(180)
        self.assertEqual(self.panel.rows.visualItemRect(old).top(),start+59);self.assertEqual(self.panel.rows.opacity(new),1)

    def test_insertion_preserves_the_visible_scroll_anchor(self):
        for identity in range(1,9):self.see(identity)
        self.panel.observe([],self.catalog,self.now);self.panel.refresh(self.market,900,self.now)
        self.panel.geometry_animation.setCurrentTime(180);self.app.processEvents()
        self.panel.rows.verticalScrollBar().setValue(100)
        anchor=self.panel.rows.itemAt(QPoint(8,2));top=self.panel.rows.visualItemRect(anchor).top()
        self.see(9);self.panel.observe([],self.catalog,self.now);self.panel.refresh(self.market,900,self.now)
        self.assertEqual(self.panel.rows.visualItemRect(anchor).top(),top)
        self.panel.geometry_animation.setCurrentTime(90);self.assertEqual(self.panel.rows.visualItemRect(anchor).top(),top)
        self.panel.geometry_animation.setCurrentTime(180);self.assertEqual(self.panel.rows.visualItemRect(anchor).top(),top)

    def test_reference_refresh_does_not_restart_row_motion_and_number_repaints_are_local(self):
        self.app.setProperty('reduceMotion',False)
        for identity in range(1,7):self.see(identity)
        self.panel.observe([],self.catalog,self.now);self.panel.refresh(self.market,900,self.now)
        self.panel.geometry_animation.setCurrentTime(70)
        quote=Quote(6,2000,self.now,self.now,10,'MesoWatch','','24h')
        self.market.cached=lambda item:quote if item.game_id==6 else None
        self.panel.refresh(self.market,900,self.now)
        self.assertEqual(self.panel.geometry_animation.currentTime(),70)
        self.panel.geometry_animation.setCurrentTime(180);self.panel.animation.setCurrentTime(160);self.app.processEvents()
        regions=[]
        class Paints(QObject):
            def eventFilter(self,watched,event):
                if event.type()==QEvent.Type.Paint:regions.append(event.region().boundingRect())
                return False
        observer=Paints(self.panel);self.panel.rows.viewport().installEventFilter(observer)
        self.panel.animating={6};self.panel.advance(.5);self.app.processEvents()
        self.assertTrue(regions)
        self.assertTrue(all(rect.height()<=59 for rect in regions),regions)

    def test_reduced_motion_settles_an_in_progress_history_insertion(self):
        self.app.setProperty('reduceMotion',False);self.see(1)
        self.panel.observe([],self.catalog,self.now);self.panel.refresh(self.market,900,self.now)
        self.panel.geometry_animation.setCurrentTime(50);self.assertTrue(self.panel.rows.motion)
        self.app.setProperty('reduceMotion',True);self.panel.advance_geometry(.5)
        self.assertFalse(self.panel.rows.motion);self.assertEqual(self.panel.rows.height(),61)
        self.app.setProperty('reduceMotion',False)
