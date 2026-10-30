"""One event per verified arrival, not one event per OCR crop or surface."""
import json,os
from pathlib import Path
import unittest
from unittest.mock import patch
from PySide6.QtCore import QRect,QCoreApplication,QEvent
from PySide6.QtGui import QImage,QPainter,QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from price_lens.chat import ChatTranslation
from price_lens.translation_ui import TranslationPanel

ROOT=Path(__file__).resolve().parents[1]


class Pipe:
    def __init__(self):self.writes=[];self.output=b''
    def write(self,data):self.writes.append(data)
    def readAllStandardOutput(self):value=self.output;self.output=b'';return value


class ChatEventTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen');cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.chat=ChatTranslation(ROOT)
        self.image=QImage(800,600,QImage.Format.Format_RGB888);self.image.fill(QColor('#eeeeee'))
        painter=QPainter(self.image)
        for x,y in ((205,105),(237,125),(260,137),(21,503),(55,507),(450,108)):
            painter.fillRect(x,y,3,9,QColor('#121212'))
        painter.end();self.chat.frame=self.image.copy();self.chat.region=self.image.rect();self.chat.identity=1

    def tearDown(self):
        self.chat.process=None;self.chat.close();self.chat.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.app.processEvents()

    @staticmethod
    def row(role,box,speaker='ExamplePlayer',original='같이 사냥해요'):
        return dict(box=box,speaker=speaker,original=original,text='Let us train together',note='Local',source_role=role,role_verified=True)

    def accept(self,row,at=10):
        with patch('price_lens.chat.time.monotonic',return_value=at):self.chat.accept_row(row)

    def test_bubble_and_first_chat_line_share_one_event_in_either_arrival_order(self):
        bubble=self.row('bubble',[200,100,180,70]);line=self.row('chat',[20,500,260,18])
        for first,second in ((bubble,line),(line,bubble)):
            self.chat.clear();self.chat.frame=self.image.copy();self.chat.region=self.image.rect()
            self.accept(first);self.accept(second,11)
            self.assertEqual(len(self.chat.cards),1);self.assertEqual(len(self.chat.history),1)
            card=self.chat.cards[0];self.assertEqual(card['source_role'],'bubble')
            self.assertEqual(len(card['sources']),2)
            with patch('price_lens.chat.time.monotonic',return_value=11):
                rows=self.chat.annotations(self.image,1,1,[0,0,800,600])
            self.assertEqual(len(rows),1);self.assertEqual(len(rows[0]['source_boxes']),2)
            self.assertTrue(rows[0]['source_verified']);self.assertTrue(rows[0]['anchor_visible'])

    def test_other_people_anonymous_text_and_separate_equal_chat_lines_remain_distinct(self):
        self.accept(self.row('bubble',[200,100,180,70],speaker='ExampleOne'))
        self.accept(self.row('chat',[20,500,260,18],speaker='ExampleTwo'),11)
        self.assertEqual(len(self.chat.history),2)

    def test_continuous_bubble_prevents_duplicate_when_chat_background_changes(self):
        bubble=self.row('bubble',[200,100,180,70]);line=self.row('chat',[20,500,260,18])
        self.accept(bubble);self.accept(line,11)
        changed=self.image.copy();p=QPainter(changed);p.fillRect(QRect(20,500,260,18),QColor('#909090'));p.end()
        self.chat.frame=changed;self.chat.identity+=1;self.accept(line,12)
        self.assertEqual(len(self.chat.cards),1);self.assertEqual(len(self.chat.history),1)
        self.assertEqual(self.chat.cards[0]['source_role'],'bubble')
        self.chat.clear();self.chat.frame=self.image.copy()
        for role,box in (('store',[200,100,180,70]),('text',[450,100,180,70])):
            self.accept(self.row(role,box,speaker=''))
        self.assertEqual(len(self.chat.history),2)
        self.chat.clear();self.chat.frame=self.image.copy()
        self.accept(self.row('chat',[20,480,260,18]));self.accept(self.row('chat',[20,505,260,18]),10.1)
        self.assertEqual(len(self.chat.history),2)

    def test_verified_fragment_upgrades_atomically_and_cannot_downgrade(self):
        fragment=self.row('bubble',[230,120,100,40],speaker='plePlayer',original='같이 사냥해요!!')
        full=self.row('bubble',[200,100,180,70],speaker='ExamplePlayer',original='주말에 같이 사냥해요!!')
        self.accept(fragment);event=self.chat.cards[0]['id']
        self.accept(full,10.5)
        self.assertEqual(len(self.chat.cards),1);self.assertEqual(len(self.chat.history),1)
        self.assertEqual(self.chat.cards[0]['id'],event)
        self.assertEqual(self.chat.history[0]['speaker'],'ExamplePlayer')
        self.assertEqual(self.chat.history[0]['original'],full['original'])
        self.accept(fragment,11)
        self.assertEqual(self.chat.cards[0]['original'],full['original']);self.assertEqual(len(self.chat.history),1)

    def test_fragment_requires_pixel_continuity_and_preserves_semantic_roles(self):
        fragment=self.row('bubble',[230,120,100,40],speaker='plePlayer',original='같이 사냥해요!!')
        self.accept(fragment)
        changed=self.image.copy();p=QPainter(changed);p.fillRect(QRect(230,120,100,40),QColor('black'));p.end()
        self.chat.frame=changed
        self.accept(self.row('bubble',[200,100,180,70],original='주말에 같이 사냥해요!!'),11)
        self.assertEqual(len(self.chat.history),2)
        for first,second in (('장공250','장공250만'),('같이가요','안같이가요'),('같이가요','같이가요?')):
            self.assertFalse(self.chat.fragment_of({'speaker':'ExamplePlayer','original':first},self.row('bubble',[1,1,80,40],original=second)))

    def test_a_proven_disappearance_allows_a_legitimate_repeat(self):
        row=self.row('bubble',[200,100,180,70]);self.accept(row)
        self.chat.cards[0]['sources'][0]['gone_at']=10.2
        self.accept(row,11)
        self.assertEqual(len(self.chat.history),2);self.assertEqual(len(self.chat.cards),1)

    def test_phase_finishing_restarts_safely_without_extra_capture_or_old_errors(self):
        chat=self.chat;pipe=Pipe();chat.process=pipe;chat.ready=chat.enabled=True;requests=[];statuses=[]
        chat.status.connect(statuses.append)
        chat.frame_requested.connect(lambda:requests.append(chat.request(self.image,self.image.rect())))
        panel=TranslationPanel(enabled=True)
        try:
            chat.start_scan();old=chat.identity
            self.assertEqual(chat.phase,'scanning');self.assertNotIn('Translating',chat.phase_message())
            chat.finish_scan();self.assertEqual(chat.phase,'finishing');self.assertTrue(chat.active)
            panel.set_active(chat.active);self.assertEqual(panel.translate_button.text(),'Restart scan')
            chat.want_frame();self.assertEqual(requests,[True])
            chat.start_scan();self.assertEqual(chat.phase,'scanning')
            pipe.output=(json.dumps({'id':old,'row':self.row('bubble',[200,100,180,70])})+'\n'+
                         json.dumps({'id':old,'error':'obsolete error'})+'\n'+json.dumps({'id':old,'done':{'count':1}})+'\n').encode()
            chat.receive();QTest.qWait(20)
            self.assertEqual(chat.history,[]);self.assertEqual(requests,[True,True]);self.assertNotIn('obsolete error',statuses)
            self.assertEqual(chat.phase,'scanning')
            current=chat.identity;chat.abort_scan('Game no longer visible')
            self.assertFalse(chat.active);self.assertEqual(chat.phase,'idle')
            pipe.output=(json.dumps({'id':current,'row':self.row('bubble',[200,100,180,70])})+'\n'+
                         json.dumps({'id':current,'done':{'count':1}})+'\n').encode()
            chat.receive();self.assertEqual(chat.history,[])
        finally:panel.deleteLater()

    def test_contexts_clip_to_game_and_event_memory_is_bounded(self):
        pipe=Pipe();self.chat.process=pipe;self.chat.ready=True
        self.assertTrue(self.chat.request(self.image,QRect(100,50,500,400),contexts=[
            {'role':'store','box':[80,40,200,100],'verified':True},
            {'role':'store','box':[700,500,40,40],'verified':True},
            {'role':'store','box':[100,80,40,40],'verified':False}]))
        header=json.loads(pipe.writes[-2]);self.assertEqual(header['contexts'],[{'role':'store','box':[0,0,180,90],'verified':True}])
        self.chat.frame=self.image.copy();self.chat.region=self.image.rect()
        for n in range(70):
            self.chat.identity+=1;self.accept(self.row('store',[200,100,180,70],speaker='',original=f'새 메시지{n}'),n+20)
        self.assertLessEqual(len(self.chat.events),64);self.assertLessEqual(len(self.chat.cards),8);self.assertEqual(len(self.chat.history),30)
        active={card['id'] for card in self.chat.cards}
        self.assertTrue(all(source['pixels'] is None for event in self.chat.events if event['id'] not in active for source in event['sources']))
