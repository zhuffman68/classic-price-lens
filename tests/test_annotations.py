"""Only our own offscreen window and mocked OS pointer; no input is sent."""
import json
import os
import unittest
from unittest.mock import patch

from PySide6.QtCore import QPoint, QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication
from price_lens.annotations import AnnotationWindow


class AnnotationMotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = AnnotationWindow(start_listener=False)
        self.command = {"geometry": [0, 0, 800, 800], "hover_enabled": True, "rows": [
            {"x": 120, "y": 90, "name": "Example Hat", "key": 1, "text": "FM 1,000 mesos",
             "follow_pointer": [100, 100], "pointer_region": [0, 0, 800, 800]}]}
        with patch("price_lens.annotations.QCursor.pos", return_value=QPoint(100, 100)):
            self.window.read_command(json.dumps(self.command))

    def tearDown(self):
        self.window.pointer_timer.stop()
        self.window.watchdog.stop()
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def test_card_follows_pointer_without_a_new_reading_or_drawing_command(self):
        row = self.window.rows[0]
        before = self.window.label_rect(row, QPoint(100, 100))
        last_command = self.window.last_command
        with patch("price_lens.annotations.QCursor.pos", return_value=QPoint(108, 105)), patch("builtins.print"):
            self.window.report_pointer()
        after = self.window.label_rect(row, QPoint(108, 105))
        self.assertEqual((after.x() - before.x(), after.y() - before.y()), (8, 5))
        self.assertEqual(self.window.last_command, last_command)
        self.assertEqual(self.window.pointer_timer.interval(), 16)

    def test_watched_label_pulses_twice_then_stays_marked_without_restarting(self):
        row={**self.command['rows'][0],'watched':True,'watch_event':10,'color':'#86ceac'}
        self.window.read_command(json.dumps({**self.command,'rows':[row]}))
        active=self.window.rows[0];animation=active['_watch_pulse']
        for when, expected in ((400,1),(800,0),(1200,1)):
            animation.setCurrentTime(when)
            self.assertAlmostEqual(active['_watch_level'],expected,places=5)
        self.window.read_command(json.dumps({**self.command,'rows':[{**row,'text':'FM 1,200 mesos'}]}))
        self.assertIs(self.window.rows[0]['_watch_pulse'],animation)
        animation.setCurrentTime(1600)
        self.assertIsNone(active['_watch_pulse'])
        self.assertTrue(active['watched'])
        self.assertEqual(active['color'],'#86ceac')
        self.window.read_command(json.dumps({**self.command,'rows':[row]}))
        self.assertIsNone(self.window.rows[0]['_watch_pulse'])

    def test_short_missing_label_does_not_replay_the_same_watch_event(self):
        row={**self.command['rows'][0],'watched':True,'watch_event':20}
        self.window.read_command(json.dumps({**self.command,'rows':[row]}))
        self.window.read_command(json.dumps({**self.command,'rows':[],'hover_enabled':False}))
        self.window.read_command(json.dumps({**self.command,'rows':[row]}))
        self.assertIsNone(self.window.rows[0].get('_watch_pulse'))
        self.window.read_command(json.dumps({**self.command,'rows':[{**row,'watch_event':21}]}))
        self.assertIsNotNone(self.window.rows[0].get('_watch_pulse'))

    def test_reduce_motion_keeps_the_watch_marker_without_a_deferred_pulse(self):
        row={**self.command['rows'][0],'watched':True,'watch_event':30}
        self.window.read_command(json.dumps({**self.command,'rows':[row],'reduce_motion':True}))
        self.assertTrue(self.window.rows[0]['watched'])
        self.assertIsNone(self.window.rows[0].get('_watch_pulse'))
        self.window.read_command(json.dumps({**self.command,'rows':[row],'reduce_motion':False}))
        self.assertIsNone(self.window.rows[0].get('_watch_pulse'))

    def test_watched_shop_label_keeps_the_tooltip_occlusion_opacity(self):
        row={'x':120,'y':90,'name':'Example Hat','key':'shop:0:1','text':'FM 1,000 mesos',
             'kind':'shop','color':'#86ceac','watched':True,'watch_event':40,'obscured':True}
        self.window.read_command(json.dumps({**self.command,'rows':[row]}))
        active=self.window.rows[0]
        self.assertEqual(active['_target_alpha'],.25)
        pulse=active['_watch_pulse']
        self.window.read_command(json.dumps({**self.command,'rows':[row]}))
        self.assertIs(self.window.rows[0]['_watch_pulse'],pulse)
        self.assertEqual(self.window.rows[0]['_target_alpha'],.25)

    def test_cursor_jump_or_leaving_game_hides_the_old_reference(self):
        row = self.window.rows[0]
        self.assertIsNone(self.window.label_rect(row, QPoint(250, 250)))
        row["pointer_region"] = [95, 95, 10, 10]
        self.assertIsNone(self.window.label_rect(row, QPoint(110, 100)))

    def test_stationary_pointer_does_not_repaint(self):
        with patch("price_lens.annotations.QCursor.pos", return_value=QPoint(100, 100)), patch("builtins.print"):
            self.window.report_pointer()
            with patch.object(self.window, "update") as repaint:
                self.window.report_pointer()
            repaint.assert_not_called()

    def test_shop_label_positions_stay_fixed(self):
        row = {"x": 120, "y": 90, "_width": 230}
        self.assertEqual(self.window.label_rect(row, QPoint(100, 100)),
                         self.window.label_rect(row, QPoint(140, 130)))

    def test_inventory_card_has_a_short_fade_in_and_out(self):
        row = self.window.rows[0]
        row["_fade"].setCurrentTime(110)
        self.assertAlmostEqual(row["_alpha"], 1.0)
        with patch("price_lens.annotations.QCursor.pos", return_value=QPoint(100, 100)):
            self.window.read_command(json.dumps({**self.command, "rows": []}))
        self.assertIn(row, self.window.retiring)
        fade = row["_fade"]
        fade.setCurrentTime(45)
        self.assertGreater(row["_alpha"], 0.0)
        self.assertLess(row["_alpha"], 1.0)
        fade.setCurrentTime(90)
        self.assertNotIn(row, self.window.retiring)

    def test_shop_prices_fade_and_move_between_captured_positions(self):
        shop = {"x": 120, "y": 90, "name": "Example Hat", "key": "shop:0:1",
                "text": "FM 1,000 mesos", "animate_move": True}
        self.window.read_command(json.dumps({**self.command, "rows": [shop]}))
        row = self.window.rows[0]
        row["_fade"].setCurrentTime(110)
        self.assertAlmostEqual(row["_alpha"], 1.0)
        before = self.window.label_rect(row, QPoint(0, 0))
        shop = {**shop, "x": 160, "y": 130}
        self.window.read_command(json.dumps({**self.command, "rows": [shop]}))
        move = row["_move"]
        move.setCurrentTime(45)
        middle = self.window.label_rect(row, QPoint(0, 0))
        self.assertGreater(middle.x(), before.x())
        self.assertLess(middle.x(), 160)
        move.setCurrentTime(95)
        self.assertEqual(self.window.label_rect(row, QPoint(0, 0)).x(), 160)
        self.window.read_command(json.dumps({**self.command, "rows": []}))
        self.assertIn(row, self.window.retiring)
        row["_fade"].setCurrentTime(90)
        self.assertNotIn(row, self.window.retiring)

    def test_disabling_labels_clears_immediately_instead_of_leaving_a_fade(self):
        self.window.read_command(json.dumps({**self.command, "rows": [], "hover_enabled": False}))
        self.assertEqual(self.window.retiring, [])
        self.assertTrue(self.window.isHidden())

    def test_only_shop_labels_overlapping_the_description_fade_and_return_in_place(self):
        rows=[{'x':120,'y':90,'name':'Hat','key':'shop:0','kind':'shop','text':'FM 1,000'},
              {'x':120,'y':150,'name':'Shoes','key':'shop:1','kind':'shop','text':'FM 2,000'}]
        state={**self.command,'rows':rows}
        self.window.read_command(json.dumps(state))
        for row in self.window.rows:row['_fade'].setCurrentTime(110)
        before=[self.window.label_rect(row,QPoint()) for row in self.window.rows]
        for row in rows:row['occlusion']=[250,80,300,50]
        self.window.read_command(json.dumps(state))
        affected,clear=self.window.rows
        affected['_fade'].setCurrentTime(110)
        self.assertAlmostEqual(affected['_alpha'],.25)
        self.assertAlmostEqual(clear['_alpha'],1)
        self.assertEqual(before,[self.window.label_rect(row,QPoint()) for row in self.window.rows])
        for row in rows:row['occlusion']=None
        self.window.read_command(json.dumps(state))
        affected['_fade'].setCurrentTime(110)
        self.assertAlmostEqual(affected['_alpha'],1)
        self.assertEqual(before,[self.window.label_rect(row,QPoint()) for row in self.window.rows])

    def test_reduce_motion_keeps_overlap_transparency_without_an_animation(self):
        self.window.read_command(json.dumps({**self.command,'reduce_motion':True,'rows':[
            {'x':120,'y':90,'name':'Hat','key':'shop:0','kind':'shop','text':'FM 1,000','occlusion':[200,80,300,100]}]}))
        self.assertAlmostEqual(self.window.rows[0]['_alpha'],.25)
        self.assertIsNone(self.window.rows[0].get('_fade'))

    def test_age_updates_do_not_pulse_a_stable_market_price(self):
        row={'x':120,'y':90,'name':'Hat','key':'shop:0','kind':'shop','text':'FM 1,000 · 1s',
             'content_id':[1,1000]}
        state={**self.command,'rows':[row]};self.window.read_command(json.dumps(state))
        self.window.rows[0]['_fade'].setCurrentTime(110)
        self.window.read_command(json.dumps({**state,'rows':[{**row,'text':'FM 1,000 · 2s'}]}))
        self.assertIsNone(self.window.rows[0].get('_text_fade'))
        self.assertAlmostEqual(self.window.rows[0].get('_text_alpha',1),1)

    def test_scan_status_uses_game_bottom_right_and_stacks_above_tracker(self):
        from price_lens.overlay_layout import corner_offset
        bounds=[100,150,600,500]
        tracker={'kind':'experience','anchor':'bottom_left','bounds':bounds,'extra':'raw EXP\nMeso +1,200'}
        offset=corner_offset(bounds,[tracker]);self.assertEqual(offset,76)
        status={'kind':'translation_status','key':'chat:status','name':'Korean translation','text':'Scanning… 4s',
                'x':0,'y':0,'anchor':'bottom_right','bounds':bounds,'bottom_offset':offset}
        self.window.read_command(json.dumps({**self.command,'reduce_motion':True,'rows':[status]}))
        rect=self.window.label_rect(self.window.rows[0],QPoint())
        self.assertEqual(rect.right(),695)
        self.assertEqual(rect.bottom(),645-offset)
