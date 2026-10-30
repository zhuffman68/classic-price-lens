"""Pixel continuity, OCR alternatives and full-window fairness under rescans."""
from collections import OrderedDict
from pathlib import Path
from types import SimpleNamespace
import os
import unittest
from unittest.mock import patch

import numpy as np
from PySide6.QtCore import QCoreApplication, QEvent, QRect
from PySide6.QtGui import QImage, QPainter, QColor
from PySide6.QtWidgets import QApplication

from price_lens.chat import ChatTranslation
from price_lens.chat_ocr import Recognizer
from price_lens.chat_scan import ScanMemory
from price_lens.chat_text import recruiting_phrase, supported_ocr_alternative
from price_lens.chat_tracking import stamp, locate_offset
from price_lens.chat_worker import scan
from price_lens.translation_ui import TranslationPanel, grouped_history

ROOT=Path(__file__).resolve().parents[1]


def scene(dx=0,dy=0,extra=False,other_header=False):
    image=QImage(600,420,QImage.Format.Format_RGB888);image.fill(QColor('#26394d'))
    painter=QPainter(image);painter.translate(dx,dy)
    painter.fillRect(100,100,160,130 if extra else 90,QColor('#eeeeee'))
    for x,h in ((111,7),(117,10),(128,8),(140,5),(155,9)):
        painter.fillRect(x,106,3,h,QColor('#111111'))
    if other_header:painter.fillRect(111,106,48,10,QColor('#111111'))
    for x,y,w,h in ((112,128,7,4),(119,132,3,14),(130,127,8,3),(136,130,3,16),
                     (146,139,12,4),(164,130,3,15),(170,126,9,4),(179,139,5,7)):
        painter.fillRect(x,y,w,h,QColor('#111111'))
    if extra:
        for y in (166,180,194,208):
            for x in range(109,250,13):painter.fillRect(x,y,7,8,QColor('#111111'))
    painter.end();return image


def tracked(image):
    return dict(box=[100,100,160,90],track_box=[110,125,78,23],speaker_box=[108,104,54,14],
                stamp=stamp(image,[100,100,160,90]),track_stamp=stamp(image,[110,125,78,23]),
                speaker_stamp=stamp(image,[108,104,54,14]),track_pixels=image.copy(110,125,78,23),source_role='bubble')


def row():
    return dict(box=[100,100,160,90],track_box=[110,125,78,23],speaker_box=[108,104,54,14],
                speaker='ExamplePlayer',original='보너스팟 팟점여',text='Please invite me to the bonus party',
                note='Game-chat phrase',source_role='bubble',role_verified=True)


