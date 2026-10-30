"""Synthetic chat only: game nouns, exact identities and semantic fail-closed checks."""
import os
from pathlib import Path
import time
import unittest
from unittest.mock import Mock,patch

from price_lens.outgoing_text import expand,protect,template,validate

ROOT=Path(__file__).resolve().parents[1]


class OutgoingTermsTests(unittest.TestCase):
    def render(self,message,names=()):
        source=expand(message,names);output=template(source,names)
        self.assertIsNotNone(output,message)
        return validate(source,output,names)

    def test_game_activity_questions_and_negation_have_complete_meaning(self):
        cases=[('Do you play MapleStory?','메이플스토리','하시나요?'),
               ('I play MapleStory.','메이플스토리','해요.'),
               ('I am playing MapleStory.','메이플스토리','하고 있어요.'),
               ('I do not play MapleStory.','메이플스토리','하지 않아요.'),
               ('I want to do a PQ.','파티퀘스트','하고 싶어요.'),
               ('I do not want to do a PQ.','파티퀘스트','하고 싶지 않아요.'),
               ('Are you doing KPQ?','커닝시티 파티퀘스트','계신가요?'),
               ('Can I join your party quest?','파티퀘스트','참여해도 될까요?'),
               ('I cannot join your party quest.','파티퀘스트','참여할 수 없어요.'),
               ('Are you not playing MapleStory?','메이플스토리','안 하고 계신가요?'),
               ('Could you explain this party quest?','파티퀘스트','설명해 주실 수 있나요?')]
        for source,term,meaning in cases:
            with self.subTest(source=source):
                output=self.render(source);self.assertIn(term,output);self.assertIn(meaning,output)
                self.assertNotIn('MapleStory',output);self.assertNotIn('party quest',output);self.assertNotIn('Kerning',output)

    def test_party_recruitment_keeps_exact_member_count_and_bonus_type(self):
        for source in ('LF2M KPQ bonus','LFM 2 KPQ bonus'):
            output=self.render(source);self.assertIn('2명',output);self.assertIn('커닝 파퀘 보너스',output)
            self.assertIn('파티원',output);self.assertIn('구합니다',output)

    def test_prose_or_questions_never_take_the_fragment_trade_shortcut(self):
        for source in ('selling a cheap scroll for anyone who wants it',
                       'selling Work Gloves because I do not play anymore',
                       'buying a scroll that is useful for my warrior',
                       'selling Free Market 250k','selling Work Gloves for 250k?',
                       'thank you?','I play MapleStory?'):
            self.assertIsNone(template(expand(source),('Work Gloves',)),source)

    def test_ordinary_trade_fragments_still_keep_item_stat_price_and_offer_roles(self):
        output=self.render('S> 8att WG 2.5m ea c/o 2m a/w 3m firm pmo')
        for token in ('8 att','Work Gloves','2.5m','2m','3m','개당','현재 제시가','즉구가','흥정 불가','귓말'):self.assertIn(token,output)

    def test_gfa_gma_do_not_expand_scroll_twice_or_drop_the_attack_type(self):
        for shorthand,english,korean in (('GFA','Glove ATT scroll','장갑 공격력 주문서'),
                                        ('GMA','Glove Magic ATT scroll','장갑 마력 주문서')):
            source=expand('Do you have a '+shorthand+' scroll?');self.assertIn(english,source);self.assertNotIn('scroll scroll',source)
            protected=protect(source);marker=next(iter(protected.replacements))
            output=validate(source,protected.restore(marker+'이 있나요?'))
            self.assertIn(korean+'가 있나요?',output)

    def test_item_names_with_game_terms_and_chat_aliases_stay_exact(self):
        for name in ('Free Market Chair','MapleStory Shield','Party Quest Chair','PartyQuest Chair','MapleStory','FM Radio Chair',"TY's Hat"):
            source=expand('WTS '+name+' 250k',[name])
            self.assertEqual(source,'selling '+name+' 250k')
            output=validate(source,template(source,[name]),[name]);self.assertIn(name,output)
        source=expand('Please bring Free Market Chair to the FM.',['Free Market Chair'])
        protected=protect(source,['Free Market Chair'])
        reverse={value:token for token,value in protected.replacements.items()}
        output=validate(source,protected.restore(reverse['Free Market Chair']+'를 '+reverse['자유시장']+'에 가져와 주세요.'),['Free Market Chair'])
        self.assertIn('Free Market Chair',output);self.assertIn('자유시장에',output)

    def test_handles_are_not_expanded_as_slang_or_mistaken_for_game_terms(self):
        source=expand('Please invite @ty and @fm.');self.assertIn('@ty',source);self.assertIn('@fm',source)
        protected=protect(source);tokens={value:token for token,value in protected.replacements.items()}
        output=validate(source,protected.restore(tokens['@ty']+'와 '+tokens['@fm']+'을 초대해 주세요.'))
        self.assertIn('@ty',output);self.assertIn('@fm',output)

    def test_general_game_nouns_are_korean_but_remain_contextual_in_model_input(self):
        source=expand('Please explain the party quest in MapleStory.');protected=protect(source)
        self.assertIn('party quest',protected.masked);self.assertIn('MapleStory',protected.masked)
        output=validate(source,protected.restore('MapleStory의 파티 퀘스트를 설명해 주세요.'))
        self.assertIn('메이플스토리',output);self.assertIn('파티퀘스트',output)
        with self.assertRaises(ValueError):protected.restore('그 게임의 임무를 설명해 주세요.')

    def test_all_previously_frozen_towns_and_market_terms_restore_korean(self):
        for english,korean in [('Free Market','자유시장'),('Kerning City','커닝시티'),('Henesys','헤네시스'),('Ellinia','엘리니아'),('Perion','페리온')]:
            source='Please meet me in '+english+'.';protected=protect(source)
            output=validate(source,protected.restore(next(iter(protected.replacements))+'에서 만나 주세요.'))
            self.assertIn(korean+'에서',output);self.assertNotIn(english,output)

    def test_classic_tier_percent_and_stat_are_not_reinterpreted_as_modern_scrolls(self):
        name='Glove Attack Scroll: Chaos';source=expand('WTS 10% '+name+' 2.5m',[name])
        output=validate(source,template(source,[name]),[name])
        for value in ('10%',name,'2.5m'):self.assertIn(value,output)
        self.assertNotIn('혼돈',output)
        protected=protect('Please bring 8 ATT Work Gloves for 250k.')
        self.assertIn('8 ATT',protected.replacements.values())
        self.assertTrue(validate('Lesser scroll','Lesser 주문서입니다.'))
        with self.assertRaises(ValueError):validate('Beginner scroll','Beginner 주문서입니다.')

    def test_lost_question_negation_or_untranslated_prose_is_rejected(self):
        for source,output in [('Do you play MapleStory?','메이플스토리를 하고 있습니다.'),
                              ('I do not want to join.','참여하고 싶어요.'),
                              ('selling a cheap scroll','판매: a cheap scroll'),
                              ('Please wait here.','Please 여기서 기다려 주세요.')]:
            with self.subTest(source=source),self.assertRaises(ValueError):validate(expand(source),output)

    def test_negation_and_question_words_inside_exact_item_names_are_literal(self):
        for name in ('Never Ending Hat','No Problem Chair','Why? Hat'):
            self.assertIn(name,self.render('WTS '+name+' 250k',[name]))
        source=expand('Please invite @not.');protected=protect(source)
        self.assertIn('@not',validate(source,protected.restore(next(iter(protected.replacements))+'을 초대해 주세요.')))

    def test_quantity_and_per_item_price_have_distinct_roles_in_known_item_sentences(self):
        for message in ('I want to buy 2 Work Gloves for 250k each.',
                        'I have 2 Work Gloves for 2.5m each.',
                        'I am selling 2 Work Gloves for 250k per item.'):
            output=self.render(message);self.assertIn('Work Gloves 2개',output);self.assertIn('개당',output)
            self.assertIn('2.5m' if '2.5m' in message else '250k',output)
        with self.assertRaises(ValueError):validate('I want to buy 2 Work Gloves for 250k each.','Work Gloves 2개를 250k에 사고 싶어요.')

    def test_negative_korean_inflections_and_smart_apostrophe_remain_negative(self):
        self.assertIn('판매하지 않아요',self.render('I am not selling Work Gloves for 250.'))
        self.assertTrue(validate('Do not sell Work Gloves for 250k.','Work Gloves를 250k에 판매하지 마십시오.'))
        self.assertTrue(validate('I am selling Work Gloves for 2.5m, not 250k.','Work Gloves를 2.5m에 판매합니다. 250k가 아닙니다.'))
        with self.assertRaises(ValueError):validate('I can’t join your party quest.','파티퀘스트에 참여합니다.')

    def test_250_250k_and_2_5m_are_distinct_and_currency_is_never_inferred(self):
        for amount in ('250','250k','2.5m'):
            output=self.render('S> WG '+amount);self.assertIn(amount,output)
        for source,output in [('250','250k에 판매합니다.'),('250k','2.5m에 판매합니다.'),('250','250 메소에 판매합니다.'),('10%','10개 주문서입니다.')]:
            with self.assertRaises(ValueError):validate(source,output)


