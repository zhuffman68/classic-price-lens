import os
from types import SimpleNamespace
import unittest
from PySide6.QtGui import QImage,QPixmap
from PySide6.QtWidgets import QApplication
from price_lens.windows_capture import WindowsDesktopCapture


class Screen:
    def __init__(self, colour):
        self.image=QImage(20,10,QImage.Format.Format_RGBA8888);self.image.fill(colour)
        self.windows=[]
    def grabWindow(self, window):
        self.windows.append(window)
        return QPixmap.fromImage(self.image)


class WindowsDesktopCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.first=Screen('red');self.second=Screen('blue')
        self.desktop=SimpleNamespace(screens=lambda:[self.first,self.second])
        self.capture=WindowsDesktopCapture(self.desktop)
        self.frames=[];self.errors=[]
        self.capture.image_ready.connect(self.frames.append)
        self.capture.errorOccurred.connect(lambda code,text:self.errors.append(text))

    def tearDown(self):
        self.capture.stop();self.capture.deleteLater();self.app.processEvents()

    def test_only_selected_os_display_is_read_with_desktop_id_zero(self):
        self.capture.setScreen(self.second);self.capture.start();self.capture.grab()
        self.assertTrue(self.frames)
        self.assertEqual(self.frames[-1].pixelColor(0,0).name(),'#0000ff')
        self.assertFalse(self.first.windows)
        self.assertEqual(set(self.second.windows),{0})

    def test_pause_and_socket_backpressure_skip_os_grabs(self):
        self.capture.setScreen(self.first);self.capture.setPaused(True);self.capture.start();self.capture.grab()
        self.assertFalse(self.first.windows);self.assertFalse(self.capture.timer.isActive())
        self.capture.setPaused(False);self.capture.can_capture=lambda:False;self.capture.grab()
        self.assertFalse(self.first.windows)

    def test_empty_capture_stops_after_three_attempts_and_reports_once(self):
        self.first.image=QImage();self.capture.setScreen(self.first);self.capture.start()
        for _ in range(6):self.capture.grab()
        self.assertEqual(len(self.first.windows),3)
        self.assertEqual(len(self.errors),1)
        self.assertFalse(self.capture.isActive());self.assertFalse(self.capture.timer.isActive())

    def test_removed_display_cannot_fall_back_to_primary(self):
        self.capture.setScreen(self.second);self.desktop.screens=lambda:[self.first];self.capture.start()
        for _ in range(3):self.capture.grab()
        self.assertFalse(self.first.windows);self.assertFalse(self.second.windows)
        self.assertIn('no longer available',self.errors[0])

    def test_capture_rate_is_bounded(self):
        self.capture.setMaximumFrameRate(1000);self.assertEqual(self.capture.timer.interval(),100)
        self.capture.setMaximumFrameRate(1);self.assertEqual(self.capture.timer.interval(),1000)
