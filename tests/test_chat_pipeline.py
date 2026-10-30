"""Bounded whole-game text coverage and conservative local translation routing."""
from collections import OrderedDict
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from PySide6.QtGui import QImage,QColor,QPainter
from price_lens.chat_text import recruiting_phrase,numbers_preserved,model_source,message_key
from price_lens.chat_worker import Translator,scan,source_role


def fake_translator(output):
    translator=Translator.__new__(Translator);translator.cache=OrderedDict();calls=[]
    translator.source=SimpleNamespace(encode=lambda text,**_: [text])
    translator.target=SimpleNamespace(decode=lambda values:values[0])
    def batch(tokens,**kwargs):calls.append((tokens,kwargs));return [SimpleNamespace(hypotheses=[[output]])]
    translator.model=SimpleNamespace(translate_batch=batch)
    return translator,calls


class ChatPipelineTests(unittest.TestCase):
    def test_partial_glossary_ordinary_grammar_reaches_the_local_model(self):
        translator,calls=fake_translator('Can the Warrior train again today?')
        output,note=translator.translate('전사 오늘도 사냥할 수 있나요?')
        self.assertEqual(output,'Can the Warrior train again today?');self.assertIn('Approximate',note)
        self.assertEqual(len(calls),1);self.assertIn('Warrior',calls[0][0][0][0])
        translator.translate('전사 오늘도 사냥할 수 있나요?');self.assertEqual(len(calls),1)

    def test_known_complete_phrases_stay_fast_and_counts_are_people(self):
        translator,calls=fake_translator('bad')
        self.assertEqual(translator.translate('안녕하세요')[0],'hello')
        self.assertEqual(translator.translate('러쉬팟 궁수껴주시나요?')[0],'Are you taking an Archer for the rush party?')
        self.assertEqual(translator.translate('보너스 세분구함!')[0],'Looking for three people for bonus!')
        self.assertIn('one person',translator.translate('러시팟 한명 모집합니다')[0]);self.assertEqual(calls,[])
        self.assertIsNone(recruiting_phrase('보너스 세분구함 모르겠어요'))
        self.assertNotIn('one person',model_source('열한명 구함 내일 같이 해요')[0])

    def test_lost_terms_ambiguous_shorthand_and_numeric_units_are_not_fluent_guesses(self):
        translator,calls=fake_translator('I am ready.')
        output,note=translator.translate('전사 오늘도 사냥할 수 있나요?')
        self.assertIn('Warrior',output);self.assertIn('Partial',note);self.assertEqual(len(calls),1)
        translator,_=fake_translator('Warrior for sale')
        output,note=translator.translate('전사 ㅍㅍ?');self.assertIn('ㅍㅍ',output);self.assertIn('Partial',note)
        translator,_=fake_translator('Warrior costs250k mesos.')
        output,note=translator.translate('전사 장비는250 메소인가요?')
        self.assertIn('Numbers uncertain',note)
        translator,_=fake_translator('Two bonuses tomorrow.')
        output,note=translator.translate('보너스 두분 구함 내일 같이 해요')
        self.assertIn('Partial',note);self.assertIn('두분',output)
        self.assertFalse(numbers_preserved('250','250k'));self.assertFalse(numbers_preserved('10%','10'))
        self.assertTrue(numbers_preserved('250만 메소 10%','2.5m mesos 10%'))
        for equivalent in ('10 퍼센트','10프로','10 percent'):
            self.assertTrue(numbers_preserved('10%',equivalent))
            self.assertTrue(numbers_preserved(equivalent,'10%'))
            self.assertFalse(numbers_preserved('10',equivalent))
            self.assertFalse(numbers_preserved(equivalent,'10'))

    def test_role_requires_context_or_a_header_in_chat_geometry(self):
        self.assertEqual(source_role([50,40,200,15],'가격: 물약 팝니다',False,(),(800,600)),('text',False))
        self.assertEqual(source_role([50,500,200,15],'Player: 안녕하세요',False,(),(800,600)),('chat',True))
        self.assertEqual(source_role([50,500,200,15],'판매: 물약 팝니다',False,(),(800,600)),('text',False))
        context=[{'role':'store','box':[20,20,300,200],'verified':True}]
        self.assertEqual(source_role([50,40,200,15],'안녕하세요',False,context,(800,600)),('store',True))
        self.assertEqual(source_role([50,40,200,15],'가격: 물약',True,context,(800,600)),('store',True))
        self.assertEqual(source_role([50,40,200,15],'SamplePlayer님의 꽃바람 메시지:',False),('banner',True))

    def test_alternating_budget_reaches_generic_text_before_other_bubbles(self):
        image=QImage(500,300,QImage.Format.Format_RGB888);image.fill(QColor('#222222'))
        recognizer=SimpleNamespace(read=lambda _:('안녕하세요',.99));translator=SimpleNamespace(translate=lambda _:('hello','Local'))
        outputs=[]
        with patch('price_lens.chat_ocr.bubbles',return_value=[[10,10,90,40],[120,10,90,40]]), \
             patch('price_lens.chat_ocr.text_regions',return_value=[[20,200,200,14]]), \
             patch('price_lens.chat_ocr.lines',side_effect=lambda crop:[(crop,14)]):
            first=scan(image,recognizer,translator,outputs.append,budget=0)
            second=scan(image,recognizer,translator,outputs.append,budget=0,offset=first['next_offset'])
        self.assertEqual(outputs[0]['source_role'],'bubble');self.assertEqual(outputs[1]['source_role'],'text')
        self.assertEqual(first['next_offset'],1);self.assertEqual(second['next_offset'],2)
        with patch('price_lens.chat_ocr.bubbles') as detector:
            result=scan(image,recognizer,translator,outputs.append,cancelled=lambda:True)
        detector.assert_not_called();self.assertEqual(result['count'],0)

    def test_colored_generic_ink_yields_bounded_candidates_and_high_contrast(self):
        from price_lens.chat_ocr import text_regions,contrast_line,pixels
        image=QImage(400,120,QImage.Format.Format_RGB888);image.fill(QColor('#171c25'))
        painter=QPainter(image)
        for x in range(25,225,10):
            painter.fillRect(x,45,5,12,QColor('#f778d0'));painter.fillRect(x,49,8,3,QColor('#f778d0'))
        painter.end();regions=text_regions(image)
        self.assertTrue(regions);self.assertLessEqual(len(regions),96)
        crop=contrast_line(image.copy(*regions[0]));values=pixels(crop)
        self.assertLess(values.min(),30);self.assertGreater(values.max(),240)
        self.assertNotEqual(message_key('250'),message_key('250k'))
        self.assertNotEqual(message_key('가요'),message_key('안가요'))
        self.assertEqual(message_key('두 분 구함!!'),message_key('두분구함!'))

    def test_confident_colored_raw_text_is_not_destroyed_by_contrast_retry(self):
        image=QImage(400,200,QImage.Format.Format_RGB888);image.fill(QColor('white'))
        class Reader:
            def __init__(self):self.calls=0
            def read(self,line):self.calls+=1;return ('감사합니다',.94)
        reader=Reader();rows=[]
        with patch('price_lens.chat_ocr.bubbles',return_value=[]),patch('price_lens.chat_ocr.text_regions',return_value=[[20,30,120,20]]):
            scan(image,reader,SimpleNamespace(translate=lambda _:('thanks','Local')),rows.append)
        self.assertEqual(reader.calls,1);self.assertEqual(len(rows),1)
