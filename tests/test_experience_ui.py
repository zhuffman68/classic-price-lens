"""Automatic EXP watching, rate units and history; no OS capture or network."""
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from PySide6.QtCore import QCoreApplication,QEvent
from PySide6.QtWidgets import QApplication
from price_lens.experience_ui import ExperiencePanel
from test_experience import payload


class ExperienceUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.panel = ExperiencePanel(Path(self.directory.name)/"sessions.sqlite")
        self.now = time.monotonic()
        self.clock = patch("price_lens.experience_ui.time.monotonic",lambda:self.now)
        self.clock.start()

    def tearDown(self):
        self.clock.stop()
        self.panel.close_session()
        self.panel.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.directory.cleanup()

    def feed(self, exp, seconds=0):
        self.now += seconds
        self.panel.feed({"atMs":int(self.now*1000),"experience":payload(exp)})

    def test_readable_connected_exp_starts_automatically(self):
        self.assertIsNone(self.panel.tracker.run)
        self.feed(2000)
        self.assertIsNone(self.panel.tracker.run)
        self.panel.set_connected(True)
        self.feed(2010,1)
        self.assertIsNotNone(self.panel.tracker.run)
        self.assertFalse(hasattr(self.panel,"window_picker"))
        self.assertFalse(hasattr(self.panel,"start_button"))
        self.assertTrue(self.panel.details.isHidden())
        self.assertEqual(self.panel.table.window(),self.panel.history_dialog)
        self.assertEqual(self.panel.notes.window(),self.panel.options_dialog)

    def train(self):
        self.panel.set_connected(True)
        self.feed(2000)
        for _ in range(31):self.feed(self.panel.tracker.current.exp+10,1)

    def test_percent_is_default_with_minute_hour_and_eta(self):
        self.train()
        self.assertEqual(self.panel.rate.text(),"+6.00%")
        self.assertEqual(self.panel.hour_rate.text(),"+360.0%")
        self.assertEqual(self.panel.elapsed.text(),"0m 31s")
        self.assertIn("%/min",self.panel.overlay_row()["text"])
        self.assertNotIn("EXP/min",self.panel.overlay_row()["text"])
        self.assertTrue(self.panel.overlay_row()["name"].startswith("Lv."))

    def test_raw_and_both_keep_percentage_first(self):
        self.train()
        self.panel.set_display("raw")
        self.assertEqual(self.panel.rate.text(),"600")
        self.assertEqual(self.panel.hour_rate.text(),"36,000")
        self.assertIn("600 EXP/min",self.panel.overlay_row()["text"])
        self.panel.set_display("both")
        self.assertIn("%",self.panel.rate.text())
        self.assertIn("%/min",self.panel.overlay_row()["text"])
        self.assertIn("EXP/min",self.panel.overlay_row()["extra"])

    def test_pause_excludes_unseen_gain_and_reset_saves_then_keeps_watching(self):
        self.train()
        self.panel.pause_button.click()
        self.assertTrue(self.panel.tracker.paused)
        self.assertEqual(self.panel.pause_button.text(),"Resume watching")
        before=self.panel.tracker.run.exp
        self.feed(3000,1)
        self.assertEqual(self.panel.tracker.run.exp,before)
        self.panel.save_button.click()
        self.assertEqual(len(self.panel.history.rows()),1)
        self.assertIsNotNone(self.panel.tracker.run)
        self.assertEqual(self.panel.tracker.run.exp,0)
        self.assertFalse(self.panel.user_paused)
        self.assertEqual(self.panel.totals()["seconds"],0)

    def test_global_context_loss_does_not_count_hidden_gain(self):
        self.panel.set_connected(True);self.feed(2000);self.feed(2010,1)
        self.panel.set_connected(False);self.panel.set_connected(True)
        self.feed(2500,1);self.feed(2510,1)
        self.assertEqual(self.panel.tracker.run.exp,20)

    def test_exp_disable_pauses_and_enable_resumes_without_inventing_gain(self):
        self.panel.set_connected(True);self.feed(2000);self.feed(2010,1)
        self.panel.enabled_check.setChecked(False);self.feed(3000,1)
        self.assertEqual(self.panel.tracker.run.exp,10)
        self.assertTrue(self.panel.tracker.paused)
        self.panel.enabled_check.setChecked(True)
        self.assertFalse(self.panel.tracker.paused)
        self.feed(3010,1);self.feed(3020,1)
        self.assertEqual(self.panel.tracker.run.exp,20)

    def test_stale_readings_hold_the_overlay_and_watch_timer(self):
        self.train();before=self.panel.tracker.run.seconds
        self.now+=6;self.panel.refresh()
        self.assertIsNone(self.panel.overlay_row())
        self.assertEqual(self.panel.tracker.run.seconds,before)
        self.assertIn("timer held",self.panel.state.text())

    def test_map_changes_save_a_segment_and_continue_the_total_timer(self):
        self.train()
        before=self.panel.totals()["seconds"]
        self.panel.tracker.map_name="Old map"
        for _ in range(2):
            self.now+=1
            self.panel.feed({"atMs":int(self.now*1000),"experience":{**payload(self.panel.tracker.current.exp+10),"mapRead":True,"map":{"map":"New map"}}})
        self.assertIsNotNone(self.panel.tracker.run)
        self.assertEqual(self.panel.tracker.run.map_name,"New map")
        self.assertGreaterEqual(self.panel.totals()["seconds"],before)
        self.assertEqual(len(self.panel.history.rows()),1)


if __name__=="__main__":unittest.main()
