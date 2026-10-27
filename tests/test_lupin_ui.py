"""Feature-state integration using the real UI, isolated settings and fake pixels."""
import sys,time,unittest
import test_ui_context as fixtures
from test_experience import payload


class LupinUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.ContextUiTests.setUpClass();cls.app=fixtures.ContextUiTests.app

    def setUp(self):
        self.fixture=fixtures.ContextUiTests();self.fixture.setUp();self.window=self.fixture.window

    def tearDown(self):
        self.fixture.tearDown();self.fixture.doCleanups()

    def test_three_shortcuts_have_independent_defaults(self):
        self.assertEqual(self.window.hotkey_sequence,'F10')
        self.assertEqual(self.window.exp_sequence,'F11')
        self.assertEqual(self.window.chat_sequence,'F9' if sys.platform=='win32' else 'F12')

    def test_exp_start_pause_resume_survives_price_toggle_and_stop_hides_overlay(self):
        w=self.window
        self.assertFalse(w.exp_enabled);self.assertIsNone(w.exp_panel.overlay_row())
        w.exp_hotkeys.activated.emit();self.assertTrue(w.exp_enabled)
        w.on_experience({'atMs':int(time.monotonic()*1000),'experience':payload(2000)})
        self.assertIsNotNone(w.exp_panel.tracker.run)
        w.hotkeys.activated.emit()
        self.assertFalse(w.prices_enabled);self.assertTrue(w.exp_enabled)
        self.assertEqual(w.mode,'live')
        w.exp_hotkeys.activated.emit();self.assertTrue(w.exp_panel.user_paused)
        self.assertIn('paused',w.exp_panel.overlay_row()['name'])
        w.exp_hotkeys.activated.emit();self.assertFalse(w.exp_panel.user_paused)
        w.exp_panel.stop_button.click()
        self.assertFalse(w.exp_enabled);self.assertFalse(w.reader.experience_enabled)
        self.assertIsNone(w.exp_panel.overlay_row())

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

    def test_exp_overlay_toggle_is_one_setting_in_both_places(self):
        w=self.window;w.exp_panel.overlay_check.setChecked(False)
        self.assertFalse(w.exp_overlay);self.assertFalse(w.exp_overlay_check.isChecked())
        w.exp_overlay_check.setChecked(True)
        self.assertTrue(w.exp_overlay);self.assertTrue(w.exp_panel.overlay_check.isChecked())

    def test_brief_detection_uncertainty_keeps_status_but_hides_game_labels(self):
        w=self.window;w.on_reading(self.fixture.reading(True))
        w.last_identified_at=time.monotonic();w.reader.game_area=None
        self.assertEqual(w.connection_state()[0],'Classic World identified')
        w.draw_labels(time.time(),False)
        self.assertEqual(w.overlay.rows,[])
