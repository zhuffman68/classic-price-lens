"""Reject maximization while retaining normal resizing and minimization."""
import os
import unittest

from PySide6.QtCore import QCoreApplication,QEvent,Qt
from PySide6.QtWidgets import QApplication,QWidget
from price_lens.window_policy import NormalWindow


class WindowPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.window=QWidget();self.window.resize(460,700)
        self.policy=NormalWindow(self.window)
        self.window.show();self.app.processEvents()

    def tearDown(self):
        self.window.close();self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)

    def test_maximize_request_retains_normal_geometry_and_manual_resize_still_works(self):
        self.window.showMaximized();self.app.processEvents()
        self.assertFalse(self.window.isMaximized())
        self.assertEqual((self.window.width(),self.window.height()),(460,700))
        self.window.resize(540,740);self.app.processEvents()
        self.assertEqual((self.window.width(),self.window.height()),(540,740))

    def test_minimize_and_restore_remain_available(self):
        self.window.showMinimized();self.app.processEvents()
        self.assertTrue(self.window.isMinimized())
        self.window.showNormal();self.app.processEvents()
        self.assertFalse(self.window.isMinimized())
        self.assertFalse(self.window.isMaximized())
        flags=self.window.windowFlags()
        self.assertTrue(flags & Qt.WindowType.WindowMinimizeButtonHint)
        self.assertFalse(flags & Qt.WindowType.WindowMaximizeButtonHint)


if __name__ == '__main__':unittest.main()
