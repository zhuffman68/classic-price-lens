"""Actual local reader IPC: EXP scheduling must preserve shop observations."""
import os
from pathlib import Path
import time
import unittest

from PySide6.QtCore import QCoreApplication, QEvent, QRect
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from price_lens.capture import PixelReader

ROOT = Path(__file__).resolve().parents[1]


class ExperienceCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
        cls.app = QApplication.instance() or QApplication([])

    def wait(self, condition):
        deadline = time.monotonic()+10
        while not condition():
            self.assertLess(time.monotonic(),deadline,"EXP/shop reader did not respond")
            self.app.processEvents()
            time.sleep(.005)

    def test_exp_only_results_preserve_stationary_shop_and_use_one_process(self):
        reader = PixelReader(ROOT)
        reader.auto_enabled = False
        reader.live_source = True
        reader.crop = QRect(0,0,1366,768)
        reader.experience_enabled = True
        shops, exp = [], []
        reader.reading.connect(shops.append)
        reader.experience.connect(lambda result:exp.append(result) if 'experience' in result else None)
        frame = QImage(1366,768,QImage.Format.Format_RGBA8888)
        frame.fill(QColor("#373f45"))
        painter = QPainter(frame)
        painter.drawImage(0,640,QImage(str(ROOT/"vendor/minerva/samples/exp-bar/100300__64.49--ideal-ratio-1366x768-strip.png")))
        painter.drawImage(340,120,QImage(str(ROOT/"vendor/minerva/samples/player-shop/gems-and-ores.png")))
        painter.end()
        try:
            self.wait(lambda:reader.process.state() == reader.process.ProcessState.Running)
            pid = reader.process.processId()
            reader.on_stream_frame(frame,time.monotonic())
            self.wait(lambda:bool(shops) and bool(exp))
            self.assertEqual(exp[-1]["experience"]["bar"]["exp"],100300)
            self.assertTrue(shops[-1]["shop"]["rows"])
            count = len(shops)
            reader.last_experience = time.monotonic()-2
            reader.on_stream_frame(frame,time.monotonic())
            self.wait(lambda:len(exp) >= 2)
            self.assertEqual(reader.process.processId(),pid)
            self.assertEqual(len(shops),count,"An EXP-only reply must not replace shop rows")
            reader.experience_enabled = False
            count = len(exp)
            reader.last_experience = 0
            reader.on_stream_frame(frame,time.monotonic())
            for _ in range(10):
                self.app.processEvents()
            self.assertEqual(len(exp),count)
        finally:
            reader.close()
            reader.deleteLater()
            QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
