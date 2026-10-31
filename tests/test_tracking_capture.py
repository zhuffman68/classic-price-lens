"""Generated game pixels and bounded local OCR IPC; never starts OS sharing."""
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication,QEvent,QObject,QProcess,QRect,Signal
from PySide6.QtGui import QColor,QImage
from PySide6.QtWidgets import QApplication

from price_lens.capture import PixelReader
from price_lens.pickup_capture import PickupWorker
from price_lens.platform_paths import reader_binary
from test_game_area import game_frame


ROOT=Path(__file__).resolve().parents[1]


class PendingPickupWorker(QObject):
    result=Signal(dict)

    def __init__(self):
        super().__init__()
        self.pending=True
        self.context=('old frame',)
        self.invalidations=0
        self.closed=False

    def invalidate(self):
        self.invalidations+=1
        self.context=None

    def close(self):self.context=None;self.closed=True


class TrackingCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        cls.app=QApplication.instance() or QApplication([])
        if not reader_binary(ROOT).is_file():raise unittest.SkipTest('Build or install the pixel reader first')

    def wait(self,condition):
        deadline=time.monotonic()+10
        while not condition():
            self.assertLess(time.monotonic(),deadline,'Fixture reader did not finish')
            self.app.processEvents();time.sleep(.005)

    def dispose_reader(self,reader):
        reader.close();reader.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def located_reader(self,*,manual=False):
        reader=PixelReader(ROOT);reader.timer.stop()
        self.addCleanup(self.dispose_reader,reader)
        self.assertTrue(reader.process.waitForStarted(3000))
        reader.live_source=True;reader.prices_enabled=False
        if manual:reader.crop=QRect(70,50,1300,780)
        reader.on_stream_frame(game_frame(),time.monotonic())
        self.wait(lambda:reader.tracking_area is not None and not reader.pending)
        self.assertTrue(reader.tracking_ready)
        return reader

    def test_manual_crop_uses_real_locator_guards_and_keeps_display_coordinates(self):
        reader=self.located_reader(manual=True)
        self.assertFalse(reader.auto_active);self.assertIsNone(reader.game_area)
        for actual,expected in zip(reader.tracking_area.getRect(),(120,90,960,600)):
            self.assertLessEqual(abs(actual-expected),8)
        self.assertEqual(reader.crop,QRect(70,50,1300,780))
        self.assertEqual(len(reader.manual_game_guards),2)
        for rect,digest in reader.manual_game_guards:
            self.assertTrue(reader.tracking_area.contains(rect))
            self.assertTrue(reader.guard_matches(reader.image,rect,digest))
        self.assertIsNotNone(reader.manual_game_footer)
        self.assertEqual(reader.tracking_frame_at,reader.last_frame)
        self.assertEqual(reader.stream.socket.state(),reader.stream.socket.LocalSocketState.UnconnectedState)

    def test_manual_selection_without_caption_and_hud_never_establishes_tracking(self):
        reader=PixelReader(ROOT);reader.timer.stop();self.addCleanup(self.dispose_reader,reader)
        self.assertTrue(reader.process.waitForStarted(3000))
        reader.live_source=True;reader.prices_enabled=False
        reader.crop=QRect(150,150,800,400)
        reader.on_stream_frame(game_frame(),time.monotonic())
        self.wait(lambda:not reader.pending)
        self.assertIsNone(reader.tracking_area);self.assertFalse(reader.tracking_ready)
        self.assertEqual(reader.manual_game_guards,[])
        self.assertEqual(reader.crop,QRect(150,150,800,400))

    def test_guard_loss_invalidates_auto_and_manual_tracking_before_image_ready(self):
        for manual in (False,True):
            with self.subTest(manual=manual):
                reader=self.located_reader(manual=manual)
                pending=PendingPickupWorker();reader.pickup_worker=pending
                reader.tracking_identity_area={'x':100,'y':100,'width':224,'height':32}
                generation=reader.generation;observed=[]
                reader.image_ready.connect(lambda _image,r=reader:observed.append((r.tracking_ready,r.tracking_area)))
                blank=QImage(reader.image.size(),QImage.Format.Format_RGBA8888);blank.fill(QColor('#171c25'))
                reader.on_stream_frame(blank,time.monotonic())
                self.assertEqual(observed,[(False,None)])
                self.assertGreater(reader.generation,generation)
                self.assertEqual(reader.tracking_frame_at,0)
                self.assertIsNone(reader.tracking_identity_area)
                self.assertGreater(pending.invalidations,0);self.assertIsNone(pending.context)

    def test_tracking_readiness_expires_and_requires_live_unpaused_guarded_frames(self):
        reader=self.located_reader(manual=True);stamp=reader.tracking_frame_at
        with patch('price_lens.capture.time.monotonic',return_value=stamp+1.501):
            self.assertFalse(reader.tracking_ready)
        with patch('price_lens.capture.time.monotonic',return_value=stamp-.01):
            self.assertFalse(reader.tracking_ready)
        reader.paused=True;self.assertFalse(reader.tracking_ready);reader.paused=False
        reader.live_source=False;self.assertFalse(reader.tracking_ready);reader.live_source=True
        reader.manual_game_guards=[];self.assertFalse(reader.tracking_ready)

    def test_pickup_reader_runs_and_returns_while_primary_reader_remains_pending(self):
        reader=self.located_reader();reader.experience_enabled=True;reader.tracking_epoch=17
        reader.pending=True;reader.pending_since=time.monotonic()
        results=[];reader.experience.connect(results.append)
        reader.scan()
        self.assertIsNotNone(reader.pickup_worker)
        worker=reader.pickup_worker
        self.wait(lambda:worker.process.state()==QProcess.ProcessState.Running)
        reader.on_stream_frame(game_frame(),time.monotonic())
        self.wait(lambda:bool(results))
        self.assertTrue(reader.pending,'Pickup OCR must not wait for or complete the primary job')
        self.assertTrue(results[-1]['pickupsRead'])
        self.assertEqual(results[-1]['trackingEpoch'],17)
        self.assertEqual(results[-1]['captureGeneration'],reader.generation)
        self.assertIn('pickupNameProof',results[-1])
        self.assertNotEqual(reader.process.processId(),worker.process.processId())
        self.assertEqual(reader.stream.socket.state(),reader.stream.socket.LocalSocketState.UnconnectedState)

    def test_pickup_replies_reject_old_epoch_generation_age_and_paused_capture(self):
        reader=self.located_reader();reader.experience_enabled=True;reader.tracking_epoch=7
        results=[];reader.experience.connect(results.append)
        packet={'atMs':int(reader.last_frame*1000),'trackingEpoch':7,'captureGeneration':reader.generation,
                'pickupsRead':True,'pickups':{'valid':True,'lines':[]}}
        for changes in ({'trackingEpoch':6},{'captureGeneration':reader.generation-1},{'atMs':0}):
            reader.on_pickup_result({**packet,**changes})
        self.assertEqual(results,[])
        reader.on_pickup_result(packet);self.assertEqual(results,[packet])
        reader.paused=True;reader.on_pickup_result(packet);self.assertEqual(results,[packet])

    def test_exp_replies_reject_old_epoch_and_generation_before_forwarding(self):
        reader=self.located_reader();reader.experience_enabled=True;reader.tracking_epoch=9
        reader.submitted_sequence=reader.image_sequence
        results=[];reader.experience.connect(results.append)
        packet={'atMs':int(reader.last_frame*1000),'experience':{}}
        for generation,epoch in ((reader.generation-1,9),(reader.generation,8),(reader.generation,9)):
            reader.pending=True;reader.pending_experience=True
            reader.pending_generation=generation;reader.pending_tracking_epoch=epoch
            with patch.object(reader.process,'readAllStandardOutput',return_value=(json.dumps(packet)+'\n').encode()):
                reader.on_output()
            if generation!=reader.generation or epoch!=reader.tracking_epoch:self.assertEqual(results,[])
        self.assertEqual(len(results),1);self.assertEqual(results[0]['trackingEpoch'],9)

    def test_known_cover_invalidates_pending_crop_without_submitting_more_pixels(self):
        reader=self.located_reader();reader.experience_enabled=True
        pending=PendingPickupWorker();reader.pickup_worker=pending
        reader.exclude_regions=lambda:[reader.pickup_area(reader.tracking_area)]
        results=[];reader.experience.connect(results.append)
        reader.scan_pickups(time.monotonic())
        self.assertGreater(pending.invalidations,0)
        self.assertIsNone(pending.context)
        self.assertEqual(len(results),1)
        self.assertEqual(results[0]['pickups'],{'valid':False,'covered':True,'lines':[]})

    def test_stopping_tracking_releases_worker_even_when_main_capture_is_paused(self):
        reader=self.located_reader();reader.experience_enabled=True
        pending=PendingPickupWorker();reader.pickup_worker=pending
        reader.paused=True;reader.experience_enabled=False
        self.assertTrue(pending.closed)
        self.assertIsNone(reader.pickup_worker)


class PickupWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        cls.app=QApplication.instance() or QApplication([])
        if not reader_binary(ROOT).is_file():raise unittest.SkipTest('Build or install the pixel reader first')

    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.worker=PickupWorker(ROOT,self.directory.name)
        self.results=[];self.worker.result.connect(self.results.append)

    def tearDown(self):
        self.worker.close();self.worker.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.app.processEvents()
        self.directory.cleanup()

    def wait(self,condition):
        deadline=time.monotonic()+10
        while not condition():
            self.assertLess(time.monotonic(),deadline,'Pickup fixture reader did not finish')
            self.app.processEvents();time.sleep(.005)

    def frame(self,colour):
        image=QImage(256,128,QImage.Format.Format_RGBA8888);image.fill(QColor(colour));return image

    def test_invalidation_keeps_one_inflight_buffer_and_discards_its_result(self):
        worker=self.worker;first=self.frame('#302c29');second=self.frame('#282f36')
        self.assertFalse(worker.submit(first,time.monotonic(),1,2))
        self.wait(lambda:worker.process.state()==QProcess.ProcessState.Running)
        self.assertTrue(worker.submit(first,time.monotonic(),1,2,{'submitted':'first'}))
        original=worker.path.read_bytes()
        worker.invalidate();self.assertTrue(worker.pending);self.assertIsNone(worker.context)
        self.assertFalse(worker.submit(second,time.monotonic(),1,3))
        self.assertEqual(worker.path.read_bytes(),original)
        self.wait(lambda:not worker.pending)
        self.assertEqual(self.results,[]);self.assertFalse(worker.watchdog.isActive())
        self.assertTrue(worker.submit(second,time.monotonic(),1,3,{'submitted':'second'}))
        self.wait(lambda:bool(self.results))
        self.assertEqual(len(self.results),1)
        self.assertEqual(self.results[0]['captureGeneration'],1)
        self.assertEqual(self.results[0]['trackingEpoch'],3)
        self.assertEqual(self.results[0]['pickupNameProof'],{'submitted':'second'})
        self.assertIsNone(worker.context);self.assertEqual(worker.timings.maxlen,120)

    def test_oversized_output_and_timeout_revoke_context_and_terminate_only_our_worker(self):
        worker=self.worker;worker.pending=True;worker.context=(1,2,3,None)
        with patch.object(worker.process,'readAllStandardOutput',return_value=b'x'*(worker.MAX_RESULT_BYTES+1)),patch.object(worker.process,'kill') as kill:
            worker.on_output();kill.assert_called_once()
        self.assertIsNone(worker.context);self.assertEqual(worker.buffer,b'');self.assertEqual(self.results,[])
        worker.context=(1,2,3,None);worker.started_at=time.monotonic()-worker.TIMEOUT-.1
        with patch.object(worker.process,'kill') as kill:
            worker.check_timeout();kill.assert_called_once()
        self.assertIsNone(worker.context)
        worker.on_finished(0,QProcess.ExitStatus.NormalExit)
        self.assertFalse(worker.pending);self.assertFalse(worker.watchdog.isActive())

    def test_close_uses_bounded_waits_and_prevents_restart(self):
        worker=self.worker
        with patch.object(worker.process,'waitForFinished',side_effect=[False,True]) as wait,patch.object(worker.process,'kill') as kill:
            worker.close()
        self.assertEqual([call.args for call in wait.call_args_list],[(400,),(600,)])
        kill.assert_called_once();self.assertTrue(worker.closed)
        self.assertFalse(worker.submit(self.frame('#292929'),time.monotonic(),1,2))


if __name__=='__main__':unittest.main()
