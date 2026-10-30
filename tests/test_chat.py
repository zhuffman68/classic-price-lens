"""Numeric safety, snapshot retirement and actual local worker transport."""
import json
import os
from pathlib import Path
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QRect,QProcess,QCoreApplication,QEvent
from PySide6.QtGui import QImage,QPainter,QFontDatabase,QFont,QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from price_lens.chat_text import amounts,glossary,numbers_preserved,normalize
from price_lens.chat import ChatTranslation,stamp
from price_lens.annotations import AnnotationWindow

ROOT=Path(__file__).resolve().parents[1]


class ChatTextTests(unittest.TestCase):
    def test_korean_banner_heading_is_not_discarded_as_a_speaker_name(self):
        from price_lens.chat_worker import scan
        image=QImage(500,200,QImage.Format.Format_RGB888);image.fill(QColor('#202030'))
        class Reader:
            def read(self,_):return 'ExamplePlayer님의 꽃바람 메시지:',.96
        class Translator:
            def translate(self,_):return 'Message from ExamplePlayer','Local'
        rows=[]
        with patch('price_lens.chat_ocr.bubbles',return_value=[]),patch('price_lens.chat_ocr.text_regions',return_value=[[50,40,200,14]]):
            result=scan(image,Reader(),Translator(),rows.append)
        self.assertEqual(result['count'],1);self.assertEqual(rows[0]['speaker'],'')
        self.assertIn('메시지',rows[0]['original'])
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

    def test_slow_scan_does_not_add_another_full_wait_and_fast_scans_stay_bounded(self):
        class Pipe:
            def __init__(self):self.output=b''
            def readAllStandardOutput(self):value=self.output;self.output=b'';return value
        chat=ChatTranslation(ROOT);chat.process=pipe=Pipe();chat.enabled=chat.ready=chat.watching=True;chat.until=104
        try:
            for duration,expected in ((.75,50),(.05,200)):
                chat.identity=chat.batch_identity=7;chat.busy=True;chat.started=100-duration
                pipe.output=(json.dumps({'id':7,'done':{'count':0}})+'\n').encode()
                with patch('price_lens.chat.time.monotonic',return_value=100):chat.receive()
                self.assertFalse(chat.busy);self.assertTrue(chat.watching);self.assertEqual(chat.cadence.interval(),expected)
        finally:
            chat.process=None;chat.close();chat.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)

    def test_restarting_a_busy_scan_drops_late_results_and_requests_only_latest_frame(self):
        class Pipe:
            def __init__(self):self.writes=[];self.output=b''
            def write(self,data):self.writes.append(data)
            def readAllStandardOutput(self):data=self.output;self.output=b'';return data
        chat=ChatTranslation(ROOT);pipe=Pipe();chat.process=pipe;chat.enabled=chat.ready=True
        image=QImage(400,240,QImage.Format.Format_RGB888);image.fill(QColor('#eeeeee'))
        requests=[]
        def submit():requests.append(chat.request(image,image.rect()))
        chat.frame_requested.connect(submit)
        try:
            chat.start_scan();old=chat.identity
            self.assertTrue(chat.busy);self.assertEqual(requests,[True])
            chat.start_scan();self.assertGreater(chat.identity,old)
            self.assertEqual(json.loads(pipe.writes[-1]),{'cancel_before':chat.identity})
            row={'box':[50,40,90,50],'speaker':'Player','original':'안녕하세요','text':'hello','note':'Local'}
            pipe.output=(json.dumps({'id':old,'row':row})+'\n'+json.dumps({'id':old,'done':{'count':1}})+'\n').encode()
            chat.receive();self.assertEqual(chat.cards,[]);QTest.qWait(20)
            self.assertEqual(requests,[True,True]);self.assertTrue(chat.busy)
            pipe.output=(json.dumps({'id':chat.identity,'row':row})+'\n'+json.dumps({'id':chat.identity,'done':{'count':1}})+'\n').encode()
            chat.receive();self.assertEqual(len(chat.cards),1);self.assertEqual(len(chat.history),1)
            self.assertTrue(chat.watching);self.assertTrue(chat.cadence.isActive())
            previous_until=chat.until;chat.start_scan();self.assertEqual(len(chat.cards),1)
            self.assertGreaterEqual(chat.until,previous_until);self.assertTrue(chat.window_timer.isActive())
        finally:
            chat.process=None;chat.close();chat.deleteLater()
            QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.app.processEvents()

    def test_no_result_notice_expires_without_another_frame(self):
        chat=ChatTranslation(ROOT);chat.enabled=chat.ready=True;messages=[];chat.status.connect(messages.append)
        try:
            chat.announce('No readable Korean found');self.assertTrue(chat.has_overlay)
            chat.notice_timer.start(10);QTest.qWait(30)
            self.assertFalse(chat.has_overlay);self.assertEqual(messages[-1],'Ready · local Korean translation')
        finally:
            chat.close();chat.deleteLater()
            QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.app.processEvents()

    def test_cards_linger_after_disappearance_and_history_stays(self):
        chat=ChatTranslation(ROOT)
        image=QImage(500,300,QImage.Format.Format_RGB888);image.fill(QColor("#eeeeee"))
        box=[50,40,90,50]
        card={"id":1,"box":box,"stamp":stamp(image,box),"gone_at":None,"text":"hello","original":"안녕하세요","speaker":"Player","note":"Local"}
        chat.cards=[card];chat.history=[{k:card[k] for k in ('text','original','speaker','note')}]
        try:
            with patch('price_lens.chat.time.monotonic',return_value=10):
                self.assertEqual(len(chat.annotations(image,1,1,[20,20,400,200])),1)
            changed=image.copy();p=QPainter(changed);p.fillRect(QRect(*box),QColor("#111111"));p.end()
            with patch('price_lens.chat.time.monotonic',return_value=11):
                self.assertEqual(len(chat.annotations(changed,1,1,[20,20,400,200])),1)
            with patch('price_lens.chat.time.monotonic',return_value=12.6):
                self.assertEqual(chat.annotations(changed,1,1,[20,20,400,200]),[])
            self.assertEqual(len(chat.history),1)
        finally:
            chat.close();chat.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.app.processEvents()

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
        image=QImage(900,400,QImage.Format.Format_RGB888);image.fill(QColor("#202020"))
        painter=QPainter(image);painter.fillRect(40,30,160,70,QColor("#eeeeee"));painter.setPen(QColor("#000000"));painter.setFont(font)
        painter.drawText(55,55,"Player:");painter.drawText(55,80,"안녕하세요")
        painter.fillRect(650,250,160,70,QColor('#eeeeee'));painter.drawText(665,275,'Other:');painter.drawText(665,300,'감사합니다');painter.end()
        chat=ChatTranslation(ROOT);messages=[];chat.status.connect(messages.append)
        try:
            chat.enable(True)
            limit=time.monotonic()+15
            while not chat.ready and time.monotonic()<limit:QTest.qWait(10)
            self.assertTrue(chat.ready,messages)
            self.assertTrue(chat.request(image,image.rect()))
            self.assertFalse(chat.request(image,image.rect()))
            while chat.busy and time.monotonic()<limit:QTest.qWait(10)
            self.assertFalse(chat.busy,messages)
            self.assertEqual(len(chat.cards),2,messages)
            self.assertIn("hello",chat.cards[0]["text"].lower())
            process=chat.process;chat.enable(False)
            self.assertIsNone(chat.process)
            self.assertEqual(process.state(),QProcess.ProcessState.NotRunning)
        finally:
            chat.close();chat.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.app.processEvents()
