"""Actual reader IPC fed generated screenshots; never starts OS sharing."""
import os
from pathlib import Path
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from price_lens.capture import PixelReader
from test_game_area import game_frame

ROOT=Path(__file__).resolve().parents[1]


class AreaCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
        cls.app=QApplication.instance() or QApplication([])

    def test_pixel_tracker_rejects_old_coordinates_and_stops_when_covered(self):
        reader=PixelReader(ROOT)
        reader.live_source=True
        results=[]
        reader.reading.connect(results.append)
        def wait_for(predicate):
            deadline=time.monotonic()+10
            while not predicate():
                self.assertLess(time.monotonic(),deadline,"Pixel reader did not finish fixture")
                self.app.processEvents()
                time.sleep(0.005)
        try:
            wait_for(lambda:reader.process.state()==reader.process.ProcessState.Running)
            reader.on_stream_frame(game_frame(),time.monotonic())
            wait_for(lambda:bool(results))
            self.assertIsNotNone(reader.game_area)
            self.assertEqual(len(reader.game_guards),2)
            reader.on_stream_frame(game_frame(x=320,y=180),time.monotonic())
            self.assertIsNone(reader.game_area,"Old coordinates must disappear before the new OCR result")
            wait_for(lambda:reader.game_area is not None)
            self.assertLessEqual(abs(reader.game_area.x()-320),8)
            blank=QImage(1600,900,QImage.Format.Format_RGBA8888)
            blank.fill(QColor("#171c25"))
            count=len(results)
            reader.on_stream_frame(blank,time.monotonic())
            self.assertIsNone(reader.game_area)
            wait_for(lambda:len(results)>count)
            self.assertIsNone(results[-1]["gameArea"])
            self.assertIsNone(results[-1]["shop"])
            self.assertEqual(reader.stream.socket.state(),reader.stream.socket.LocalSocketState.UnconnectedState)
        finally:
            reader.close()
            reader.deleteLater()
            QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
            self.app.processEvents()

    def test_stationary_shop_skips_ocr_until_geometry_check_is_due(self):
        reader=PixelReader(ROOT)
        reader.live_source=True
        results=[]
        reader.reading.connect(results.append)
        def wait_for(predicate):
            deadline=time.monotonic()+10
            while not predicate():
                self.assertLess(time.monotonic(),deadline,"Reader did not finish shop fixture")
                self.app.processEvents()
                time.sleep(0.005)
        try:
            wait_for(lambda:reader.process.state()==reader.process.ProcessState.Running)
            frame=game_frame(width=1200,height=800,desktop=(1600,1000))
            painter=QPainter(frame)
            painter.drawImage(340,180,QImage(str(ROOT/'vendor/minerva/samples/player-shop/gems-and-ores.png')))
            painter.end()
            reader.on_stream_frame(frame,time.monotonic())
            wait_for(lambda:bool(results))
            self.assertIsNotNone(reader.shop_rect)
            self.assertIsNotNone(reader.shop_fingerprint)
            count=len(results)
            submitted=reader.pending_since
            # Isolate the geometry interval from CPU contention during real OCR.
            with patch("price_lens.capture.time.monotonic", return_value=reader.last_geometry_check+.01):
                reader.on_stream_frame(frame,time.monotonic())
                self.app.processEvents()
                self.assertEqual(reader.pending_since,submitted,"Unchanged pixels should skip another OCR request")
            self.assertEqual(len(results),count)
            reader.last_geometry_check=time.monotonic()-1
            reader.on_stream_frame(frame,time.monotonic())
            wait_for(lambda:len(results)>count)
            self.assertIsNotNone(reader.game_area)
        finally:
            reader.close()
            reader.deleteLater()
            QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
            self.app.processEvents()
