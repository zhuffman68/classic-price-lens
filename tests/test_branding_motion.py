"""Verify bundled animation decoding, hidden-window idling and interrupted transitions."""
import os
from pathlib import Path
import unittest

from PySide6.QtCore import QPoint,QRect
from PySide6.QtGui import QMovie,QImageReader
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QLabel,QWidget

from price_lens.branding import Brand
from price_lens.motion import AnimatedTabs
from price_lens.annotations import AnnotationWindow


class BrandingMotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
        cls.app=QApplication.instance() or QApplication([])

    def tearDown(self):self.app.setProperty("reduceMotion",False)

    def test_real_sprite_decodes_animates_and_stops_when_hidden_or_reduced(self):
        window=QWidget();brand=Brand(Path(__file__).resolve().parents[1],window)
        self.app.setProperty("reduceMotion",False)
        try:
            self.assertTrue(brand.sprite.movie.isValid())
            self.assertGreater(brand.sprite.movie.frameCount(),1)
            frames=[];brand.sprite.movie.frameChanged.connect(frames.append)
            window.show();brand.show();brand.sync();QTest.qWait(350)
            self.assertGreater(len(frames),1)
            window.hide();self.app.processEvents()
            self.assertEqual(brand.sprite.movie.state(),QMovie.MovieState.Paused)
            self.app.setProperty("reduceMotion",True)
            window.show();brand.sync();self.app.processEvents()
            self.assertEqual(brand.sprite.movie.state(),QMovie.MovieState.Paused)
        finally:window.close();window.deleteLater();self.app.processEvents()

    def test_complete_original_frame_delays_and_attack_return(self):
        window=QWidget();brand=Brand(Path(__file__).resolve().parents[1],window)
        try:
            self.app.setProperty("reduceMotion",False)
            for movie,expected in ((brand.sprite.movie,[120,150,150,250]),
                                   (brand.sprite.attack,[200,150,300,100,100,250,300,100,100,150,500])):
                delays=[]
                reader=QImageReader(movie.fileName())
                for frame in range(reader.imageCount()):
                    self.assertFalse(reader.read().isNull());delays.append(reader.nextImageDelay())
                self.assertEqual(delays,expected)
            window.show();brand.show();brand.sync();self.app.processEvents()
            brand.sprite.throw();self.assertIs(brand.sprite.current,brand.sprite.attack)
            for _ in range(140):
                QTest.qWait(25)
                if brand.sprite.current is brand.sprite.movie:break
            self.assertIs(brand.sprite.current,brand.sprite.movie)
            self.assertEqual(brand.sprite.attack.state(),QMovie.MovieState.NotRunning)
        finally:window.close();window.deleteLater();self.app.processEvents()

    def test_rapid_tab_changes_retire_the_old_transition_and_show_latest_page(self):
        tabs=AnimatedTabs();tabs.resize(480,500)
        for name in ("Prices","Search","EXP"):tabs.addTab(QLabel(name),name)
        try:
            self.app.setProperty("reduceMotion",False)
            tabs.show();self.app.processEvents()
            for index in (1,2,0,2):tabs.setCurrentIndex(index);self.app.processEvents()
            QTest.qWait(180)
            self.assertEqual(tabs.currentWidget().text(),"EXP")
            self.assertIsNone(tabs.snapshot)
            self.app.setProperty("reduceMotion",True);tabs.setCurrentIndex(0)
            self.assertIsNone(tabs.snapshot)
        finally:tabs.close();tabs.deleteLater();self.app.processEvents()

    def test_exp_anchor_uses_game_bottom_left_for_two_and_three_lines(self):
        import json
        window=AnnotationWindow(start_listener=False)
        try:
            for extra in ("","600 EXP/min · 36,000 EXP/hour"):
                window.read_command(json.dumps({"geometry":[0,0,1600,1000],"reduce_motion":True,
                    "rows":[{"key":"experience","kind":"experience","x":0,"y":0,"anchor":"bottom_left",
                             "bounds":[320,200,800,600],"name":"Lv. 30 in ≈ 18m 40s","text":"+0.4%/min · +24%/hour","extra":extra}]}).encode())
                rect=window.label_rect(window.rows[0],QPoint(0,0))
                self.assertEqual(rect.left(),324)
                self.assertEqual(rect.bottom(),795)
                self.assertTrue(QRect(320,200,800,600).contains(rect))
        finally:window.close();window.deleteLater();self.app.processEvents()
