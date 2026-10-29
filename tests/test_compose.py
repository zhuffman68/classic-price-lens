"""Outgoing chat semantics, stale-result protection, UTF-8 inference and explicit copy."""
import json,os,time,unittest
from pathlib import Path
from unittest.mock import patch,Mock
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import QCoreApplication,QEvent
from price_lens.outgoing_text import expand,template,protect,validate
from price_lens.compose import KoreanComposer

ROOT=Path(__file__).resolve().parents[1]


class OutgoingTextTests(unittest.TestCase):
    def test_trade_shorthand_preserves_item_price_and_offer_roles(self):
        source=expand('S> 8att WG 2.5m ea c/o 2m a/w 3m firm, pmo')
        output=validate(source,template(source))
        for value in ('8 att Work Gloves','2.5m','2m','3m','개당','현재 제시가','즉구가','흥정 불가','가격 제안은 귓말 주세요'):self.assertIn(value,output)
        self.assertTrue(output.startswith('판매:'))
        self.assertTrue(validate(expand('WTB White Jeans 250k'),template(expand('WTB White Jeans 250k'))).startswith('구매:'))

    def test_party_and_social_slang_are_contextual_and_do_not_guess_numbers(self):
        for message,expected in [('ty4pt','파티 감사해요.'),('brb','잠시 후에 돌아올게요.'),('cc 3','3채널로 이동해 주세요.')]:
            source=expand(message);self.assertEqual(validate(source,template(source)),expected)
        for message in ('LF1M KPQ bonus','LFM 1 KPQ bonus'):
            source=expand(message);result=validate(source,template(source));self.assertIn('1명',result);self.assertIn('커닝 파퀘 보너스',result)

    def test_bare_numbers_never_acquire_a_scale_currency_or_percent(self):
        for message in ('S> WG 250','S> WG 250k','S> 10% GFA 2.5m'):
            source=expand(message);validate(source,template(source))
        for before,after in [('250','250k'),('250','250 메소'),('10%','10'),('2.5m','250k')]:
            with self.assertRaises(ValueError):validate(before,'판매: '+after)

    def test_protected_names_and_numbers_fail_closed_if_dropped_or_repeated(self):
        protected=protect('Can I buy Work Gloves for 250k?',['Work Gloves'])
        tokens=list(protected.replacements)
        good=' '.join(tokens)+' 250k에 구매할 수 있나요?'
        result=validate(protected.source,protected.restore(good))
        self.assertIn('Work Gloves',result);self.assertIn('250k',result)
        for broken in (good.replace(tokens[0],''),good+' '+tokens[0]):
            with self.assertRaises(ValueError):protected.restore(broken)

    def test_equivalent_korean_amounts_restore_the_users_format_but_keep_percent_roles(self):
        self.assertEqual(validate('2.5m','250만에 팝니다.'),'2.5m에 팝니다.')
        self.assertEqual(validate('10% scroll','10 퍼센트 스크롤'),'10% 스크롤')
        with self.assertRaises(ValueError):validate('10% scroll','10개 스크롤')

    def test_item_names_are_protected_inside_trade_templates_too(self):
        source=expand('WTS Meso Ranger Helmet 250k mesos')
        output=validate(source,template(source,['Meso Ranger Helmet']))
        self.assertIn('Meso Ranger Helmet',output);self.assertIn('250k 메소',output)


class FakePipe:
    def __init__(self):self.output=b'';self.requests=[]
    def write(self,value):self.requests.append(json.loads(bytes(value)));return len(value)
    def readAllStandardOutput(self):data=self.output;self.output=b'';return data


class ComposerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen');cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.c=KoreanComposer(ROOT);self.clipboard=Mock();self.patch=patch('price_lens.compose.QGuiApplication.clipboard',return_value=self.clipboard);self.patch.start()

    def tearDown(self):
        if isinstance(self.c.process,FakePipe):self.c.process=None
        self.c.close();self.c.deleteLater();self.patch.stop()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.app.processEvents()

    def pipe(self):
        p=FakePipe();self.c.process=p;self.c.ready=True;return p

    def reply(self,pipe,identity,text):
        pipe.output=(json.dumps({'id':identity,'text':text})+'\n').encode();self.c.receive()

    def test_preview_never_copies_and_explicit_copy_emits_confirmation(self):
        copies=[];self.c.copied.connect(copies.append)
        self.c.set_text('ty');self.c.timer.stop();self.c.preview()
        self.clipboard.setText.assert_not_called();self.assertIsNone(self.c.process)
        self.c.request_copy();self.clipboard.setText.assert_called_once_with('감사합니다.')
        self.assertEqual(copies,['감사합니다.'])

    def test_edited_draft_cannot_copy_an_old_inflight_result(self):
        p=self.pipe();self.c.set_text('Please come here');self.c.request_copy();old=p.requests[-1]['id']
        self.c.set_text('Please wait here');self.c.timer.stop();self.c.preview()
        self.reply(p,old,'여기로 와 주세요.')
        self.clipboard.setText.assert_not_called();self.assertFalse(self.c.result)
        self.reply(p,p.requests[-1]['id'],'여기서 기다려 주세요.')
        self.assertEqual(self.c.result,'여기서 기다려 주세요.');self.clipboard.setText.assert_not_called()

    def test_cancelled_popup_cannot_copy_a_late_result(self):
        p=self.pipe();self.c.set_text('Please come here');self.c.request_copy();identity=p.requests[-1]['id'];self.c.cancel_copy()
        self.reply(p,identity,'여기로 와 주세요.');self.assertTrue(self.c.result);self.clipboard.setText.assert_not_called()

    def test_enter_animates_popup_closed_and_copies_later_without_a_second_action(self):
        from price_lens.composer_ui import ComposerDialog
        from PySide6.QtCore import Qt
        pipe=self.pipe();dialog=ComposerDialog(self.c,'Super+F8');dialog.show();self.app.processEvents()
        dialog.editor.input.setText('Please come here');self.c.timer.stop()
        QTest.keyClick(dialog.editor.input,Qt.Key.Key_Return)
        identity=pipe.requests[-1]['id'];self.assertEqual(self.c.copy_pending,identity)
        QTest.qWait(160);self.assertFalse(dialog.isVisible());self.assertEqual(self.c.copy_pending,identity)
        self.reply(pipe,identity,'여기로 와 주세요.');self.clipboard.setText.assert_called_once_with('여기로 와 주세요.')
        dialog.deleteLater()

    def test_escape_during_submission_animation_revokes_pending_copy(self):
        from price_lens.composer_ui import ComposerDialog
        from PySide6.QtCore import Qt
        pipe=self.pipe();dialog=ComposerDialog(self.c,'Super+F8');dialog.show();self.app.processEvents()
        dialog.editor.input.setText('Please come here');self.c.timer.stop()
        QTest.keyClick(dialog.editor.input,Qt.Key.Key_Return);identity=pipe.requests[-1]['id']
        dialog.reject();QTest.qWait(160);self.reply(pipe,identity,'여기로 와 주세요.')
        self.clipboard.setText.assert_not_called();dialog.deleteLater()

    def test_catalog_arrival_invalidates_a_pending_unprotected_draft(self):
        p=self.pipe();self.c.set_text('Please bring Blue Hawkeye');self.c.request_copy();old=p.requests[-1]['id']
        self.c.set_names([type('Item',(),{'name':'Blue Hawkeye'})()]);self.c.timer.stop();self.c.preview()
        self.reply(p,old,'파란 모자를 가져와 주세요.')
        self.clipboard.setText.assert_not_called();self.assertFalse(self.c.result)
        current=p.requests[-1];self.assertNotIn('Blue Hawkeye',current['text'])
        marker=next(iter(self.c.inflight[1].replacements))
        self.reply(p,current['id'],marker+' 가져와 주세요.')
        self.assertIn('Blue Hawkeye',self.c.result);self.clipboard.setText.assert_not_called()

    def test_model_still_unloads_if_the_draft_changes_during_startup(self):
        p=self.pipe();self.c.ready=False
        self.c.set_text('Please come here');self.c.timer.stop();self.c.preview()
        self.c.set_text('ty');self.c.timer.stop();self.c.preview()
        p.output=b'{"ready":true}\n';self.c.receive()
        self.assertTrue(self.c.idle.isActive());self.assertEqual(self.c.result,'감사합니다.')
        self.assertEqual(p.requests,[]);self.clipboard.setText.assert_not_called()

    def test_cold_model_loading_has_a_separate_deadline_from_translation(self):
        with patch('price_lens.compose.QProcess.start'):
            self.c.start_worker()
        self.assertEqual(self.c.deadline.interval(),60000)
        self.c.unload()
        p=self.pipe();self.c.ready=False
        self.c.set_text('Please come here');self.c.timer.stop();self.c.preview()
        self.assertFalse(p.requests)
        p.output=b'{"ready":true}\n';self.c.receive()
        self.assertEqual(len(p.requests),1)
        self.assertEqual(self.c.deadline.interval(),12000)
        self.assertFalse(self.c.error)
        self.clipboard.setText.assert_not_called()

    def test_model_cannot_invent_an_unstated_currency(self):
        p=self.pipe();self.c.set_text('Can you accept 250');self.c.request_copy()
        # Keep all protected values but introduce an unstated currency.
        marker=p.requests[-1]['text'].split()[-1]
        self.reply(p,p.requests[-1]['id'],marker+' 메소 괜찮나요?')
        self.assertTrue(self.c.error);self.clipboard.setText.assert_not_called()

    @unittest.skipUnless((ROOT/'models/english-korean/translation/model.bin').exists(),'Prepared writer model is optional in a source checkout')
    def test_real_worker_preserves_unicode_names_numbers_and_unloads(self):
        self.c.set_names([type('Item',(),{'name':'Kerning City'})()])
        self.c.set_text('Please meet me in Kerning City on channel 3.');self.c.request_copy()
        limit=time.monotonic()+15
        while not self.c.result and not self.c.error and time.monotonic()<limit:QTest.qWait(10)
        self.assertFalse(self.c.error,self.c.error);self.assertIn('Kerning City',self.c.result);self.assertIn('3',self.c.result)
        self.clipboard.setText.assert_called_once_with(self.c.result)
        self.c.unload();self.assertIsNone(self.c.process)
