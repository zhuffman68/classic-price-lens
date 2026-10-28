"""Verify bundled animation decoding, hidden-window idling and interrupted transitions."""
import os
from pathlib import Path
import unittest

from PySide6.QtCore import QPoint,QRect
from PySide6.QtGui import QMovie,QImageReader
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QLabel,QWidget,QVBoxLayout

from price_lens.branding import Brand
from price_lens.motion import AnimatedTabs,RollingLabel
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
            QTest.qWait(390)
            self.assertEqual(tabs.currentWidget().text(),"EXP")
            self.assertFalse(tabs.sliding)
            self.app.setProperty("reduceMotion",True);tabs.setCurrentIndex(0)
            self.assertFalse(tabs.sliding)
        finally:tabs.close();tabs.deleteLater();self.app.processEvents()

    def test_live_slide_keeps_zeros_visible_and_handles_mid_transition_updates(self):
        tabs=AnimatedTabs();tabs.resize(460,700);tabs.addTab(QLabel('Prices'),'Prices')
        page=QWidget();layout=QVBoxLayout(page);value=RollingLabel('0m 00s');layout.addWidget(value)
        tabs.addTab(page,'Tracking');self.app.setProperty('reduceMotion',False)
        try:
            tabs.show();self.app.processEvents();tabs.setCurrentIndex(1)
            self.assertTrue(tabs.sliding)
            self.assertEqual(value.roll.progress,1.0)
            tabs.animation.setCurrentTime(150)
            self.assertGreater(page.x(),0)
            self.assertLess(page.x(),tabs.width())
            value.setText('0m 01s');self.assertEqual(value.roll.text,'0m 01s')
            tabs.animation.setCurrentTime(300)
            self.assertFalse(tabs.sliding)
            self.assertFalse(tabs.widget(0).isVisible())
            self.assertTrue(value.isVisible())
            self.assertTrue(tabs.stack.layout().isEnabled())
        finally:tabs.close();tabs.deleteLater();self.app.processEvents()

    def test_slide_keeps_progress_and_visible_pages_when_the_viewport_resizes(self):
        tabs=AnimatedTabs();tabs.resize(460,700)
        tabs.addTab(QLabel('Prices'),'Prices');tabs.addTab(QLabel('Tracking'),'Tracking')
        self.app.setProperty('reduceMotion',False)
        try:
            tabs.show();self.app.processEvents();tabs.setCurrentIndex(1)
            tabs.animation.setCurrentTime(120)
            page=tabs.widget(1);fraction=page.x()/tabs.stack.width()
            tabs.resize(560,640);self.app.processEvents()
            self.assertTrue(tabs.sliding)
            self.assertGreaterEqual(tabs.animation.currentTime(),120)
            self.assertAlmostEqual(page.x()/tabs.stack.width(),fraction,delta=.02)
            self.assertTrue(tabs.widget(0).isVisible());self.assertTrue(page.isVisible())
            tabs.animation.setCurrentTime(300)
            self.assertFalse(tabs.sliding)
            self.assertEqual(page.pos(),tabs.stack.contentsRect().topLeft())
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
