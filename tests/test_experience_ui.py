"""Exercise EXP controls and real local persistence without starting screen sharing."""
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent
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

    def test_start_requires_connected_fresh_reading_and_saves_to_history(self):
        self.assertFalse(self.panel.start_button.isEnabled())
        self.panel.set_connected(True)
        self.feed(2000)
        self.assertTrue(self.panel.start_button.isEnabled())
        self.panel.start_button.click()
        self.assertFalse(self.panel.start_button.isEnabled())
        for second in range(1,32):
            self.feed(2000+second*10,1)
        self.assertIn("% / 5 min",self.panel.rate.text())
        self.assertIn("Observed:",self.panel.details.text())
        self.panel.save_button.click()
        self.assertEqual(self.panel.table.rowCount(),1)
        self.assertEqual(self.panel.history.rows()[0]["exp"],310)
        self.assertIsNone(self.panel.tracker.run)

    def test_global_context_loss_does_not_count_hidden_gain(self):
        self.panel.set_connected(True)
        self.feed(2000)
        self.panel.start()
        self.feed(2010,1)
        self.panel.set_connected(False)
        self.panel.set_connected(True)
        self.feed(2500,1)
        self.feed(2510,1)
        self.assertEqual(self.panel.tracker.run.exp,20)

    def test_exp_disable_pauses_session_and_drops_incoming_samples(self):
        self.panel.set_connected(True)
        self.feed(2000)
        self.panel.start()
        self.feed(2010,1)
        self.panel.enabled_check.setChecked(False)
        self.feed(3000,1)
        self.assertEqual(self.panel.tracker.run.exp,10)
        self.assertTrue(self.panel.tracker.paused)
        self.assertIn("off",self.panel.state.text())

    def test_stale_reading_cannot_start_and_overlay_is_independent_of_prices(self):
        self.panel.set_connected(True)
        self.feed(2000)
        self.now += 6
        self.panel.refresh()
        self.assertFalse(self.panel.start_button.isEnabled())
        self.assertIsNone(self.panel.overlay_row())


if __name__ == "__main__":
    unittest.main()
