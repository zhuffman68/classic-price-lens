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
