"""Measure the actual Prices layout while search returns to retained cards."""
import unittest
from PySide6.QtCore import QAbstractAnimation,QPoint,Qt
from PySide6.QtTest import QTest
import test_ui_context as fixtures


class SearchReturnMotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.ContextUiTests.setUpClass.__func__(cls)

    def setUp(self):
        fixtures.ContextUiTests.setUp(self)
        self.app.setProperty('reduceMotion',True)
        self.window.resize(520,840);self.window.show();self.app.processEvents()

    def tearDown(self):
        fixtures.ContextUiTests.tearDown(self)
        self.app.setProperty('reduceMotion',False)

    def content_y(self):
        return self.window.price_content.mapTo(self.window.prices_page,QPoint()).y()

    def prepare(self,context,selected=False,query='Example'):
        w=self.window;p=w.search_panel
        if context!='ready':w.on_reading(fixtures.ContextUiTests.reading(self,context=='shop'))
        self.app.processEvents();base=self.content_y();cards=dict(w.card_views)
        p.query.setText(query);p.timer.stop();p.find_items()
        if selected:p.choose_first()
        self.app.processEvents();self.app.setProperty('reduceMotion',False)
        return base,cards

    def clear(self,method):
        p=self.window.search_panel
        if method=='button':QTest.mouseClick(p.query.clear_button,Qt.MouseButton.LeftButton)
        else:
            p.query.setCursorPosition(len(p.query.text()))
            while p.query.text():QTest.keyClick(p.query,Qt.Key.Key_Backspace)

    def assert_return_geometry(self,base,cards):
        p=self.window.search_panel;positions=[]
        self.assertFalse(p.timer.isActive())
        animation=p.results_area.animation
        # Sampling explicit times must not race the real timer in a slow VM.
        animation.pause()
        for ms in (0,16,32,48,64,80,96,112,130):
            if ms==130:
                if animation.state()==QAbstractAnimation.State.Paused:animation.resume()
                elif animation.state()==QAbstractAnimation.State.Stopped:animation.start()
            animation.setCurrentTime(ms);self.app.processEvents()
            positions.append(self.content_y())
        self.assertGreater(positions[0],base)
        self.assertGreater(len(set(positions)),3)
        self.assertEqual(positions,sorted(positions,reverse=True))
        self.assertEqual(positions[-1],base)
        # This exceeds the old debounce deadline and catches both the delayed
        # count removal and the final layout-spacing jump from the real fixture.
        QTest.qWait(230);self.assertEqual(self.content_y(),base)
        self.assertEqual(self.window.card_views,cards)
        self.assertFalse(self.window.scroll.isHidden())
        self.assertIsNone(self.window.price_content.outgoing)
        self.assertEqual(self.window.reader.starts,0)

    def test_backspace_returns_to_shop_without_a_late_layout_step(self):
        base,cards=self.prepare('shop');self.clear('backspace');self.assert_return_geometry(base,cards)

    def test_clear_button_returns_to_inventory_without_a_late_layout_step(self):
        base,cards=self.prepare('inventory');self.clear('button');self.assert_return_geometry(base,cards)

    def test_selected_card_clear_returns_to_shop_in_one_transition(self):
        base,cards=self.prepare('shop',True);self.clear('button');self.assert_return_geometry(base,cards)

    def test_empty_result_clear_returns_to_ready_in_one_transition(self):
        base,cards=self.prepare('ready',query='Not an item');self.clear('backspace');self.assert_return_geometry(base,cards)

    def test_clear_and_retype_retargets_without_losing_retained_cards(self):
        base,cards=self.prepare('shop');p=self.window.search_panel
        self.clear('button');p.results_area.animation.pause();p.results_area.animation.setCurrentTime(55);self.app.processEvents()
        mid_height=p.results_area.height()
        p.query.setText('Example');p.timer.stop();p.find_items();p.results_area.animation.pause();self.app.processEvents()
        self.assertEqual(p.results_area.height(),mid_height)
        self.assertIsNone(p.selected);self.assertTrue(self.window.scroll.isHidden())
        p.results_area.animation.resume();p.results_area.animation.setCurrentTime(130);self.app.processEvents()
        self.assertEqual(p.results.count(),1);self.assertIn('1 matches',p.hint.text())
        self.assertEqual(self.window.card_views,cards)
        self.clear('backspace');self.assert_return_geometry(base,cards)

    def test_reduced_motion_clear_is_complete_without_pending_geometry(self):
        base,cards=self.prepare('shop',True);self.app.setProperty('reduceMotion',True)
        self.clear('button');self.app.processEvents()
        self.assertEqual(self.content_y(),base);self.assertEqual(self.window.card_views,cards)
        self.assertEqual(self.window.search_panel.results_area.height(),0)
        self.assertIsNone(self.window.search_panel.results_area.outgoing)

    def test_clearing_keeps_outgoing_row_pixels_until_the_animation_finishes(self):
        self.prepare('shop');p=self.window.search_panel
        before=p.results_area.grab().toImage()
        self.clear('button')
        self.assertIsNotNone(p.results_area.outgoing)
        self.assertEqual(p.results_area.outgoing.before.toImage(),before)
        p.results_area.animation.pause();p.results_area.animation.setCurrentTime(65);self.app.processEvents()
        self.assertGreater(p.results_area.height(),0)
        self.assertFalse(p.results_area.outgoing.grab().toImage().isNull())


if __name__=='__main__':unittest.main()
