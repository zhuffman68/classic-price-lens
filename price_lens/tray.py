"""Controls for our own panel and OS notification area; no game access."""
from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .icons import app_icon


class TrayController(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.minimize_pending = False
        self.icon = QSystemTrayIcon(app_icon(window.root), window)
        self.icon.setToolTip("Lupin")
        self.menu = QMenu(window)
        self.status = self.menu.addAction("Lupin")
        self.status.setEnabled(False)
        self.menu.addSeparator()
        self.show = self.menu.addAction("Show panel", self.restore)
        self.toggle = self.menu.addAction("Start reading", window.toggle_capture)
        self.labels = self.menu.addAction("Show price labels")
        self.labels.setCheckable(True)
        self.labels.toggled.connect(window.labels_check.setChecked)
        self.menu.addAction("Settings…", self.settings)
        self.menu.addSeparator()
        self.menu.addAction("Quit Lupin", window.close)
        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self.activated)
        self.icon.messageClicked.connect(self.restore)
        self.icon.show()

    def available(self):
        return QSystemTrayIcon.isSystemTrayAvailable()

    def update(self):
        title = self.window.connection_state()[0]
        self.status.setText(title)
        self.icon.setToolTip("Lupin · " + title)
        self.toggle.setText(self.window.share.text())
        self.toggle.setEnabled(self.window.share.isEnabled())
        self.labels.blockSignals(True)
        self.labels.setChecked(self.window.labels_enabled)
        self.labels.blockSignals(False)

    def minimize(self):
        # Wayland can acknowledge a minimize request with a normal-state
        # configure before this deferred callback. Keep the original intent.
        requested = self.minimize_pending
        self.minimize_pending = False
        if (self.window.closing or self.window.isHidden() or not self.window.minimize_to_tray
                or not (requested or self.window.isMinimized()) or not self.available()):
            return False
        self.window.hide()
        state = "Waiting for screen sharing." if self.window.capture_starting else "Reading continues." if self.window.mode == "live" else "Reading is paused." if self.window.mode == "paused" else "Reading has not started."
        self.icon.showMessage("Lupin is in the tray",
                              state + " Right-click the tray icon for controls, or click it to show the panel.",
                              QSystemTrayIcon.MessageIcon.Information, 6000)
        return True

    def schedule_minimize(self):
        self.minimize_pending = True
        QTimer.singleShot(0, self.minimize)

    def restore(self):
        self.minimize_pending = False
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    def settings(self):
        self.restore()
        self.window.open_settings()

    def activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.restore()

    def close(self):
        self.minimize_pending = False
        self.icon.hide()
