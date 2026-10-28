"""Our own window/menu events only; notifications are captured, never sent by tests."""
import unittest
from unittest.mock import patch

import test_ui_context as context


class TrayTests(unittest.TestCase):
    setUpClass = classmethod(context.ContextUiTests.setUpClass.__func__)
    setUp = context.ContextUiTests.setUp
    tearDown = context.ContextUiTests.tearDown

    def test_minimize_defaults_to_tray_with_one_notification_and_restore(self):
        self.assertTrue(self.window.minimize_to_tray)
        self.window.show()
        with patch("price_lens.tray.QSystemTrayIcon.isSystemTrayAvailable", return_value=True), \
                patch.object(self.window.tray.icon, "showMessage") as notification:
            self.window.showMinimized()
            self.app.processEvents()
            self.assertTrue(self.window.isHidden())
            notification.assert_called_once()
            self.assertIn("Reading continues", notification.call_args.args[1])
            self.assertEqual(self.window.reader.pauses, [])
            self.window.tray.restore()
            self.app.processEvents()
            self.assertTrue(self.window.isVisible())
            self.assertFalse(self.window.isMinimized())

    def test_unavailable_tray_keeps_the_panel_in_the_taskbar(self):
        self.window.show()
        with patch("price_lens.tray.QSystemTrayIcon.isSystemTrayAvailable", return_value=False), \
                patch.object(self.window.tray.icon, "showMessage") as notification:
            self.window.showMinimized()
            self.app.processEvents()
            self.assertFalse(self.window.isHidden())
            notification.assert_not_called()

    def test_wayland_state_acknowledgment_does_not_lose_minimize_intent(self):
        self.window.show()
        with patch("price_lens.tray.QSystemTrayIcon.isSystemTrayAvailable", return_value=True), \
                patch.object(self.window.tray.icon, "showMessage") as notification:
            self.window.showMinimized()
            # Native Wayland may clear Qt's minimized flag before the timer.
            with patch.object(self.window, "isMinimized", return_value=False):
                self.app.processEvents()
            self.assertTrue(self.window.isHidden())
            notification.assert_called_once()

    def test_restore_cancels_a_pending_tray_minimize(self):
        self.window.show()
        with patch("price_lens.tray.QSystemTrayIcon.isSystemTrayAvailable", return_value=True), \
                patch.object(self.window.tray.icon, "showMessage") as notification:
            self.window.showMinimized()
            self.window.tray.restore()
            self.app.processEvents()
            self.assertTrue(self.window.isVisible())
            self.assertFalse(self.window.isMinimized())
            notification.assert_not_called()

    def test_tray_minimization_can_be_disabled_and_saved(self):
        self.window.tray_check.setChecked(False)
        self.assertFalse(self.window.settings.values["minimize-to-tray"])
        self.window.show()
        with patch("price_lens.tray.QSystemTrayIcon.isSystemTrayAvailable", return_value=True):
            self.window.showMinimized()
            self.app.processEvents()
            self.assertFalse(self.window.isHidden())

    def test_tray_actions_share_button_and_label_state(self):
        self.window.render()
        self.assertEqual(self.window.tray.toggle.text(), "Pause reading")
        self.window.tray.toggle.trigger()
        self.assertEqual(self.window.mode, "paused")
        self.assertEqual(self.window.reader.pauses, [True])
        self.assertEqual(self.window.tray.toggle.text(), "Resume reading")
        self.window.tray.labels.trigger()
        self.assertFalse(self.window.labels_enabled)
        self.window.tray.labels.trigger()
        self.assertTrue(self.window.labels_enabled)
        self.window.monitor.setCurrentIndex(-1)
        self.assertFalse(self.window.tray.toggle.isEnabled())

    def test_quit_closes_hidden_app_and_cancels_scheduled_minimize(self):
        self.window.show()
        closed = []
        self.window.closed.connect(lambda: closed.append(True))
        with patch("price_lens.tray.QSystemTrayIcon.isSystemTrayAvailable", return_value=True), \
                patch.object(self.window.tray.icon, "showMessage") as notification:
            self.window.showMinimized()
            next(action for action in self.window.tray.menu.actions() if action.text() == "Quit Lupin").trigger()
            self.app.processEvents()
            self.assertTrue(self.window.closing)
            self.assertEqual(closed, [True])
            notification.assert_not_called()
            self.assertFalse(self.window.tray.icon.isVisible())
