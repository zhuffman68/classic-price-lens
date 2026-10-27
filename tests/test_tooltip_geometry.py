"""Native description bounds from public OCR samples, including clipped panels."""
from pathlib import Path
import unittest
from PySide6.QtCore import QRect
from PySide6.QtGui import QImage,QColor
from price_lens.tooltip_geometry import description_bounds,still_present,TooltipReference

ROOT=Path(__file__).resolve().parents[1]


class TooltipGeometryTests(unittest.TestCase):
    def test_own_price_cards_do_not_clip_the_native_panel_bounds(self):
        from PySide6.QtGui import QPainter
        image=QImage(800,600,QImage.Format.Format_RGBA8888);image.fill(QColor('#eeeeee'))
        painter=QPainter(image);painter.fillRect(QRect(200,200,300,180),QColor('#464b78'))
        masks=[QRect(350,y,240,36) for y in (195,235,275,315)]
        for mask in masks:painter.fillRect(mask,QColor('#161c26'))
        painter.end();area=dict(x=212,y=211,width=160,height=12)
        bounds=description_bounds(image,area,masks)
        self.assertIsNotNone(bounds);self.assertGreaterEqual(bounds.right(),499)
        self.assertGreaterEqual(bounds.bottom(),379)
    def test_brief_miss_retains_only_the_same_visible_item_and_stationary_pointer(self):
        image=QImage(str(ROOT/'vendor/minerva/samples/player-shop/equips-under-the-pointer-and-its-tooltip.png'))
        found={'name':'Fixture item','area':dict(x=214,y=150,width=164,height=18),'_pointer':[60,20]}
        for reason in ('gone','name_changed','pointer_moved','expired'):
            with self.subTest(reason=reason):
                tracker=TooltipReference();self.assertIs(tracker.observe(found,image,(60,20),now=1),found)
                self.assertIsNotNone(tracker.panel)
                self.assertIs(tracker.observe(None,image,(60,20),now=1.2),found)
                changed=image.copy();point=(60,20);now=1.25
                if reason=='gone':changed.fill(QColor('#171c25'))
                if reason=='name_changed':
                    from PySide6.QtGui import QPainter
                    painter=QPainter(changed);painter.fillRect(QRect(214,150,164,18),QColor('#555577'));painter.end()
                if reason=='pointer_moved':point=(120,20)
                if reason=='expired':now=1.5
                self.assertIsNone(tracker.observe(None,changed,point,now=now))

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
