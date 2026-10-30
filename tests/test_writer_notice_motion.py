"""Writer-to-notice handoff and status morphs use our own isolated Qt canvas."""
import json
from types import SimpleNamespace
import time
import unittest
from unittest.mock import Mock,patch

from PySide6.QtCore import QPoint,QCoreApplication,QEvent,QRect
from PySide6.QtWidgets import QApplication
from price_lens.annotations import AnnotationWindow
from price_lens.overlay_notice import OverlayNotice
from price_lens.overlay_layout import writer_placement
from price_lens.ui import LensWindow


class NoticeStateTests(unittest.TestCase):
    def test_notice_waits_for_writer_then_keeps_the_full_short_lifetime(self):
        notice=OverlayNotice();bounds=[0,0,800,600]
        with patch('price_lens.overlay_notice.time.monotonic',return_value=100):
            notice.show('Copied to clipboard','Ctrl+V to paste the Korean text',identity=7)
        self.assertIsNone(notice.row(bounds,blocked=True,now=100.18))
        row=notice.row(bounds,now=100.2);self.assertEqual(row['notice_until'],102.7)
        self.assertEqual(notice.row(bounds,now=101)['notice_until'],102.7)
        self.assertIsNone(notice.row(bounds,now=102.71))
        notice.clear();self.assertIsNone(notice.row(bounds,now=100.3));self.assertIsNone(notice.identity)

    def test_notice_uses_the_writers_safe_corner_and_monitor_origin_at_multiple_scales(self):
        for scale in (1,1.5,2):
            bounds=[30,40,800,600];footer=QRect(round(31*scale),round(596*scale),round(798*scale),round(44*scale))
            place=writer_placement(bounds,footer,scale_x=1/scale,scale_y=1/scale);self.assertIsNotNone(place)
            origin=[1920,-1080];global_place={**place,'box':[place['box'][0]+origin[0],place['box'][1]+origin[1],*place['box'][2:]]}
            notice=OverlayNotice();notice.show('Copied to clipboard','Ctrl+V to paste')
            row=notice.row(bounds,placement=global_place,origin=origin)
            box=QRect(*row['notification_box']);editor=QRect(*place['box'])
            self.assertEqual(box.bottom(),editor.bottom());self.assertEqual(box.width(),editor.width())
            self.assertTrue(QRect(*bounds).contains(box));self.assertLess(box.bottom(),596)

    def test_user_screenshot_layout_keeps_feedback_beside_the_hud_at_the_editor_bottom(self):
        # Geometry measured by the installed reader from the user-provided
        # screen.png; no private screenshot or character text enters fixtures.
        bounds=[0,0,1364,801];footer=QRect(283,756,798,45)
        placement=writer_placement(bounds,footer)
        self.assertEqual(placement['box'],[1087,554,271,240])
        notice=OverlayNotice();notice.show('Copied to clipboard','Ctrl+V to paste the Korean text')
        box=QRect(*notice.row(bounds,placement=placement)['notification_box'])
        self.assertEqual(box,QRect(1087,746,271,48));self.assertFalse(box.intersects(footer))

    def test_actual_second_monitor_placement_subtracts_origin_once(self):
        bounds=[150,112,1364,801]
        placement=dict(box=[3157,666,271,240],bounds=bounds)
        notice=OverlayNotice();notice.show('Copied to clipboard','Ctrl+V to paste the Korean text')
        row=notice.row(bounds,placement=placement,origin=[1920,0])
        self.assertEqual(row['notification_box'],[1237,858,271,48])

    def test_edit_cancel_and_failure_replace_only_the_current_notice_identity(self):
        window=SimpleNamespace(closing=False,write_pending_identity=None,write_notice=OverlayNotice(),
            composer=SimpleNamespace(identity=7,copy_pending=7,error=''),last_screen=time.time(),draw_labels=Mock())
        LensWindow.on_translation_submitted(window,7)
        self.assertEqual(window.write_notice.message['notice_icon'],'progress')
        window.composer.copy_pending=None;LensWindow.on_writer_changed(window)
        self.assertIsNone(window.write_notice.message)
        window.composer.copy_pending=7;LensWindow.on_translation_submitted(window,7)
        window.composer.error='Uncertain result';LensWindow.on_writer_changed(window)
        self.assertEqual(window.write_notice.message['notice_icon'],'warning');self.assertEqual(window.write_notice.seconds,3)
        window.composer.error='';LensWindow.on_translation_copied(window)
        self.assertEqual(window.write_notice.message['notice_icon'],'copied');self.assertEqual(window.write_notice.seconds,2.5)
        window.composer.identity=8;LensWindow.on_writer_changed(window);self.assertIsNone(window.write_notice.message)


class NoticeCanvasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.window=AnnotationWindow(start_listener=False);self.notice=OverlayNotice()
        self.bounds=[0,0,800,600];self.placement=dict(box=[514,340,280,240],bounds=self.bounds)
        self.command=dict(geometry=[0,0,800,600],hover_enabled=False,rows=[])

    def tearDown(self):
        self.window.pointer_timer.stop();self.window.watchdog.stop()
        for row in self.window.rows+self.window.retiring:self.window.dispose_row(row)
        self.window.close();self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.app.processEvents()

    def send(self,*,reduced=False,empty=False):
        rows=[] if empty else [self.notice.row(self.bounds,placement=self.placement)]
        self.window.read_command(json.dumps({**self.command,'rows':rows,'reduce_motion':reduced}))

    def progress(self):
        self.notice.show('Translating to Korean…','Preparing text for your clipboard',seconds=65,pending=True)
        self.send();row=self.window.rows[0];row['_fade'].setCurrentTime(160);return row

    def test_translating_to_copied_crossfades_both_lines_without_blank_or_reflow(self):
        row=self.progress();before=self.window.label_rect(row,QPoint())
        self.notice.show('Copied to clipboard','Ctrl+V to paste the Korean text');self.send()
        self.assertIs(self.window.rows[0],row);self.assertEqual(self.window.label_rect(row,QPoint()),before)
        self.assertEqual(row['_alpha'],1);self.assertIsNone(row.get('_text_fade'));self.assertFalse(row.get('_rolls'))
        animation=row['_notice_transition'];animation.setCurrentTime(100)
        layers=self.window.notice_layers(row);self.assertEqual(len(layers),2)
        self.assertAlmostEqual(sum(weight for _,weight in layers),1);self.assertTrue(all(.4<weight<.6 for _,weight in layers))
        self.assertEqual(self.window.label_rect(row,QPoint()),before);self.window.grab()
        animation.setCurrentTime(200);self.assertEqual(self.window.notice_layers(row)[0][0]['name'],'Copied to clipboard')
        self.assertEqual(row['_notice_from'],[])

    def test_interrupted_notice_transition_preserves_its_current_visual_mix(self):
        row=self.progress();self.notice.show('Copied to clipboard','Ctrl+V to paste');self.send()
        row['_notice_transition'].setCurrentTime(100);before=self.window.notice_layers(row)
        self.notice.show('Translation could not be copied','Open the writer to review',warning=True,seconds=3);self.send()
        self.assertEqual(self.window.notice_layers(row),before)
        row['_notice_transition'].setCurrentTime(200)
        self.assertEqual(self.window.notice_layers(row)[0][0]['notice_icon'],'warning')

    def test_regular_updates_do_not_restart_content_or_expiry_animations(self):
        row=self.progress();self.notice.show('Copied to clipboard','Ctrl+V to paste');self.send()
        transition=row['_notice_transition'];expiry=row['_notice_expiry'];transition.setCurrentTime(70)
        self.send();self.assertIs(row['_notice_transition'],transition);self.assertEqual(transition.currentTime(),70)
        self.assertIs(row['_notice_expiry'],expiry)

    def test_notice_expires_smoothly_without_a_new_frame_or_enabled_price_reading(self):
        self.notice.show('Copied to clipboard','Ctrl+V to paste');self.send();row=self.window.rows[0]
        row['_fade'].setCurrentTime(160);row['_notice_expiry'].timeout.emit()
        self.assertEqual(self.window.rows,[]);self.assertIn(row,self.window.retiring)
        row['_fade'].setCurrentTime(90);self.assertAlmostEqual(row['_alpha'],.5,places=2)
        row['_fade'].setCurrentTime(180);self.assertEqual(self.window.retiring,[]);self.assertFalse(self.window.isVisible())

    def test_clearing_notice_still_fades_when_price_reading_is_paused(self):
        row=self.progress();self.send(empty=True)
        self.assertIn(row,self.window.retiring);self.assertEqual(row['_fade'].duration(),180)
        row['_fade'].setCurrentTime(180);self.assertFalse(self.window.isVisible())

    def test_old_expiry_callback_cannot_hide_a_new_copied_result(self):
        row=self.progress();old=row['_notice_expiry']
        self.notice.show('Copied to clipboard','Ctrl+V to paste');self.send();new=row['_notice_expiry']
        old.timeout.emit();self.assertIn(row,self.window.rows);self.assertIs(row['_notice_expiry'],new)
        self.assertLessEqual(new.interval(),2500)

    def test_reduce_motion_set_mid_transition_stops_motion_but_keeps_precise_expiry(self):
        row=self.progress();self.notice.show('Copied to clipboard','Ctrl+V to paste');self.send()
        row['_notice_transition'].setCurrentTime(70);self.send(reduced=True)
        self.assertIsNone(row['_notice_transition']);self.assertEqual(row['_notice_level'],1)
        row['_notice_expiry'].timeout.emit();self.assertEqual(self.window.rows,[]);self.assertEqual(self.window.retiring,[])

    def test_status_text_length_does_not_change_geometry_and_large_font_stays_bounded(self):
        row=self.progress();before=self.window.label_rect(row,QPoint())
        self.notice.show('Copied to clipboard','A very long instruction '*20);self.send()
        self.assertEqual(self.window.label_rect(row,QPoint()),before)
        self.window.notice_title_font.setPixelSize(24);self.window.notice_body_font.setPixelSize(20);self.send()
        box=self.window.label_rect(row,QPoint());self.assertTrue(QRect(*self.bounds).contains(box));self.assertGreaterEqual(box.height(),60)
        self.window.grab()

    def test_notice_canvas_uses_display_local_box_on_the_actual_second_monitor(self):
        bounds=[150,112,1364,801];self.notice.show('Copied to clipboard','Ctrl+V to paste the Korean text')
        row=self.notice.row(bounds,placement=dict(box=[3157,666,271,240],bounds=bounds),origin=[1920,0])
        self.window.read_command(json.dumps(dict(geometry=[1920,0,1920,1080],hover_enabled=False,reduce_motion=True,rows=[row])))
        box=self.window.label_rect(self.window.rows[0],QPoint())
        self.assertEqual(box,QRect(1237,858,271,48))
        self.assertEqual(box.translated(self.window.pos()),QRect(3157,858,271,48))
