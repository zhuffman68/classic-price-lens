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
        self.assertEqual(self.panel.overlay_rows(),[])
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
        self.assertEqual(self.panel.elapsed.text(),"00:31")
        self.assertIn("%",self.panel.overlay_rows()[0]["metrics"][1][1])
        self.assertNotIn("EXP",self.panel.overlay_rows()[0]["metrics"][1][1])
        self.assertIn("Lv.",self.panel.overlay_rows()[0]["name"])

    def test_tracking_clock_adds_hours_and_keeps_seconds_without_shifting_controls(self):
        from price_lens.experience import clock_text
        self.panel.resize(428,650);self.panel.show();self.panel.set_connected(True);self.panel.start()
        self.app.processEvents();before=self.panel.pause_button.geometry()
        for seconds,expected in ((3599,'59:59'),(3600,'1:00:00'),(3661,'1:01:01'),(36061,'10:01:01')):
            self.panel.elapsed.setText(clock_text(seconds));self.app.processEvents()
            self.assertEqual(self.panel.elapsed.text(),expected)
            self.assertGreaterEqual(self.panel.elapsed.width(),self.panel.elapsed.fontMetrics().horizontalAdvance(expected))
            self.assertEqual(self.panel.pause_button.geometry(),before)

    def test_units_and_rate_labels_remain_consistent_in_each_mode(self):
        self.train()
        self.assertEqual(self.panel.minute_caption.text(), 'Per minute')
        self.assertEqual(self.panel.hour_caption.text(), 'Per hour')
        self.assertEqual([w.text() for w in self.panel.meso_captions][1:], ['Per minute','Per hour'])
        self.assertTrue(all('%' in w.text() for w in (self.panel.gain,self.panel.rate,self.panel.hour_rate)))
        self.panel.set_display('raw')
        self.assertTrue(all('EXP' in w.text() for w in (self.panel.gain,self.panel.rate,self.panel.hour_rate)))
        self.panel.set_display('both')
        self.assertTrue(all('%' in w.text() for w in (self.panel.gain,self.panel.rate,self.panel.hour_rate)))
        self.assertIn('EXP gained', self.panel.raw_hint.text())

    def test_meso_units_wait_for_confirmed_log_then_remain_inline(self):
        self.panel.show();self.app.processEvents()
        self.assertEqual(self.panel.meso_heading.text(),'MESO')
        self.assertEqual(self.panel.meso_gain.text(),'—')
        self.panel.set_connected(True);self.panel.start()
        self.pickup();self.pickup(29);self.pickup(29)
        self.now+=2;self.panel.refresh()
        self.assertEqual(self.panel.meso_gain.text(),'+29 mesos')
        self.assertTrue(all(not w.isHidden() for w in self.panel.meso_captions))

    def pickup(self,*amounts):
        from test_meso_tracking import log
        self.now+=.2
        self.panel.feed({'atMs':int(self.now*1000),'pickupsRead':True,'pickups':log(*amounts)})

    def test_warmup_is_explicit_only_during_a_session(self):
        self.assertEqual(self.panel.observation.text(), '')
        self.assertTrue(self.panel.observation.isHidden())
        self.panel.set_connected(True);self.panel.start();self.feed(2000)
        self.assertIn('Measuring pace', self.panel.observation.text())
        self.assertIn('30s', self.panel.observation.text())
        for _ in range(31):self.feed(self.panel.tracker.current.exp+10,1)
        self.assertNotIn('remaining', self.panel.observation.text())
        self.panel.stop()
        self.assertTrue(self.panel.observation.isHidden())

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
        self.assertEqual(self.panel.rate.text(),"600 EXP")
        self.assertEqual(self.panel.hour_rate.text(),"36,000 EXP")
        self.assertEqual(self.panel.overlay_rows()[0]["metrics"][1][1],"600 EXP")
        self.panel.set_display("both")
        self.assertIn("%",self.panel.rate.text())
        self.assertIn("%",self.panel.overlay_rows()[0]["metrics"][1][1])
        self.assertIn("EXP/min",self.panel.overlay_rows()[0]["secondary"])

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
        self.assertEqual(self.panel.overlay_rows(),[])
        self.assertFalse(self.panel.user_paused)

    def test_global_context_loss_does_not_count_hidden_gain(self):
        self.panel.set_connected(True);self.panel.start();self.feed(2000);self.feed(2010,1)
        self.panel.set_connected(False);self.panel.set_connected(True)
        self.feed(2500,1);self.feed(2510,1)
        self.assertEqual(self.panel.tracker.run.exp,20)

    def test_paused_session_survives_another_character_and_map_without_resetting(self):
        self.train();self.pickup();self.pickup(1200);self.pickup(1200)
        panel=self.panel;run=panel.tracker.run;panel.tracker.map_name=run.map_name='Original map'
        panel.toggle_pause();totals=panel.totals();money=panel.mesos.gain;seconds=panel.mesos.seconds
        panel.set_connected(False);panel.set_connected(True)
        for _ in range(3):
            self.now+=1
            panel.feed({'atMs':int(self.now*1000),'experience':{**payload(5000,name='OtherCharacter'),
                        'mapRead':True,'map':{'map':'Other map'}},'pickupsRead':True,'pickups':{'valid':True,'lines':[]}})
        self.assertIs(panel.tracker.run,run);self.assertEqual(panel.tracker.current.character,'TestWarrior')
        self.assertEqual(panel.tracker.map_name,'Original map');self.assertEqual(panel.totals(),totals)
        self.assertEqual(panel.mesos.gain,money);self.assertEqual(panel.mesos.seconds,seconds)
        self.assertTrue(panel.user_paused);self.assertTrue(panel.tracker.paused);self.assertTrue(panel.mesos.paused)
        self.assertFalse(panel.pause_button.isEnabled());self.assertEqual(panel.overlay_rows(),[])
        self.assertIn('TestWarrior',panel.state.text());self.assertEqual(panel.history.rows(),[])
        panel.toggle_pause();self.assertTrue(panel.user_paused)
        exp=panel.tracker.current.exp
        self.feed(exp+500,1);self.assertEqual(panel.overlay_rows(),[])
        self.feed(exp+500,1)
        self.assertTrue(panel.pause_button.isEnabled());self.assertEqual(len(panel.overlay_rows()),2)
        self.assertEqual(panel.totals(),totals);self.assertIs(panel.tracker.run,run)
        panel.toggle_pause();self.feed(exp+500,1);self.feed(exp+510,1)
        self.assertEqual(panel.totals()['exp'],totals['exp']+10)
        self.pickup(5000);self.pickup(5000,100);self.pickup(5000,100)
        self.assertEqual(panel.mesos.gain,money+100)

    def test_stopped_reader_ignores_gain_and_new_session_starts_clean(self):
        self.panel.set_connected(True);self.panel.start();self.feed(2000);self.feed(2010,1)
        self.panel.stop();self.feed(3000,1)
        self.assertFalse(self.panel.enabled);self.assertIsNone(self.panel.tracker.run)
        self.now+=6;self.panel.start();self.feed(3010,1);self.feed(3020,1)
        self.assertEqual(self.panel.tracker.run.exp,10)

    def test_stale_readings_hold_the_overlay_and_watch_timer(self):
        self.train();before=self.panel.tracker.run.seconds
        self.now+=6;self.panel.refresh()
        self.assertIn("Reading held",self.panel.overlay_rows()[0]["status"])
        self.assertEqual(self.panel.tracker.run.seconds,before)
        self.assertIn("Reading held",self.panel.state.text())

    def test_inconsistent_exp_is_explained_separately_from_an_unreadable_bar(self):
        self.train();self.now+=6
        self.panel.feed({'atMs':int(self.now*1000),'experience':payload(4000,12_000)})
        self.assertIn('Checking EXP values',self.panel.state.text())
        self.assertEqual(self.panel.overlay_rows()[0]['compact_note'],'Checking EXP')
        self.assertNotIn('unreadable',self.panel.state.text())
        self.now+=1;self.panel.feed({'atMs':int(self.now*1000),'experience':{}})
        self.assertIn('Reading held',self.panel.state.text())

    def test_warmup_counts_clear_reading_time_and_gain_can_appear_before_rates(self):
        self.panel.set_connected(True);self.panel.start();self.feed(2000);self.feed(2010,2)
        self.assertEqual(self.panel.overlay_rows()[0]['text'],'+0.10%')
        self.assertIsNone(self.panel.tracker.window(300)['rate'])
        self.assertIn('clear EXP readings remaining',self.panel.observation.text())
        self.now+=60;self.feed(2500)
        self.assertIsNone(self.panel.tracker.window(300)['rate'])
        self.assertIn('clear EXP readings remaining',self.panel.observation.text())
        self.assertEqual(self.panel.overlay_rows()[0]['text'],'+0.10%')
        for _ in range(31):self.feed(self.panel.tracker.current.exp+10,1)
        self.assertIsNotNone(self.panel.tracker.window(300)['rate'])

    def test_shared_rate_explanation_replaces_normal_overlay_window_labels(self):
        self.panel.set_connected(True);self.panel.start();self.feed(2000)
        self.assertIn('Measuring pace',self.panel.overlay_rows()[0]['status'])
        self.assertEqual(self.panel.overlay_rows()[0]['basis'],'')
        for _ in range(361):self.feed(self.panel.tracker.current.exp+1,1)
        row=self.panel.overlay_rows()[0]
        self.assertEqual(row['basis'],'')
        self.assertEqual(row['status'],'')
        self.assertEqual(self.panel.observation.text(),'')
        self.assertEqual(self.panel.rates_note.text(),'Rates based on the last 5 minutes')
        self.assertAlmostEqual(self.panel.tracker.window(300)['seconds'],300)
        self.assertGreater(self.panel.mesos.seconds,300)
        self.assertIn('Level 28 · ETA',row['footer'])
        self.panel.toggle_pause()
        self.assertEqual(self.panel.overlay_rows()[0]['compact_note'],'Paused')
        self.assertEqual(self.panel.overlay_rows()[0]['basis'],'')

    def test_shared_pickup_tracking_holds_pause_and_saves_its_basis(self):
        self.train();self.pickup();self.pickup(1200);self.pickup(1200)
        self.now+=2;self.panel.refresh()
        self.assertEqual(self.panel.meso_gain.text(),'+1,200 mesos')
        self.assertEqual(self.panel.overlay_rows()[1]['text'],'+1,200')
        self.assertNotIn('meso',self.panel.overlay_rows()[0]['footer'].lower())
        self.panel.toggle_pause();self.pickup(5000);self.pickup(5000)
        self.assertEqual(self.panel.mesos.gain,1200)
        self.panel.toggle_pause();self.pickup(5000);self.pickup(5000,100);self.pickup(5000,100)
        self.panel.stop();saved=self.panel.history.rows()[0]
        self.assertEqual(saved['mesos'],1300);self.assertEqual(saved['meso_basis'],'pickups')
        self.assertIsNone(saved['wallet_end'])

    def test_pickups_can_be_saved_without_readable_exp(self):
        self.panel.set_connected(True);self.panel.start()
        self.pickup();self.pickup(1200);self.pickup(1200)
        self.assertEqual(self.panel.mesos.gain,1200)
        self.assertEqual(len(self.panel.overlay_rows()),2)
        self.panel.stop();self.assertEqual(self.panel.history.rows()[0]['mesos'],1200)

    def test_overlay_numbers_are_throttled_but_pause_updates_immediately(self):
        self.train();self.now+=1;self.panel.refresh()
        self.panel.mesos.observed=True;self.panel.mesos.gain=100;self.panel.refresh()
        first=self.panel.overlay_rows();gain=self.panel.gain.text();clock=self.panel.elapsed.text()
        self.panel.mesos.gain=200
        self.feed(self.panel.tracker.current.exp+10,1)
        updated=self.panel.overlay_rows()
        self.assertEqual([{k:v for k,v in row.items() if k!='clock'} for row in updated],
                         [{k:v for k,v in row.items() if k!='clock'} for row in first])
        self.assertEqual(self.panel.gain.text(),gain);self.assertNotEqual(self.panel.elapsed.text(),clock)
        self.assertEqual(self.panel.meso_gain.text(),'+100 mesos')
        self.feed(self.panel.tracker.current.exp+10,1)
        self.assertNotEqual(self.panel.overlay_rows(),first)
        self.assertEqual(self.panel.gain.text(),self.panel.overlay_rows()[0]['text'])
        self.assertEqual(self.panel.meso_gain.text(),'+200 mesos');self.assertEqual(self.panel.overlay_rows()[1]['text'],'+200')
        self.panel.toggle_pause();self.assertEqual(self.panel.overlay_rows()[0]['status'],'Paused')

    def test_pause_freezes_the_last_displayed_eta_and_rates_through_long_delays(self):
        self.train();eta=self.panel.eta.text();rates=(self.panel.rate.text(),self.panel.hour_rate.text())
        footer=self.panel.overlay_rows()[0]['footer'];self.panel.toggle_pause()
        for seconds in (1,6,60,600):
            self.now+=seconds;self.feed(4000)
            self.assertEqual(self.panel.eta.text(),eta)
            self.assertEqual((self.panel.rate.text(),self.panel.hour_rate.text()),rates)
            self.assertEqual(self.panel.overlay_rows()[0]['footer'],footer)
        self.assertEqual(self.panel.eta_caption.text(),'Level 28 · ETA')
        self.assertIn('Level 28 · ETA',footer)

    def test_detected_map_header_keeps_the_start_of_the_name_and_full_tooltip(self):
        self.panel.set_connected(True);self.panel.start();self.feed(2000)
        full='Victoria Road: Tree Dungeon, Forest Up North V'
        self.panel.tracker.map_name=full;self.panel.resize(428,650);self.panel.show();self.panel.refresh();self.app.processEvents()
        self.assertEqual(self.panel.map_label.text(),'Tree Dungeon, Forest Up North V')
        self.assertEqual(self.panel.map_label.toolTip(),full)
        self.assertTrue(self.panel.map_label.property('elideRight'))
        self.assertEqual(self.panel.tracker.map_name,full)
        self.assertGreaterEqual(self.panel.map_label.width(),self.panel.map_label.fontMetrics().horizontalAdvance(self.panel.map_label.text()))
        self.panel.map_input.setText('My map: route 1');self.panel.refresh()
        self.assertEqual(self.panel.map_label.text(),'My map: route 1')

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

    def test_map_changes_retain_rates_gains_pickups_and_warmup_progress(self):
        self.train();self.pickup();self.pickup(120);self.pickup(120)
        run=self.panel.tracker.run;self.panel.tracker.map_name=run.map_name='Old map'
        gains=self.panel.totals();money=self.panel.mesos.gain;seconds=self.panel.mesos.seconds
        for _ in range(2):
            self.now+=1
            self.panel.feed({'atMs':int(self.now*1000),'experience':{**payload(self.panel.tracker.current.exp),'mapRead':True,'map':{'map':'New map'}}})
        self.assertIsNot(self.panel.tracker.run,run)
        self.assertIsNotNone(self.panel.tracker.window(300)['rate'])
        self.assertAlmostEqual(self.panel.totals()['exp'],gains['exp'])
        self.assertEqual(self.panel.mesos.gain,money);self.assertGreater(self.panel.mesos.seconds,seconds)
        self.assertEqual(self.panel.mesos.last_pickup,120)
        self.assertNotIn('remaining',self.panel.observation.text())

    def test_resume_reacquires_without_restarting_exp_or_meso_pace(self):
        self.train();self.pickup();self.pickup(120);self.pickup(120)
        self.now+=2;self.panel.refresh();before=self.panel.overlay_rows();rates=(self.panel.rate.text(),self.panel.meso_rate.text())
        seconds=self.panel.tracker.window(300)['seconds']
        self.panel.toggle_pause();self.now+=90;self.panel.refresh();clock=self.panel.elapsed.text()
        self.panel.toggle_pause();self.assertTrue(self.panel.reacquiring)
        self.assertEqual((self.panel.rate.text(),self.panel.meso_rate.text()),rates)
        self.assertEqual(self.panel.overlay_rows()[0]['compact_note'],'Reacquiring')
        self.feed(self.panel.tracker.current.exp+100,1)
        self.assertFalse(self.panel.reacquiring)
        self.assertIsNotNone(self.panel.tracker.window(300)['rate'])
        self.assertEqual(self.panel.tracker.window(300)['seconds'],seconds)
        self.assertNotIn('remaining',self.panel.observation.text());self.assertNotEqual(self.panel.elapsed.text(),clock)
        self.assertEqual(self.panel.overlay_rows()[0]['metrics'],before[0]['metrics'])

    def test_meso_footer_has_last_pickup_and_paused_header_survives_empty_basis(self):
        self.train();self.pickup();self.pickup(29);self.pickup(29);self.now+=2;self.panel.refresh()
        meso=self.panel.overlay_rows()[1]
        self.assertEqual(meso['basis'],'');self.assertEqual(meso['footer'],'Last pickup: +29')
        self.assertTrue(all(value.startswith('+') for _,value in meso['metrics']))
        self.panel.toggle_pause();meso=self.panel.overlay_rows()[1]
        self.assertEqual(meso['compact_note'],'Paused');self.assertEqual(meso['footer'],'Last pickup: +29')

    def test_same_name_pixels_with_z_two_ocr_flips_do_not_split_a_session(self):
        from test_tracking_identity import proof
        self.panel.set_connected(True);self.panel.start()
        for index,name in enumerate(('achZ','ach2','achZ','ach2','ach2')):
            self.now+=1
            self.panel.feed({'atMs':int(self.now*1000),'experience':{**payload(2000+index*10,name=name),'nameProof':proof()}})
        self.assertEqual(self.panel.tracker.current.character,'achZ')
        self.assertEqual(self.panel.tracker.run.exp,40);self.assertEqual(self.panel.history.rows(),[])
        run=self.panel.tracker.run;self.panel.toggle_pause();self.panel.interrupt_context()
        for _ in range(2):
            self.now+=1;self.panel.feed({'atMs':int(self.now*1000),'experience':{**payload(2100,name='ach2'),'nameProof':proof()}})
        self.assertTrue(self.panel.paused_context_ready);self.assertIs(self.panel.tracker.run,run)

    def test_zero_indent_level_badge_does_not_reserve_a_spare_character(self):
        self.train();self.panel.resize(428,650);self.panel.show();self.app.processEvents()
        label=self.panel.level_label;m=label.contentsMargins()
        self.assertLessEqual(label.sizeHint().width(),label.fontMetrics().horizontalAdvance(label.text())+m.left()+m.right()+2)


if __name__=="__main__":unittest.main()
