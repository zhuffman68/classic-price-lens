"""Numeric safety, snapshot retirement and actual local worker transport."""
import json
import os
from pathlib import Path
import time
import unittest

from PySide6.QtCore import QRect,QProcess
from PySide6.QtGui import QImage,QPainter,QFontDatabase,QFont,QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from price_lens.chat_text import amounts,glossary,numbers_preserved,normalize
from price_lens.chat import ChatTranslation,stamp
from price_lens.annotations import AnnotationWindow

ROOT=Path(__file__).resolve().parents[1]


class ChatTextTests(unittest.TestCase):
    def test_explicit_units_and_unitless_numbers_remain_distinct(self):
        for original,expected in (("25만","250k"),("250만","2.5m"),("250k","250k"),("2.5m","2.5m"),("1억","100m")):
            with self.subTest(original=original):
                self.assertEqual(amounts(original)[0]["display"],expected)
        self.assertIsNone(amounts("250")[0]["amount"])
        self.assertEqual(amounts("250")[0]["display"],"250")
        self.assertFalse(numbers_preserved("250만 메소","250m mesos"))
        self.assertTrue(numbers_preserved("장공250만 팝니다","Glove ATT scroll 2.5m for sale"))
        self.assertFalse(numbers_preserved("250 팝니다","250k for sale"))
        self.assertFalse(numbers_preserved("장공 25만","Glove ATT scroll 25k 250k"))
        self.assertFalse(numbers_preserved("250 팝니다","250 mesos for sale"))
        self.assertFalse(numbers_preserved("250원","250 dollars"))
        self.assertTrue(numbers_preserved("250만 메소","2.5m mesos"))

    def test_game_phrases_and_ambiguous_substrings(self):
        self.assertEqual(glossary("심심해"),"I'm bored")
        self.assertEqual(glossary("홀리심볼 주세요"),"Holy Symbol please")
        self.assertIsNone(glossary("ㅍㅍ?"))
        self.assertIsNone(glossary("공팟 삼"))
        self.assertEqual(glossary("ㄳ"),"thanks")
        output=glossary("26표도 러시나 보너스팟 암데나 국산팟으로 갑니다")
        self.assertIn("Lv. 26 throwing-star thief",output)
        self.assertIn("Korean-speaking party",output)
        self.assertTrue(numbers_preserved("26표도 러시나 보너스팟 암데나 국산팟으로 갑니다",output))
        self.assertEqual(glossary("장공 250만 팝니다"),"Glove ATT scroll 2.5m for sale")
        self.assertEqual(normalize("보너스팟@@@@@@\n 갑니다##"),"보너스팟 갑니다")


class ChatSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
        cls.app=QApplication.instance() or QApplication([])

    def test_cards_retire_on_pixel_change_and_expiry_and_keep_game_bounds(self):
        chat=ChatTranslation(ROOT)
        image=QImage(500,300,QImage.Format.Format_RGB888);image.fill(QColor("#eeeeee"))
        box=[50,40,90,50]
        card={"box":box,"stamp":stamp(image,box),"until":time.monotonic()+3,"text":"hello","original":"안녕하세요","speaker":"Player","note":"Local"}
        chat.cards=[card]
        self.assertEqual(len(chat.annotations(image,1,1,[20,20,400,200])),1)
        changed=image.copy();p=QPainter(changed);p.fillRect(QRect(*box),QColor("#111111"));p.end()
        self.assertEqual(chat.annotations(changed,1,1,[20,20,400,200]),[])
        card["until"]=time.monotonic()-1;chat.cards=[card]
        self.assertEqual(chat.annotations(image,1,1,[20,20,400,200]),[])
        chat.close()

    def test_translation_card_wraps_and_fits_inside_game_without_changing_price_rows(self):
        window=AnnotationWindow(start_listener=False)
        try:
            window.read_command(json.dumps({"geometry":[0,0,900,700],"reduce_motion":True,"rows":[
                {"kind":"shop","key":"shop1","name":"Work Gloves","text":"FM 250,000","x":100,"y":40},
                {"kind":"translation","key":"chat1","name":"Player · Game-chat glossary","text":"Looking for a Kerning PQ bonus party, please invite me.","original":"표도 보너스팟 초대점여","x":790,"y":650,"bounds":[120,90,600,400]}]}))
            row=window.rows[1];box=window.label_rect(row,window.pos())
            self.assertTrue(QRect(120,90,600,400).contains(box))
            self.assertGreater(row["_english_height"],15)
            self.assertEqual(window.rows[0]["text"],"FM 250,000")
            self.assertFalse(window.grab().isNull())
        finally:window.close();window.deleteLater();self.app.processEvents()

    @unittest.skipUnless((ROOT/"models/korean-chat/rec.onnx").exists(),"Prepared local models are optional in a source checkout")
    def test_real_worker_reads_synthetic_korean_bubble_and_unloads(self):
        fid=QFontDatabase.addApplicationFont(str(ROOT/"price_lens/resources/fonts/Maplestory-Bold.ttf"))
        font=QFont(QFontDatabase.applicationFontFamilies(fid)[0]);font.setPixelSize(14)
        image=QImage(320,180,QImage.Format.Format_RGB888);image.fill(QColor("#202020"))
        painter=QPainter(image);painter.fillRect(40,30,160,70,QColor("#eeeeee"));painter.setPen(QColor("#000000"));painter.setFont(font)
        painter.drawText(55,55,"Player:");painter.drawText(55,80,"안녕하세요");painter.end()
        chat=ChatTranslation(ROOT);messages=[];chat.status.connect(messages.append)
        try:
            chat.enable(True)
            limit=time.monotonic()+15
            while not chat.ready and time.monotonic()<limit:QTest.qWait(10)
            self.assertTrue(chat.ready,messages)
            self.assertTrue(chat.request(image,image.rect(),[100,65]))
            self.assertFalse(chat.request(image,image.rect(),[100,65]))
            while chat.busy and time.monotonic()<limit:QTest.qWait(10)
            self.assertFalse(chat.busy,messages)
            self.assertEqual(len(chat.cards),1,messages)
            self.assertIn("hello",chat.cards[0]["text"].lower())
            process=chat.process;chat.enable(False)
            self.assertIsNone(chat.process)
            self.assertEqual(process.state(),QProcess.ProcessState.NotRunning)
        finally:chat.close()
