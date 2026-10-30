"""Only our own writer, draft pipes and synthetic screen bounds are exercised."""
import os
import unittest
from pathlib import Path
from unittest.mock import Mock,patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QObject,Signal,QRect,QCoreApplication,QEvent,Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from price_lens.compose import KoreanComposer
from price_lens.composer_overlay import ComposerOverlayController,RemoteComposer,WriterHost,composer_state
from price_lens.overlay_layout import writer_placement,corner_offset
from price_lens.overlay import Overlay

ROOT=Path(__file__).resolve().parents[1]


class FakeOverlay(QObject):
    writer_event=Signal(dict)
    writer_lost=Signal()
    writer_available=True
    def __init__(self):
        super().__init__();self.commands=[];self.host=None
    def update_writer(self,state):
        self.commands.append(state)
        if self.host:self.host.apply(state)


class WriterLayoutTests(unittest.TestCase):
    def test_measured_hud_and_legacy_anchor_choose_same_safe_corner_at_multiple_dpi(self):
        for scale in (1,1.5,2):
            bounds=[100,70,1366,768]
            footer=QRect(round(384*scale),round(794*scale),round(798*scale),round(44*scale))
            guard=QRect(round(385*scale),round(800*scale),round(36*scale),round(37*scale))
            measured=writer_placement(bounds,footer,[guard],scale_x=1/scale,scale_y=1/scale)
            legacy=writer_placement(bounds,None,[guard],scale_x=1/scale,scale_y=1/scale)
            for placed in (measured,legacy):
                rect=QRect(*placed['box'])
                self.assertGreaterEqual(rect.width(),240)
                self.assertLessEqual(rect.width(),280)
                self.assertTrue(QRect(*bounds).contains(rect))
                self.assertFalse(rect.intersects(QRect(384,794,798,44)))
                self.assertGreater(rect.left(),1182)

    def test_smaller_game_and_larger_hud_move_above_status_bar(self):
        for width in (800,960,1024,1280):
            bounds=[30,40,width,600]
            footer=QRect(30+(width-798)//2,596,798,44)
            placed=writer_placement(bounds,footer)
            box=QRect(*placed['box'])
            self.assertLess(box.bottom(),footer.top()-10)
            self.assertTrue(QRect(*bounds).contains(box))
        self.assertIsNone(writer_placement([0,0,180,200]))
        self.assertIsNone(writer_placement([0,0,800,260],QRect(0,216,798,44)))

    def test_notices_reserve_writer_and_previous_notices(self):
        bounds=[100,70,1366,768];writer=QRect(1180,600,280,232)
        offset=corner_offset(bounds,[],[writer])
        self.assertGreaterEqual(838-offset,writer.top()-6)
        self.assertGreater(offset,230)
        notice=dict(bounds=bounds,anchor='bottom_right',bottom_offset=offset)
        self.assertGreater(corner_offset(bounds,[notice],[writer]),offset)


class WriterBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.c=KoreanComposer(ROOT);self.overlay=FakeOverlay();self.control=ComposerOverlayController(self.c,self.overlay)
        self.placement=dict(box=[100,100,280,240],bounds=[0,0,800,600])
        self.clipboard=Mock();self.patch=patch('price_lens.compose.QGuiApplication.clipboard',return_value=self.clipboard);self.patch.start()
    def tearDown(self):
        if self.overlay.host and self.overlay.host.window:
            w=self.overlay.host.window;w.motion.stop();w.size_motion.stop();w.hide();w.deleteLater()
        self.c.close();self.c.deleteLater();self.control.deleteLater();self.overlay.deleteLater();self.patch.stop()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.app.processEvents()
    def event(self,action,sequence,text='',session=None):
        self.control.receive(dict(event=action,sequence=sequence,text=text,session=self.control.session if session is None else session))
    def connect_host(self):
        self.overlay.host=WriterHost(self.overlay.writer_event.emit)
        return self.overlay.host
    def test_reordered_and_old_session_messages_cannot_copy(self):
        self.control.open(self.placement,'Super+F8',True)
        self.event('edit',1,'ty');self.c.timer.stop();self.c.preview()
        self.clipboard.setText.assert_not_called()
        self.event('submit',1,'ty');self.event('submit',2,'ty',session=0)
        self.clipboard.setText.assert_not_called()
        self.event('submit',2,'ty')
        self.clipboard.setText.assert_called_once_with('감사합니다.')
        self.event('submit',3,'ty');self.clipboard.setText.assert_called_once()
    def test_unacknowledged_helper_edit_is_never_overwritten_by_old_state(self):
        events=[];remote=RemoteComposer(events.append)
        self.control.open(self.placement,'Super+F8',True)
        remote.apply(self.overlay.commands[-1]);remote.set_text('WTS Work Gloves 250k')
        self.assertFalse(remote.apply(self.overlay.commands[-1]))
        self.assertEqual(remote.text,'WTS Work Gloves 250k')
        self.event('edit',1,remote.text)
        self.assertTrue(remote.apply(self.overlay.commands[-1]))
        self.assertEqual(remote.text,self.c.text)
    def test_context_loss_revokes_pending_copy_and_retires_surface(self):
        host=self.connect_host();self.control.open(self.placement,'Super+F8',True)
        self.assertTrue(self.control.presented);self.assertTrue(host.window.isVisible())
        host.window.input.setText('Please wait here');self.c.timer.stop()
        self.c.copy_pending=self.c.identity
        self.control.context(None)
        QTest.qWait(150)
        self.assertIsNone(self.c.copy_pending);self.assertFalse(host.window.isVisible())
        self.assertFalse(self.control.presented);self.assertIsNone(self.control.rectangle())
    def test_enter_copies_and_hides_writer_without_changing_annotation_flags(self):
        host=self.connect_host();self.control.open(self.placement,'Super+F8',True)
        w=host.window;self.app.processEvents()
        w.input.setText('ty');self.c.timer.stop()
        QTest.keyClick(w.input,Qt.Key.Key_Return)
        self.assertFalse(w.isVisible());self.assertFalse(self.control.presented)
        self.clipboard.setText.assert_called_once_with('감사합니다.')
        self.assertFalse(w.windowFlags() & Qt.WindowType.WindowTransparentForInput)
        self.assertFalse(w.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus)
        self.assertFalse(w.windowFlags() & Qt.WindowType.X11BypassWindowManagerHint)

    def test_enter_freezes_the_editor_before_a_fast_result_then_fades_without_reflow(self):
        host=self.connect_host();self.control.open(self.placement,'Super+F8',False)
        w=host.window;self.app.processEvents();w.motion.setCurrentTime(w.motion.duration())
        w.input.setText('ty');self.c.timer.stop();w.size_motion.setCurrentTime(w.size_motion.duration())
        height=w.height();target=w.geometry();preview=w.preview.text();button=w.copy.text()
        w.input.returnPressed.emit()
        self.assertTrue(w.closing);self.assertTrue(w.isVisible());self.assertTrue(w.input.isReadOnly())
        self.assertTrue(w.panel.isEnabled());self.assertEqual(w.motion.duration(),180)
        self.assertEqual(w.height(),height);self.assertEqual(w.preview.text(),preview);self.assertEqual(w.copy.text(),button)
        self.clipboard.setText.assert_called_once_with('감사합니다.')
        w.motion.setCurrentTime(90)
        self.assertAlmostEqual(w.level,.5,places=2);self.assertEqual(w.height(),height)
        self.assertLessEqual(abs(w.y()-target.y()),6)
        w.motion.setCurrentTime(180)
        self.assertFalse(w.isVisible());self.assertFalse(self.control.presented)

    def test_late_state_does_not_resize_exit_and_escape_does_not_restart_the_fade(self):
        host=self.connect_host();self.control.open(self.placement,'Super+F8',False)
        w=host.window;self.app.processEvents();w.motion.setCurrentTime(140)
        w.input.setText('Please wait here');self.c.timer.stop()
        with patch.object(self.c,'preview'):w.input.returnPressed.emit()
        w.motion.setCurrentTime(80);geometry=w.geometry();target=QRect(w.target);button=w.copy.text()
        self.c.result='긴 문장입니다. '*100;self.c.note='Long model warning. '*50;self.c.changed.emit()
        self.assertEqual(w.geometry(),geometry);self.assertEqual(w.target,target);self.assertEqual(w.copy.text(),button)
        w.reject();self.assertIsNone(self.c.copy_pending)
        self.assertEqual(w.motion.currentTime(),80);self.assertEqual(w.motion.duration(),180)
        self.clipboard.setText.assert_not_called()

    def test_repeated_enter_during_fast_copy_exit_does_not_submit_again(self):
        host=self.connect_host();self.control.open(self.placement,'Super+F8',False)
        w=host.window;w.motion.setCurrentTime(140);w.input.setText('ty');self.c.timer.stop()
        w.input.returnPressed.emit();sequence=host.composer.sequence
        w.input.returnPressed.emit();w.copy.click()
        self.assertEqual(host.composer.sequence,sequence);self.clipboard.setText.assert_called_once()

    def test_reduce_motion_during_submit_exit_hides_without_cancelling_copy(self):
        host=self.connect_host();self.control.open(self.placement,'Super+F8',False)
        w=host.window;w.motion.setCurrentTime(140);w.input.setText('Please wait here');self.c.timer.stop()
        with patch.object(self.c,'preview'):w.input.returnPressed.emit()
        authorized=self.c.copy_pending;self.assertIsNotNone(authorized)
        self.control.context(self.placement,reduced=True)
        self.assertFalse(w.isVisible());self.assertFalse(self.control.presented)
        self.assertEqual(self.c.copy_pending,authorized);self.clipboard.setText.assert_not_called()

    def test_editing_the_main_draft_during_exit_revokes_the_old_copy(self):
        host=self.connect_host();self.control.open(self.placement,'Super+F8',False)
        w=host.window;w.motion.setCurrentTime(140);w.input.setText('Please wait here');self.c.timer.stop()
        with patch.object(self.c,'preview'):w.input.returnPressed.emit()
        submitted=self.c.identity;self.assertEqual(self.c.copy_pending,submitted)
        self.c.set_text('Please come here');self.c.timer.stop();self.assertIsNone(self.c.copy_pending)
        self.c.accept(submitted,'여기에서 기다려 주세요.','Old response')
        self.clipboard.setText.assert_not_called();self.assertTrue(w.closing)

    def test_new_opening_interrupts_exit_and_restores_editing(self):
        host=self.connect_host();self.control.open(self.placement,'Super+F8',False)
        w=host.window;w.motion.setCurrentTime(140);w.input.setText('ty');self.c.timer.stop();w.input.returnPressed.emit()
        w.motion.setCurrentTime(80);self.control.open(self.placement,'Super+F8',True)
        self.assertTrue(w.isVisible());self.assertFalse(w.closing);self.assertFalse(w.input.isReadOnly())
        self.assertFalse(w.panel.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))
        self.assertFalse(host.composer.submitted);self.assertTrue(self.control.active)
    def test_escape_during_exit_still_cancels_authorized_late_copy(self):
        host=self.connect_host();self.control.open(self.placement,'Super+F8',False)
        w=host.window;self.app.processEvents()
        with patch.object(self.c,'preview'):
            w.input.setText('Please wait here');self.c.timer.stop();w.input.returnPressed.emit()
        self.assertIsNotNone(self.c.copy_pending)
        w.reject();QTest.qWait(140)
        self.assertIsNone(self.c.copy_pending);self.clipboard.setText.assert_not_called()
    def test_full_preview_and_warnings_stay_accessible_inside_maximum_height(self):
        host=self.connect_host();self.control.open(self.placement,'Super+F8',True)
        self.c.text='WTS Work Gloves 250k ea';self.c.result='장갑을 판매합니다. '*40
        self.c.expanded='Selling Work Gloves for 250k each';self.c.note='Review before pasting. '*20
        self.c.changed.emit();self.app.processEvents()
        w=host.window
        self.assertEqual(w.preview.text(),self.c.result)
        self.assertLessEqual(w.height(),240)
        self.assertTrue(w.rect().contains(w.copy.mapTo(w,w.copy.rect().center())))
        self.assertGreater(w.body_scroll.verticalScrollBar().maximum(),0)
        self.assertTrue(QRect(*self.placement['box']).contains(w.geometry()))
    def test_close_during_unacknowledged_typing_still_hides(self):
        host=self.connect_host();self.control.open(self.placement,'Super+F8',True)
        host.composer.sequence+=1
        host.apply(dict(operation='close',session=self.control.session,ack=0,state=composer_state(self.c)))
        self.assertFalse(host.window.isVisible())

    def test_moving_while_edit_is_in_flight_cannot_leave_old_placement(self):
        host=self.connect_host();self.control.open(self.placement,'Super+F8',True)
        pending=[];host.composer.send=pending.append
        host.composer.set_text('ty')
        moved=dict(box=[420,180,272,240],bounds=[320,80,800,600])
        self.control.context(moved,reduced=True)
        self.assertEqual(host.window.placement,moved)
        self.control.receive(pending.pop())
        self.assertEqual(host.window.placement,self.control.placement)
        self.assertEqual(host.composer.text,'ty')

    def test_old_surface_cancel_cannot_revoke_native_fallback_submission(self):
        self.control.open(self.placement,'Super+F8',True)
        self.event('edit',1,'Please wait here');self.c.timer.stop()
        self.event('fallback',2,'Please wait here')
        self.c.copy_pending=self.c.identity
        self.event('cancel',3,'Please wait here')
        self.assertEqual(self.c.copy_pending,self.c.identity)

    def test_old_submitted_surface_cannot_cancel_a_newly_edited_draft(self):
        self.control.open(self.placement,'Super+F8',False)
        with patch.object(self.c,'preview'):
            self.event('submit',1,'Please wait here')
        self.c.set_text('Please come here');self.c.timer.stop();self.c.copy_pending=self.c.identity
        self.event('cancel',2,'Please wait here')
        self.assertEqual(self.c.copy_pending,self.c.identity)

    def test_helper_loss_releases_exclusions_and_unsubmitted_authorization(self):
        self.control.open(self.placement,'Super+F8',True)
        self.c.copy_pending=self.c.identity
        self.overlay.writer_lost.emit()
        self.assertIsNone(self.control.rectangle());self.assertFalse(self.control.active)
        self.assertIsNone(self.c.copy_pending)

    def test_focus_denial_offers_click_to_type_and_native_fallback(self):
        host=self.connect_host();self.control.open(self.placement,'Super+F8',True,'fixture-token')
        w=host.window
        with patch.object(w,'isActiveWindow',return_value=False):w.check_activation()
        self.assertFalse(w.focus_help.isHidden())
        with patch.object(w,'isActiveWindow',return_value=True):w.check_activation()
        self.assertTrue(w.focus_help.isHidden())
        chosen=[];self.control.fallback_requested.connect(chosen.append)
        host.composer.event('fallback')
        self.assertEqual(chosen,['fixture-token'])

    def test_too_short_corner_uses_native_fallback_before_creating_a_surface(self):
        host=self.connect_host()
        for maximum in (120,160,199):
            self.assertFalse(self.control.open(dict(box=[100,100,280,maximum]),'Super+F8',True))
            self.assertIsNone(host.window)
            self.assertIsNone(self.control.rectangle())

    def test_reduce_motion_set_while_open_stops_current_entrance(self):
        host=self.connect_host();self.control.open(self.placement,'Super+F8',False)
        w=host.window
        self.control.context(self.placement,reduced=True)
        self.assertEqual(w.motion.state(),w.motion.State.Stopped)
        self.assertEqual(w.size_motion.state(),w.size_motion.State.Stopped)
        self.assertEqual(w.level,1.0)

    def test_real_helper_pipe_opens_writer_without_replaying_or_clearing_canvas(self):
        overlay=Overlay(ROOT)
        control=ComposerOverlayController(self.c,overlay)
        try:
            self.assertTrue(overlay.process.waitForStarted(3000))
            from PySide6.QtCore import QProcess
            opened=dict(operation='open',session=1,ack=0,state=composer_state(self.c),placement=self.placement)
            with patch.object(overlay.process,'state',return_value=QProcess.ProcessState.Starting):
                self.assertFalse(overlay.writer_available)
                self.assertFalse(control.open(self.placement,'Super+F8',True))
                control.close()
                self.assertIsNone(control.rectangle())
            overlay.update([0,0,800,600],[dict(x=25,y=25,name='Example Hat',text='FM 1,000',key=100)])
            for _ in range(100):
                if overlay.layout_boxes:break
                QTest.qWait(20)
            self.assertTrue(overlay.layout_boxes)
            before=overlay.layout_boxes
            control.open(self.placement,'Super+F8',True)
            for _ in range(100):
                if control.actual_box:break
                QTest.qWait(20)
            self.assertIsNotNone(control.actual_box,overlay.last_error)
            self.assertEqual(overlay.layout_boxes,before)
            with patch.object(overlay.process,'write') as write:
                overlay.update([0,0,800,600],[])
                self.assertNotIn(b'"writer"',bytes(write.call_args[0][0]))
        finally:
            overlay.close();control.deleteLater();overlay.deleteLater()