@unittest.skipUnless((ROOT/'models/english-korean/translation/model.bin').is_file(),'Bundled local writer model is optional in source checkouts')
class OutgoingModelTermsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_bundled_model_uses_verified_terms_without_changing_exact_item_names_or_numbers(self):
        from price_lens.compose import KoreanComposer
        composer=KoreanComposer(ROOT);names=('Work Gloves','MapleStory Shield')
        composer.set_names([type('Item',(),{'name':name})() for name in names])
        clipboard=Mock()
        try:
            with patch('price_lens.compose.QGuiApplication.clipboard',return_value=clipboard):
                for message,expected in [
                    ('Please meet me in the FM on channel 3.',('자유시장','3')),
                    ('Please bring MapleStory Shield to the Free Market.',('MapleStory Shield','자유시장')),
                    ('I am not in Henesys.',('헤네시스','않')),
                    ('Why is this party quest so difficult?',('파티퀘스트','?')),
                ]:
                    with self.subTest(message=message):
                        composer.set_text(message);composer.timer.stop();composer.preview();deadline=time.monotonic()+25
                        while not composer.result and not composer.error and time.monotonic()<deadline:
                            from PySide6.QtTest import QTest
                            QTest.qWait(10)
                        self.assertFalse(composer.error,composer.error);self.assertTrue(composer.result)
                        for word in expected:self.assertIn(word,composer.result)
                        clipboard.setText.assert_not_called()
        finally:composer.close();composer.deleteLater();self.app.processEvents()


if __name__=='__main__':unittest.main()
