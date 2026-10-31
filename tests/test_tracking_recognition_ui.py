"""Verified game context and tracking transitions, using offscreen fake capture."""
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QRect

import test_ui_context as fixtures
from test_experience import payload
from test_meso_tracking import log


class TrackingRecognitionUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.ContextUiTests.setUpClass()
        cls.app=fixtures.ContextUiTests.app

    def setUp(self):
        self.fixture=fixtures.ContextUiTests();self.fixture.setUp()
        self.window=self.fixture.window
        self.now=time.monotonic()
        self.clock=patch('price_lens.experience_ui.time.monotonic',lambda:self.now)
        self.clock.start()
        reader=self.window.reader
        reader.tracking_ready=True
        reader.tracking_area=QRect(reader.game_area)
        reader.tracking_frame_at=self.now

    def tearDown(self):
        self.clock.stop()
        self.fixture.tearDown();self.fixture.doCleanups()

    def frame(self,recognized=True,seconds=1):
        self.now+=seconds
        reader=self.window.reader
        reader.last_frame=self.now
        reader.tracking_ready=recognized
        reader.tracking_frame_at=self.now if recognized else 0
        reader.image_ready.emit(reader.image)

    def exp(self,value=2000,*,name='TestWarrior',epoch=None,**extra):
        panel=self.window.exp_panel
        self.window.on_experience({'atMs':int(self.now*1000),
            'trackingEpoch':panel.tracking_epoch if epoch is None else epoch,
            'experience':payload(value,name=name),**extra})

    def test_fresh_desktop_and_manual_selection_cannot_start_without_verified_game_anchors(self):
        w=self.window;reader=w.reader
        reader.auto_active=False;reader.crop=reader.image.rect();reader.game_area=None
        reader.tracking_area=None;reader.tracking_ready=False;reader.tracking_frame_at=0
        w.on_exp_hotkey()
        self.assertFalse(w.exp_panel.connected);self.assertFalse(w.exp_panel.requested)
        self.assertTrue(w.pending_exp_start);self.assertEqual(reader.starts,0)
        reader.tracking_area=QRect(20,30,700,720)
        self.frame()
        self.assertTrue(w.exp_panel.connected);self.assertTrue(w.exp_panel.requested)
        self.assertFalse(w.pending_exp_start)
        self.exp()
        self.assertIsNotNone(w.exp_panel.tracker.run)
        self.assertEqual(reader.tracking_epoch,w.exp_panel.tracking_epoch)

    def test_lost_recognition_immediately_holds_and_only_original_character_resumes(self):
        w=self.window;panel=w.exp_panel;reader=w.reader
        w.on_exp_hotkey();self.exp()
        self.frame();self.exp(2010)
        run=panel.tracker.run;totals=panel.totals();seconds=panel.mesos.seconds
        old_epoch=panel.tracking_epoch
        self.assertTrue(reader.pickups_enabled)
        self.frame(False,seconds=0)
        self.assertFalse(panel.connected);self.assertTrue(panel.recognition_held)
        self.assertFalse(panel.user_paused);self.assertFalse(reader.pickups_enabled)
        self.assertEqual(reader.tracking_epoch,panel.tracking_epoch)
        self.assertGreater(panel.tracking_epoch,old_epoch)
        self.assertEqual(w.overlay.rows,[])
        self.exp(5000,epoch=old_epoch,pickupsRead=True,pickups=log(5000))
        self.frame(seconds=30)
        self.assertTrue(panel.connected);self.assertTrue(panel.recognition_held)
        for _ in range(3):
            self.frame();self.exp(5000,name='OtherCharacter')
        self.assertIs(panel.tracker.run,run);self.assertEqual(panel.totals(),totals)
        self.assertEqual(panel.mesos.seconds,seconds);self.assertEqual(panel.mesos.gain,0)
        self.assertEqual(w.overlay.rows,[]);self.assertEqual(panel.history.rows(),[])
        self.frame();self.exp(2500)
        self.assertTrue(panel.recognition_held);self.assertFalse(reader.pickups_enabled)
        self.frame();self.exp(2510)
        self.assertFalse(panel.recognition_held);self.assertTrue(reader.pickups_enabled)
        self.assertEqual(panel.totals(),totals);self.assertIs(panel.tracker.run,run)
        self.frame();self.exp(2520)
        self.assertEqual(panel.totals()['exp'],totals['exp']+10)
        self.assertEqual(reader.starts,0);self.assertEqual(reader.pauses,[])

    def test_manual_pause_stays_paused_after_recognition_and_original_identity_return(self):
        w=self.window;panel=w.exp_panel;reader=w.reader
        w.on_exp_hotkey();self.exp();panel.toggle_pause()
        self.assertTrue(panel.user_paused);self.assertFalse(reader.pickups_enabled)
        self.frame(False);self.frame()
        for value in (2500,2510):self.frame();self.exp(value)
        self.assertTrue(panel.user_paused);self.assertTrue(panel.tracker.paused)
        self.assertFalse(panel.recognition_held);self.assertTrue(panel.paused_context_ready)
        self.assertTrue(panel.pause_button.isEnabled());self.assertFalse(reader.pickups_enabled)
        self.assertEqual(panel.tracker.run.exp,0)
        epoch=reader.tracking_epoch;panel.toggle_pause()
        self.assertFalse(panel.user_paused);self.assertTrue(reader.pickups_enabled)
        self.assertGreater(reader.tracking_epoch,epoch)

    def test_unreadable_exp_does_not_turn_verified_game_context_into_a_recognition_pause(self):
        w=self.window;panel=w.exp_panel;reader=w.reader
        w.on_exp_hotkey();self.exp();epoch=panel.tracking_epoch
        self.frame()
        w.on_experience({'atMs':int(self.now*1000),'trackingEpoch':epoch,'experience':{}})
        for rows in ((),(600,),(600,)):
            self.frame(seconds=.2)
            w.on_experience({'atMs':int(self.now*1000),'trackingEpoch':epoch,
                             'pickupsRead':True,'pickups':log(*rows)})
        self.assertTrue(panel.connected);self.assertFalse(panel.recognition_held)
        self.assertEqual(panel.mesos.gain,600);self.assertTrue(reader.pickups_enabled)
        self.assertEqual(panel.tracking_epoch,epoch)


if __name__=='__main__':unittest.main()
