"""Native description bounds from public OCR samples, including clipped panels."""
from pathlib import Path
import unittest
from PySide6.QtCore import QRect
from PySide6.QtGui import QImage,QColor
from price_lens.tooltip_geometry import description_bounds,still_present

ROOT=Path(__file__).resolve().parents[1]


class TooltipGeometryTests(unittest.TestCase):
    def test_clipped_real_description_is_larger_than_its_recognized_name_line(self):
        image=QImage(str(ROOT/'vendor/minerva/samples/player-shop/equips-under-the-pointer-and-its-tooltip.png'))
        self.assertFalse(image.isNull())
        box=description_bounds(image,dict(x=214,y=150,width=164,height=18))
        self.assertIsNotNone(box)
        self.assertLessEqual(abs(box.x()-202),6)
        self.assertLessEqual(abs(box.y()-130),6)
        self.assertEqual(box.right(),image.width()-1)
        self.assertEqual(box.bottom(),image.height()-1)
        self.assertTrue(still_present(image,box))
        image.fill(QColor('#171c25'));self.assertFalse(still_present(image,box))

    def test_no_panel_is_inferred_from_an_unanchored_or_plain_image(self):
        image=QImage(800,800,QImage.Format.Format_RGBA8888);image.fill(QColor('#171c25'))
        self.assertIsNone(description_bounds(image,None))
        self.assertIsNone(description_bounds(image,dict(x=200,y=200,width=140,height=18)))