class TranslationScanTests(unittest.TestCase):
    def test_vectorized_run_edges_preserve_connected_component_geometry(self):
        from price_lens.chat_ocr import components
        rng=np.random.default_rng(17)
        for _ in range(12):
            mask=rng.random((15,21))>.48;filtered=mask.copy()
            for y,line in enumerate(mask):
                for x,on in enumerate(line):
                    if on and not (x and line[x-1]) and not (x+1<len(line) and line[x+1]):filtered[y,x]=False
            expected=[];seen=set()
            for y,x in zip(*np.nonzero(filtered)):
                if (y,x) in seen:continue
                stack=[(int(y),int(x))];points=[];seen.add((y,x))
                while stack:
                    cy,cx=stack.pop();points.append((cy,cx))
                    for ny,nx in ((cy-1,cx),(cy+1,cx),(cy,cx-1),(cy,cx+1)):
                        if 0<=ny<15 and 0<=nx<21 and filtered[ny,nx] and (ny,nx) not in seen:
                            seen.add((ny,nx));stack.append((ny,nx))
                ys,xs=zip(*points);expected.append(([min(xs),min(ys),max(xs)+1,max(ys)+1],len(points)))
            self.assertEqual(sorted(components(mask)),sorted(expected))

    def test_complete_invitation_slang_and_explicit_context(self):
        for phrase in ('보너스팟 팟점여','보너스 파티좀요','보너스팟 초대좀요','러쉬팟 팟점요'):
            with self.subTest(phrase=phrase):self.assertIn('Please invite me',recruiting_phrase(phrase))
        self.assertEqual(recruiting_phrase('팟점여'),'Please invite me to a party')
        self.assertEqual(recruiting_phrase('초대점여'),'Please invite me')
        self.assertIn('bonus party',recruiting_phrase('보너스 팟좀요'))
        for phrase in ('보너스팟 팟점여 안돼요','보너스팟 팟점여250','안 보너스팟 팟점여'):
            self.assertIsNone(recruiting_phrase(phrase))

    def test_ocr_alternatives_require_model_support_and_one_complete_phrase(self):
        source='보너스팟 땃점여'
        self.assertEqual(supported_ocr_alternative(source,[('보너스팟 팟점여',.59)]),'보너스팟 팟점여')
        for alternatives in ([('보너스팟 팟점여',.1)],[('보너스팟 팟점여250',.8)],
                             [('러쉬팟 팟점여',.8)]):
            self.assertIsNone(supported_ocr_alternative(source,alternatives))
        self.assertIsNone(supported_ocr_alternative('보너스팟 팟점아',[('보너스팟 팟점여',.7),('보너스팟 팟점요',.6)]))
        self.assertIsNone(supported_ocr_alternative('보너스팟 팟점여',[('러쉬팟 팟점여',.8)]))

    def test_ctc_exposes_only_uncertain_syllables_and_trims_decoration(self):
        reader=Recognizer.__new__(Recognizer);reader.height=48;reader.cache=OrderedDict();reader.details={}
        reader.chars=['','땃','팟','점','여','@'];prob=np.zeros((12,6),dtype='float32');prob[:,0]=.99
        for t,c in ((1,1),(3,3),(5,4),(7,5),(9,5)):prob[t,0]=.01;prob[t,c]=.99
        prob[1]=[.23,.48,.29,0,0,0]
        reader.session=SimpleNamespace(get_inputs=lambda:[SimpleNamespace(name='image')],run=lambda *_:[prob[None]])
        image=QImage(100,14,QImage.Format.Format_RGB888);image.fill(QColor('#eeeeee'))
        self.assertEqual(reader.read(image)[0],'땃점여@@')
        info=reader.detail(image)
        self.assertEqual(info['alternatives'][0][0],'팟점여@@');self.assertLess(info['content_right'],100)
        prob[1]=[.005,.99,.005,0,0,0];reader.cache.clear();reader.details.clear()
        self.assertFalse(reader.detail(image)['alternatives'])

    def test_negative_pixel_cache_invalidates_on_change_and_is_bounded(self):
        memory=ScanMemory();calls=[]
        reader=SimpleNamespace(read=lambda line:(calls.append(line.width()) or ('English shop',.99)))
        image=scene()
        for _ in range(2):memory.read(image,False,reader,lambda:False,0)
        self.assertEqual(len(calls),1)
        for i in range(140):
            changed=image.copy();changed.setPixelColor(i,0,QColor('#eeeeee'))
            memory.read(changed,False,reader,lambda:False,0)
        self.assertEqual(len(calls),141);self.assertLessEqual(len(memory.reads),128)

    def test_rescan_emits_confirmed_body_before_any_full_frame_detection(self):
        memory=ScanMemory();image=scene();memory.prepare(image);memory.remember(row(),image);outputs=[];order=[]
        def detector(_):order.append('detect');return []
        with patch('price_lens.chat_ocr.bubbles',side_effect=detector),patch('price_lens.chat_ocr.text_regions',return_value=[]):
            result=scan(image,SimpleNamespace(read=lambda _:self.fail('Cached pixels need no OCR')),
                        SimpleNamespace(),lambda r:(order.append('emit'),outputs.append(r)),memory=memory)
        self.assertEqual(order[0],'emit');self.assertEqual(result['count'],1)
        self.assertEqual(outputs[0]['original'],row()['original'])
        with patch('price_lens.chat_ocr.bubbles',return_value=[]),patch('price_lens.chat_ocr.text_regions',return_value=[]):
            outputs=[];scan(scene(other_header=True),SimpleNamespace(),SimpleNamespace(),outputs.append,memory=memory)
        self.assertEqual(outputs,[])

    def test_priority_does_not_starve_new_text_and_excludes_covered_sources(self):
        memory=ScanMemory();image=scene();memory.prepare(image)
        memory.remember(row(),image)
        recognizer=SimpleNamespace(read=lambda _:('안녕하세요',.99));translator=SimpleNamespace(translate=lambda _:('hello','Local'))
        outputs=[]
        with patch('price_lens.chat_ocr.bubbles',return_value=[[360,200,100,45]]),\
             patch('price_lens.chat_ocr.text_regions',return_value=[]),\
             patch('price_lens.chat_ocr.lines',side_effect=lambda crop:[(crop,14)]):
            scan(image,recognizer,translator,outputs.append,memory=memory)
        self.assertTrue(any(value['box']==[360,200,100,45] for value in outputs))
        remaining=memory.priority(image,[[100,100,160,90]],(),lambda *a:('bubble',True))
        self.assertFalse(any(value['box']==row()['box'] for value in remaining))

    def test_text_tracking_moves_farther_without_matching_other_speakers(self):
        before=scene();source=tracked(before)
        self.assertEqual(locate_offset(scene(61,-37,extra=True),source),(61,-37))
        self.assertIsNone(locate_offset(scene(61,-37,other_header=True),source))
        self.assertIsNone(locate_offset(scene(150,0),source))
        duplicate=QImage(600,420,QImage.Format.Format_RGB888);duplicate.fill(QColor('#26394d'))
        painter=QPainter(duplicate);part=before.copy(100,100,160,90)
        painter.drawImage(40,60,part);painter.drawImage(180,180,part);painter.end()
        self.assertIsNone(locate_offset(duplicate,source))
        blank=QImage(600,420,QImage.Format.Format_RGB888);blank.fill(QColor('#eeeeee'))
        white=tracked(blank)
        self.assertIsNone(locate_offset(scene(),white))


class TranslationRescanUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen');cls.app=QApplication.instance() or QApplication([])

    def test_padding_changes_keep_one_arrival_but_absence_allows_a_new_one(self):
        chat=ChatTranslation(ROOT)
        try:
            chat.region=QRect(0,0,600,420);chat.frame=scene();chat.identity=1
            with patch('price_lens.chat.time.monotonic',return_value=10):chat.accept_row(row())
            first=chat.history[0]['id'];chat.frame=scene(0,-20,extra=True);chat.identity=2
            second=row();second.update(box=[100,80,160,130],track_box=[110,105,78,23],speaker_box=[108,84,54,14])
            with patch('price_lens.chat.time.monotonic',return_value=10.5):chat.accept_row(second)
            self.assertEqual(len(chat.history),1);self.assertEqual(chat.history[0]['id'],first)
            chat.cards[0]['sources'][0]['gone_at']=10.6
            with patch('price_lens.chat.time.monotonic',return_value=11.2):chat.accept_row(second)
            self.assertEqual(len(chat.history),2)
        finally:chat.close();chat.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)

    def test_recent_repeat_groups_preserve_speakers_numbers_and_card_widgets(self):
        first={**row(),'id':1};second={**row(),'id':2};third={**row(),'id':3,'speaker':'AnotherPlayer'}
        grouped=grouped_history([first,second,third])
        self.assertEqual(len(grouped),2);self.assertEqual(grouped[0]['repeat_count'],2)
        self.assertEqual(len(grouped_history([{**first,'speaker':''},{**second,'speaker':''}])),2)
        self.assertEqual(len(grouped_history([first,{**second,'original':'250k'}])),2)
        panel=TranslationPanel()
        try:
            panel.set_cards([first]);widget=panel.result_cards[1]
            panel.set_cards([first,second]);self.assertIs(panel.result_cards[1],widget)
            self.assertIn('×2',widget.labels[0].text())
            panel.set_cards([first,second,third]);self.assertIs(panel.result_cards[1],widget)
        finally:panel.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
