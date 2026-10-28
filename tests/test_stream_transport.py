"""Exercise real local sockets with synthetic pixels, without any OS sharing requests."""
import os
from pathlib import Path
import tempfile
import time
import unittest
import sys
import uuid
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent, QRect
from PySide6.QtGui import QColor, QGuiApplication, QImage
from PySide6.QtWidgets import QApplication

from price_lens.stream import CaptureServer, StreamClient


class FakeCapture:
    def __init__(self):
        self.active = False
        self.starts = 0
        self.frame_rate = 10
        self.failure = ""

    def error(self):
        from PySide6.QtMultimedia import QScreenCapture
        return QScreenCapture.Error.CapturingNotSupported if self.failure else QScreenCapture.Error.NoError

    def errorString(self):
        return self.failure

    def setMaximumFrameRate(self, value):
        self.frame_rate = value

    def setScreen(self, screen):
        pass

    def isActive(self):
        return self.active

    def start(self):
        self.active = True
        self.starts += 1


class FakeFrame:
    def __init__(self, image):
        self.image = image

    def toImage(self):
        return self.image


class LocalFrameTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        name = "ClassicPriceLens-test-" + uuid.uuid4().hex if sys.platform == "win32" else str(Path(self.directory.name) / "test-socket")
        self.patcher = patch("price_lens.stream.socket_name", return_value=name)
        self.patcher.start()
        self.screen_patcher = patch("price_lens.stream.screen_for_rectangle", return_value=self.app.primaryScreen())
        self.screen_patcher.start()
        self.server = CaptureServer(self.app)
        self.fake_capture = FakeCapture()
        self.server.capture = self.fake_capture
        self.client = StreamClient(Path(__file__).resolve().parents[1])
        self.received = []
        self.client.frame.connect(lambda image, captured: self.received.append((image, captured)))
        self.client.start(QRect(10, 0, 10, 6), QRect(0, 0, 30, 6))
        self.until(lambda: self.fake_capture.starts == 1)

    def until(self, predicate):
        end = time.monotonic() + 2
        while not predicate() and time.monotonic() < end:
            self.app.processEvents()
            time.sleep(0.001)
        self.assertTrue(predicate(), "Local frame transport did not finish")

    def tearDown(self):
        self.client.stop(keep_session=True)
        self.app.processEvents()
        self.server.close()
        self.client.deleteLater()
        self.server.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.patcher.stop()
        self.screen_patcher.stop()
        self.directory.cleanup()

    def image(self):
        image = QImage(30 if sys.platform == "linux" else 10, 6, QImage.Format.Format_RGBA8888)
        image.fill(QColor("#1234ab"))
        return image

    def test_qimage_memoryview_crosses_the_real_socket_without_png(self):
        self.server.on_frame(FakeFrame(self.image()))
        self.until(lambda: len(self.received) == 1)
        image, captured = self.received[0]
        self.assertEqual((image.width(), image.height()), (10, 6))
        self.assertEqual(image.pixelColor(4, 4), QColor("#1234ab"))
        self.assertLess(time.monotonic() - captured, 1)

    def test_disconnected_display_is_rejected_without_delivering_another_monitor(self):
        messages=[];self.client.status.connect(messages.append)
        with patch('price_lens.stream.screen_for_rectangle',return_value=None):
            self.client.start(QRect(300,0,10,6),QRect(0,0,310,6))
            self.until(lambda:any('no longer available' in message for message in messages))
        self.assertTrue(all(value is None for value in self.server.clients.values()))
        self.server.on_frame(FakeFrame(self.image()))
        self.app.processEvents()
        self.assertEqual(self.received,[])

    def test_slow_consumer_drops_older_frames_instead_of_queuing_them(self):
        self.server.on_frame(FakeFrame(self.image()))
        self.server.last_frame = 0
        self.server.on_frame(FakeFrame(self.image()))
        self.until(lambda: len(self.received) == 1)
        self.assertEqual(len(self.received), 1)

    def test_new_ui_connection_reuses_the_existing_sharing_session(self):
        self.client.stop(keep_session=True)
        self.until(lambda: not self.server.clients)
        self.client.start(QRect(10, 0, 10, 6), QRect(0, 0, 30, 6))
        self.until(lambda: bool(self.server.clients) and all(self.server.clients.values()))
        self.assertEqual(self.fake_capture.starts, 1)
        self.server.last_frame = 0
        self.server.on_frame(FakeFrame(self.image()))
        self.until(lambda: len(self.received) == 1)

    def test_pause_resume_keeps_the_same_session_and_skips_frame_delivery(self):
        self.client.set_paused(True)
        self.until(lambda: len(self.server.paused_clients) == 1)
        self.assertEqual(self.fake_capture.frame_rate, 1)
        self.server.on_frame(FakeFrame(self.image()))
        self.app.processEvents()
        self.assertEqual(self.received, [])
        self.assertTrue(self.fake_capture.isActive())
        self.assertFalse(self.server.idle.isActive())
        self.client.start(QRect(10, 0, 10, 6), QRect(0, 0, 30, 6))
        self.until(lambda: not self.server.paused_clients)
        self.server.on_frame(FakeFrame(self.image()))
        self.until(lambda: len(self.received) == 1)
        self.assertEqual(self.fake_capture.frame_rate, 10)
        self.assertEqual(self.fake_capture.starts, 1)

    def test_constructor_failure_is_reported_without_waiting_for_a_missing_signal(self):
        self.fake_capture.active = False
        self.fake_capture.failure = "Capturing is not supported on this platform"
        statuses = []
        self.client.status.connect(statuses.append)
        self.client.send_subscription()
        self.until(lambda: any(message.startswith("OS capture:") for message in statuses))
        self.assertIn(self.fake_capture.failure, statuses[-1])
        self.assertEqual(self.fake_capture.starts, 1)


class CaptureStartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.folder = Path(self.directory.name)
        self.name = "ClassicPriceLens-startup-test-" + uuid.uuid4().hex
        self.paths = patch("price_lens.stream.socket_name", return_value=self.name)
        self.cache = patch("price_lens.stream.cache_directory", return_value=self.folder)
        self.paths.start()
        self.cache.start()
        self.client = StreamClient(Path(__file__).resolve().parents[1])
        self.statuses = []
        self.client.status.connect(self.statuses.append)

    def tearDown(self):
        self.client.stop(keep_session=True)
        self.client.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.paths.stop()
        self.cache.stop()
        self.directory.cleanup()

    def until_stopped(self):
        end = time.monotonic() + 2
        while self.client.active and time.monotonic() < end:
            self.app.processEvents()
            time.sleep(0.001)
        self.assertFalse(self.client.active)
        self.assertFalse(self.client.retry_timer.isActive())
        self.assertFalse(self.client.connect_timer.isActive())

    def test_failed_launch_reports_an_error_and_stops_retrying(self):
        with patch.object(self.client.launcher, "startDetached", return_value=False) as launch:
            self.client.start(QRect(0, 0, 10, 10), QRect(0, 0, 10, 10))
            self.until_stopped()
            launch.assert_called_once()
        self.assertTrue(any("helper could not start" in message for message in self.statuses))

    def test_missing_helper_has_a_deadline_before_any_os_chooser(self):
        self.client.connect_timer.setInterval(25)
        with patch.object(self.client.launcher, "startDetached", return_value=True) as launch:
            self.client.start(QRect(0, 0, 10, 10), QRect(0, 0, 10, 10))
            self.until_stopped()
            launch.assert_called_once()
        self.assertTrue(any("helper did not connect" in message for message in self.statuses))
