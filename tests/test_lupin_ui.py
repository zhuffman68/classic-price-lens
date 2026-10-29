"""Feature-state integration using the real UI, isolated settings and fake pixels."""
import sys,time,unittest
import test_ui_context as fixtures
from test_experience import payload
from unittest.mock import patch
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt


class LupinUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.ContextUiTests.setUpClass();cls.app=fixtures.ContextUiTests.app

    def setUp(self):
        self.fixture=fixtures.ContextUiTests();self.fixture.setUp();self.window=self.fixture.window

    def tearDown(self):
        self.fixture.tearDown();self.fixture.doCleanups()

    def test_four_shortcuts_share_cross_platform_super_defaults(self):
        self.assertEqual(self.window.hotkey_sequence,'Meta+F9')
        self.assertEqual(self.window.exp_sequence,'Meta+F10')
        self.assertEqual(self.window.chat_sequence,'Meta+F11')
        self.assertEqual(self.window.write_sequence,'Meta+F8')

    def test_all_shortcut_buttons_use_one_editor(self):
        w=self.window
        with patch('price_lens.shortcut_ui.edit_shortcuts') as editor:
            for button in (w.shortcuts_button,w.hotkey_button,w.translation_panel.writer.shortcut):button.click()
        self.assertEqual([call.args[1] for call in editor.call_args_list],['prices','prices','write'])
        self.assertFalse(hasattr(w.translation_panel,'shortcut_button'))

    def test_tab_footer_uses_current_shortcuts_in_a_fixed_position(self):
        w=self.window;w.show();self.app.processEvents();positions=[]
        for index,part in [(w.search_tab_index,'F9'),(w.exp_tab_index,'F10'),(w.translation_tab_index,'F11')]:
            w.tabs.setCurrentIndex(index);self.app.processEvents()
            self.assertIn(part,w.shortcut_footer.text())
            positions.append(w.shortcut_footer.mapTo(w,w.shortcut_footer.rect().topLeft()).y())
        w.translation_panel.modes.setCurrentIndex(1)
        self.assertIn('F8',w.shortcut_footer.text())
        self.assertEqual(len(set(positions)),1)
        w.on_write_hotkey_changed('Ctrl+Alt+J')
        self.assertIn('Ctrl+Alt+J',w.shortcut_footer.text())

    def test_translation_scan_button_requires_enabled_translation(self):
        panel=self.window.translation_panel
        self.assertFalse(panel.translate_button.isEnabled())
        panel.enabled_check.setChecked(True)
        self.assertTrue(panel.translate_button.isEnabled())
        panel.set_active(True);self.assertEqual(panel.translate_button.text(),'Restart scan')
        panel.enabled_check.setChecked(False)
        self.assertFalse(panel.translate_button.isEnabled())

    def test_composer_hotkey_needs_no_capture_and_notifies_after_explicit_copy(self):
        w=self.window;w.mode='idle';w.reader.image=w.reader.image.__class__()
        with patch('price_lens.compose.QGuiApplication.clipboard') as clip,patch.object(w.tray.icon,'showMessage') as notify:
            w.write_hotkeys.activated.emit()
            self.assertTrue(w.composer_dialog.isVisible())
            editor=w.composer_dialog.editor.input;editor.setText('ty')
            QTest.keyClick(editor,Qt.Key.Key_Return)
            clip.return_value.setText.assert_called_once_with('감사합니다.')
            self.assertEqual(notify.call_args[0][0],'Translation copied to clipboard')
            self.assertEqual(w.reader.starts,0)

    def test_exp_start_pause_resume_survives_price_toggle_and_stop_hides_overlay(self):
        w=self.window
        self.assertFalse(w.exp_enabled);self.assertEqual(w.exp_panel.overlay_rows(),[])
        w.exp_hotkeys.activated.emit();self.assertTrue(w.exp_enabled)
        w.on_experience({'atMs':int(time.monotonic()*1000),'experience':payload(2000)})
        self.assertIsNotNone(w.exp_panel.tracker.run)
        w.hotkeys.activated.emit()
        self.assertFalse(w.prices_enabled);self.assertTrue(w.exp_enabled)
        self.assertEqual(w.mode,'live')
        w.exp_hotkeys.activated.emit();self.assertTrue(w.exp_panel.user_paused)
        self.assertEqual(w.exp_panel.overlay_rows()[0]['status'],'Paused')
        w.exp_hotkeys.activated.emit();self.assertFalse(w.exp_panel.user_paused)
        w.exp_panel.stop_button.click()
        self.assertFalse(w.exp_enabled);self.assertFalse(w.reader.experience_enabled)
        self.assertEqual(w.exp_panel.overlay_rows(),[])

    def test_main_reading_pause_holds_tracking_and_dismisses_all_overlay_labels(self):
        w=self.window;w.on_exp_hotkey()
        w.on_experience({'atMs':int(time.monotonic()*1000),'experience':payload(2000)})
        before=w.exp_panel.mesos.seconds;w.pause()
        self.assertTrue(w.exp_panel.requested);self.assertFalse(w.exp_panel.connected)
        self.assertEqual(w.mode,'paused');self.assertFalse(w.overlay.rows)
        w.exp_panel.mesos.tick(time.monotonic()+30,False)
        self.assertLess(w.exp_panel.mesos.seconds-before,.1)
        self.assertIn('paused',w.exp_panel.meso_status.text())

    def test_search_uses_prices_page_and_has_space_priority_without_capture(self):
        w=self.window;w.on_reading(self.fixture.reading(True));w.mode='idle'
        w.search_panel.query.setText('Example');w.search_panel.timer.stop();w.search_panel.find_items()
        self.assertTrue(w.scroll.isHidden())
        w.search_panel.results.setCurrentRow(0)
        self.assertEqual(w.service.manual_item.game_id,1)
        w.search_panel.query.clear()
        self.assertIsNone(w.service.manual_item)
        self.assertFalse(w.scroll.isHidden())

    def test_exp_can_be_stopped_while_waiting_for_its_first_reading(self):
        w=self.window;w.on_exp_hotkey()
        self.assertTrue(w.exp_panel.requested)
        self.assertIsNone(w.exp_panel.tracker.run)
        self.assertTrue(w.exp_panel.stop_button.isEnabled())
        w.exp_panel.stop_button.click()
        self.assertFalse(w.exp_enabled);self.assertFalse(w.exp_panel.requested)

    def test_tracking_overlay_controls_are_independent_and_sync_with_settings(self):
        w=self.window;w.on_exp_hotkey()
        w.on_experience({'atMs':int(time.monotonic()*1000),'experience':payload(2000)})
        w.exp_panel.overlay_check.setChecked(False)
        self.assertFalse(w.exp_overlay);self.assertFalse(w.exp_overlay_check.isChecked())
        self.assertTrue(w.meso_overlay);self.assertTrue(w.meso_overlay_check.isChecked())
        self.assertTrue(w.settings.values['meso-overlay'],'The inherited preference must survive an EXP-only change and restart')
        self.assertEqual([r['key'] for r in w.overlay.rows],['meso-gain'])
        w.meso_overlay_check.setChecked(False)
        self.assertFalse(w.exp_panel.meso_overlay_check.isChecked());self.assertEqual(w.overlay.rows,[])
        w.exp_overlay_check.setChecked(True)
        self.assertTrue(w.exp_panel.overlay_check.isChecked());self.assertFalse(w.meso_overlay)
        self.assertEqual([r['key'] for r in w.overlay.rows],['experience'])
        self.assertTrue(w.settings.values['exp-overlay']);self.assertFalse(w.settings.values['meso-overlay'])

    def test_brief_detection_uncertainty_keeps_status_but_hides_game_labels(self):
        w=self.window;w.on_reading(self.fixture.reading(True))
        w.last_identified_at=time.monotonic();w.reader.game_area=None
        self.assertEqual(w.connection_state()[0],'Classic World identified')
        w.draw_labels(time.time(),False)
        self.assertEqual(w.overlay.rows,[])
