"""Exercise card retention and real intermediate geometry without screen capture."""
import unittest
import os
from PySide6.QtCore import QCoreApplication,QEvent,QPoint,Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication,QLabel,QVBoxLayout,QWidget
from price_lens.motion import CardArea,ContentArea
from price_lens.recent_items import ActiveCards


def title(name,y=0,**extra):
    return dict(name=name,area=dict(x=0,y=y,width=200,height=18),**extra)


class PriceMotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.app.setProperty('reduceMotion',False);self.window=QWidget();self.window.resize(460,600)
        self.layout=QVBoxLayout(self.window);self.layout.setContentsMargins(0,0,0,0);self.layout.setSpacing(10)
        self.area=CardArea(self.window);self.layout.addWidget(self.area)
        self.cards=QVBoxLayout(self.area.content);self.cards.setContentsMargins(0,0,0,0)
        self.history=QLabel('Live history sibling');self.history.setFixedHeight(59);self.layout.addWidget(self.history)
        self.layout.addStretch();self.window.show();self.app.processEvents()

    def tearDown(self):
        self.window.close();self.window.deleteLater();self.app.setProperty('reduceMotion',False)
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.app.processEvents()

    def add_card(self,height):
        card=QLabel('Card');card.setFixedHeight(height);self.cards.addWidget(card);card.show();return card

    def test_missing_card_is_held_at_1999_ms_and_retires_at_two_seconds(self):
        state=ActiveCards(self.window);a=title('A')
        self.assertEqual(state.observe([],a,now=99),[(a,True)])
        state.observe([],None,now=100)
        self.assertEqual(state.observe([],None,now=101.999),[(a,True)])
        self.assertEqual(state.observe([],None,now=102),[])
        self.assertFalse(state.timer.isActive())

    def test_replacement_before_deadline_does_not_visit_an_empty_state(self):
        state=ActiveCards(self.window);a,b=title('A'),title('B')
        state.observe([],a,now=99);state.observe([],None,now=100)
        self.assertEqual(state.observe([],b,now=100.8),[(b,True)])
        self.assertFalse(state.timer.isActive())
        self.assertEqual(state.observe([],b,now=101),[(b,True)])

    def test_replacement_across_contexts_cancels_only_the_missing_card(self):
        for first_hovered in (False,True):
            state=ActiveCards(self.window);a,b=title('A'),title('B')
            state.observe([] if first_hovered else [a],a if first_hovered else None,now=99)
            state.observe([],None,now=100)
            self.assertEqual(state.observe([b] if first_hovered else [],None if first_hovered else b,now=100.8),[(b,not first_hovered)])
        state=ActiveCards(self.window);state.observe([b],a,now=99)
        self.assertEqual(state.observe([b],None,now=100),[(a,True),(b,False)])

    def test_verified_partial_page_retains_only_the_missing_slot_and_real_page_changes_clear_it(self):
        state=ActiveCards(self.window)
        a=title('A',0,shop_page=1,shop_slot=(0,0,200,18));b=title('B',60,shop_page=1,shop_slot=(0,60,200,18))
        state.observe([a,b],None,now=99,page=1,context=0)
        self.assertEqual(state.observe([b],None,now=100,page=1,context=0),[(a,False),(b,False)])
        self.assertEqual(len(state.observe([b],None,now=101.999,page=1,context=0)),2)
        self.assertEqual(state.observe([b],None,now=102,page=1,context=0),[(b,False)])
        state.observe([],None,now=101,page=1,context=0)
        self.assertEqual(state.observe([],None,now=101.1,page=2,context=0),[])
        state.observe([],a,now=102,page=2,context=0)
        self.assertEqual(state.observe([],None,now=102.1,page=2,context=1),[])

    def test_existing_shop_reorder_or_omission_cannot_cancel_hover_grace(self):
        state=ActiveCards(self.window);a,b,c=title('A'),title('B'),title('C')
        state.observe([a,b],c,now=99)
        self.assertIn((c,True),state.observe([b,a],None,now=100))
        self.assertIn((c,True),state.observe([b],None,now=101.999))
        self.assertNotIn((c,True),state.observe([b],None,now=102))

    def test_unreadable_verified_slot_keeps_its_gui_identity_for_only_two_seconds(self):
        state=ActiveCards(self.window)
        previous=title('A',0,shop_page=1,shop_slot=(0,0,200,18));missing={**previous,'name':None,'price':None}
        state.observe([previous],None,now=99,page=1)
        self.assertEqual(state.observe([missing],None,now=100,page=1),[(previous,False)])
        self.assertEqual(state.observe([missing],None,now=101.999,page=1),[(previous,False)])
        self.assertEqual(state.observe([missing],None,now=102,page=1),[(missing,False)])
        self.assertIsNone(missing['name']);self.assertIsNone(missing['price'])

    def test_unknown_shop_read_and_equivalent_spelling_do_not_cancel_inventory_grace(self):
        state=ActiveCards(self.window);a=title('Hat');b=title('Cape');alias=title('HAT')
        resolve=lambda row:1 if (row.get('name') or '').lower()=='hat' else 2 if row.get('name')=='Cape' else None
        state.observe([a],b,now=99,identity=resolve)
        self.assertIn((b,True),state.observe([alias],None,now=100,identity=resolve))
        self.assertIn((b,True),state.observe([title(None)],None,now=101,identity=resolve))

    def test_nested_empty_card_layout_does_not_reuse_a_cached_height(self):
        wrapper=QWidget();nested=QVBoxLayout(wrapper);nested.setContentsMargins(0,0,0,0)
        card=QLabel('Outgoing');card.setFixedHeight(120);nested.addWidget(card);self.cards.addWidget(wrapper)
        self.area.begin();wrapper.show();card.show();self.area.complete();self.area.animation.setCurrentTime(180)
        self.assertEqual(self.area.full_height,120)
        self.area.begin();nested.removeWidget(card);card.hide();card.deleteLater()
        self.area.complete()
        self.assertEqual(self.area.full_height,0)
        self.area.animation.setCurrentTime(180);self.assertEqual(self.area.height(),0)

    def test_first_card_moves_history_continuously_from_a_zero_height_region(self):
        start=self.history.mapTo(self.window,QPoint()).y();self.area.begin();self.add_card(120);self.area.complete()
        self.assertIsNotNone(self.area.outgoing);self.assertEqual(self.area.height(),0)
        self.area.animation.setCurrentTime(90);self.app.processEvents()
        self.assertGreater(self.area.height(),0);self.assertLess(self.area.height(),120)
        halfway=self.history.mapTo(self.window,QPoint()).y()
        self.assertGreater(halfway,start);self.assertLess(halfway,start+120)
        self.area.animation.setCurrentTime(180);self.app.processEvents()
        self.assertEqual(self.area.height(),120);self.assertEqual(self.history.mapTo(self.window,QPoint()).y(),start+120)

    def test_interrupted_height_transition_restarts_at_its_current_height(self):
        self.area.begin();card=self.add_card(120);self.area.complete();self.area.animation.setCurrentTime(70)
        height=self.area.height();self.assertTrue(0<height<120)
        self.area.begin();self.assertEqual(self.area.start_height,height);self.assertEqual(self.area.height(),height)
        card.setFixedHeight(200);self.area.complete();self.area.animation.setCurrentTime(0)
        self.assertEqual(self.area.height(),height)
        self.area.animation.setCurrentTime(180);self.assertEqual(self.area.height(),200)

    def test_field_refresh_keeps_the_existing_transition_clock_and_snapshot(self):
        self.area.begin();card=self.add_card(120);self.area.complete();self.area.animation.setCurrentTime(70)
        outgoing=self.area.outgoing;height=self.area.height();card.setText('Fresh price')
        self.area.complete()
        self.assertIs(self.area.outgoing,outgoing);self.assertEqual(self.area.animation.currentTime(),70)
        self.assertEqual(self.area.height(),height);self.assertTrue(self.area.content.isHidden())
        self.area.animation.setCurrentTime(180);self.assertFalse(self.area.content.isHidden())

    def test_reduced_motion_immediately_disposes_pending_card_pixels(self):
        self.area.begin();self.add_card(120);self.area.complete();self.area.animation.setCurrentTime(70)
        self.app.setProperty('reduceMotion',True);self.area.complete()
        self.assertIsNone(self.area.outgoing);self.assertIsNone(self.area.before)
        self.assertEqual(self.area.height(),120);self.assertFalse(self.area.content.isHidden())

    def test_content_transition_has_visible_pixels_at_its_midpoint(self):
        region=ContentArea(self.window);region.setGeometry(0,0,180,90);region.setStyleSheet('background:black')
        layout=QVBoxLayout(region);label=QLabel('');label.setStyleSheet('background:#ee2222');layout.addWidget(label)
        region.show();self.app.processEvents();region.begin();label.setStyleSheet('background:#2222ee');region.complete()
        region.advance(.5);pixel=QColor(region.outgoing.grab().toImage().pixel(90,45))
        self.assertGreater(pixel.red(),40);self.assertGreater(pixel.blue(),40)

