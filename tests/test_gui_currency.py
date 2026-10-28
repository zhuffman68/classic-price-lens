"""Visible currency icons retain semantic text and stay out of overlay strings."""
import os,unittest
from PySide6.QtWidgets import QApplication
from price_lens.motion import MotionLabel,RollingLabel
from price_lens.number_motion import NumberRoll


class CurrencyUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        cls.app=QApplication.instance() or QApplication([])

    def test_gui_price_renders_coin_and_preserves_plain_text(self):
        label=RollingLabel('1,200 mesos');label.resize(220,32)
        label.setStyleSheet('background:#171c25;color:white;font-size:17px');label.show();self.app.processEvents()
        self.assertEqual(label.text(),'1,200 mesos')
        self.assertEqual(label.roll.text,'1,200 \ufffc')
        image=label.grab().toImage()
        self.assertTrue(any((p:=image.pixelColor(x,y)).red()>150 and 90<p.green()<230 and p.blue()<90
                            for y in range(image.height()) for x in range(image.width())))
        label.close();label.deleteLater()

    def test_wrapped_caption_keeps_units_semantic_and_overlay_rolls_keep_words(self):
        label=MotionLabel('Read your meso balance in the inventory.');label.setWordWrap(True);label.resize(210,50)
        label.show();self.app.processEvents();self.assertGreater(label.heightForWidth(160),0)
        self.assertIn('meso balance',label.text())
        raw=NumberRoll('FM 1,200 mesos')
        self.assertNotIn('\ufffc',raw.text)
        label.close();label.deleteLater()
