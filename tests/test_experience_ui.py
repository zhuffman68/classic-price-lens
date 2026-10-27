"""Explicit EXP tracking, rate units and history; no OS capture or network."""
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

    def test_startup_is_stopped_until_explicit_start(self):
        self.panel.set_connected(True);self.feed(2000)
        self.assertIsNone(self.panel.tracker.run)
        self.assertFalse(self.panel.enabled)
        self.assertIsNone(self.panel.overlay_row())
        self.assertTrue(hasattr(self.panel,'start_button'))
        self.assertFalse(hasattr(self.panel,'enabled_check'))
        self.assertFalse(hasattr(self.panel,'details_button'))
        self.assertEqual(self.panel.state.text(),'')
        self.assertTrue(self.panel.state.isHidden())
        self.panel.start_button.click();self.feed(2010,1)
        self.assertIsNotNone(self.panel.tracker.run)
        self.assertEqual(self.panel.table.window(),self.panel.history_dialog)
        self.assertEqual(self.panel.notes.window(),self.panel.window())
        self.assertEqual(self.panel.map_input.window(),self.panel.window())
        self.assertFalse(hasattr(self.panel,'options_button'))
        self.assertFalse(hasattr(self.panel,'options_dialog'))

    def train(self):
        self.panel.set_connected(True)
        self.panel.start()
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

    def test_exp_and_meso_rate_columns_align_at_compact_and_wide_sizes(self):
        self.train();self.panel.show()
        for width in (428,608):
            self.panel.resize(width,650);self.app.processEvents()
            for exp,money in ((self.panel.gain,self.panel.meso_gain),
                              (self.panel.rate,self.panel.meso_rate),(self.panel.hour_rate,self.panel.meso_hour)):
                self.assertEqual(exp.mapTo(self.panel,exp.rect().topLeft()).x(),money.mapTo(self.panel,money.rect().topLeft()).x())
                self.assertEqual(exp.width(),money.width())

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

    def test_pause_excludes_unseen_gain_and_stop_saves_without_restarting(self):
        self.train()
        self.panel.pause_button.click()
        self.assertTrue(self.panel.tracker.paused)
        self.assertEqual(self.panel.pause_button.text(),"Resume")
        before=self.panel.tracker.run.exp
        self.feed(3000,1)
        self.assertEqual(self.panel.tracker.run.exp,before)
        self.panel.save_button.click()
        self.assertEqual(len(self.panel.history.rows()),1)
        self.assertIsNone(self.panel.tracker.run)
        self.assertFalse(self.panel.enabled)
        self.assertIsNone(self.panel.overlay_row())
        self.assertFalse(self.panel.user_paused)

    def test_global_context_loss_does_not_count_hidden_gain(self):
        self.panel.set_connected(True);self.panel.start();self.feed(2000);self.feed(2010,1)
        self.panel.set_connected(False);self.panel.set_connected(True)
        self.feed(2500,1);self.feed(2510,1)
        self.assertEqual(self.panel.tracker.run.exp,20)

    def test_stopped_reader_ignores_gain_and_new_session_starts_clean(self):
        self.panel.set_connected(True);self.panel.start();self.feed(2000);self.feed(2010,1)
        self.panel.stop();self.feed(3000,1)
        self.assertFalse(self.panel.enabled);self.assertIsNone(self.panel.tracker.run)
        self.now+=6;self.panel.start();self.feed(3010,1);self.feed(3020,1)
        self.assertEqual(self.panel.tracker.run.exp,10)

    def test_stale_readings_hold_the_overlay_and_watch_timer(self):
        self.train();before=self.panel.tracker.run.seconds
        self.now+=6;self.panel.refresh()
        self.assertIsNone(self.panel.overlay_row())
        self.assertEqual(self.panel.tracker.run.seconds,before)
        self.assertIn("EXP estimates held",self.panel.state.text())

    def test_shared_wallet_tracking_counts_net_change_and_holds_pause(self):
        self.train()
        def wallet(value,step=1):
            self.now+=step
            self.panel.feed({'atMs':int(self.now*1000),'experience':payload(self.panel.tracker.current.exp),
                             'walletRead':True,'wallet':{'mesos':value} if value is not None else None})
        wallet(70000);wallet(70000)
        wallet(None);wallet(71200);wallet(71200)
        self.assertEqual(self.panel.meso_gain.text(),'+1,200')
        self.assertIn('Meso +1,200',self.panel.overlay_row()['extra'])
        self.panel.toggle_pause();wallet(50000);wallet(50000)
        self.assertEqual(self.panel.mesos.gain,1200)
        self.panel.toggle_pause();wallet(50000);wallet(50000);wallet(50100);wallet(50100)
        self.assertEqual(self.panel.mesos.gain,1300)
        self.panel.stop()
        saved=self.panel.history.rows()[0]
        self.assertEqual(saved['mesos'],1300)
        self.assertEqual(saved['wallet_end'],50100)

    def test_wallet_can_be_saved_without_readable_exp(self):
        self.panel.set_connected(True);self.panel.start()
        for amount in (70000,70000,71200,71200):
            self.now+=1
            self.panel.feed({'atMs':int(self.now*1000),'walletRead':True,'wallet':{'mesos':amount}})
        self.assertEqual(self.panel.mesos.gain,1200)
        self.assertIn('Meso tracking',self.panel.overlay_row()['name'])
        self.panel.stop()
        self.assertEqual(self.panel.history.rows()[0]['mesos'],1200)

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
