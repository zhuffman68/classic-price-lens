"""Only our own named socket is used for activation and installer shutdown."""
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent, QTimer
from PySide6.QtWidgets import QApplication

from price_lens.control import AppControl, request
from price_lens.stream import StreamClient


class ApplicationControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.folder = Path(self.directory.name)
        self.name = "ClassicPriceLens-control-test-" + uuid.uuid4().hex
        if sys.platform != "win32":
            self.name = str(self.folder / "control")
        self.lock = self.folder / "app.lock"
        self.control = AppControl(name=self.name, lock_path=self.lock)
        self.assertTrue(self.control.start())

    def tearDown(self):
        self.control.close()
        self.control.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.directory.cleanup()

    def send(self, command):
        # A real second process also covers Windows named-pipe behavior. Blocking
        # Qt socket calls in a Python worker thread can hold the GIL on some builds.
        script = ("import sys; from PySide6.QtCore import QCoreApplication; "
                  "from price_lens.control import request; app=QCoreApplication([]); "
                  "print(repr(request(sys.argv[1], sys.argv[2])), flush=True)")
        process = subprocess.Popen([sys.executable, "-B", "-c", script, command, self.name],
                                   cwd=Path(__file__).resolve().parents[1],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        deadline = time.monotonic() + 8
        while process.poll() is None and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.001)
        if process.poll() is None:
            process.kill()
        output, errors = process.communicate(timeout=2)
        self.assertEqual(process.returncode, 0, errors)
        self.assertIn(output.strip(), ("True", "False", "None"), errors)
        return {"True": True, "False": False, "None": None}[output.strip()]

    def test_second_launch_activates_only_the_existing_app(self):
        activations = []
        self.control.activate.connect(lambda: activations.append(True))
        second = AppControl(name=self.name, lock_path=self.lock)
        self.assertFalse(second.start())
        self.assertTrue(self.send("activate"))
        self.app.processEvents()
        self.assertEqual(activations, [True])

    def test_installer_quit_acknowledges_and_waits_for_shutdown(self):
        self.control.quit.connect(lambda: QTimer.singleShot(25, self.control.close))
        self.assertTrue(self.send("quit"))
        self.assertFalse(self.control.server.isListening())
        replacement = AppControl(name=self.name, lock_path=self.lock)
        self.assertTrue(replacement.start())
        replacement.close()

    def test_unknown_command_cannot_close_the_app(self):
        quits = []
        self.control.quit.connect(lambda: quits.append(True))
        self.assertFalse(self.send("other"))
        self.assertTrue(self.control.server.isListening())
        self.assertEqual(quits, [])

    def test_desktop_shortcut_toggles_only_the_running_app(self):
        toggles = []
        self.control.toggle.connect(lambda: toggles.append(True))
        self.assertTrue(self.send("toggle"))
        self.app.processEvents()
        self.assertEqual(toggles, [True])
        self.assertTrue(self.control.server.isListening())

    def test_minimize_command_controls_only_our_panel(self):
        minimized=[]
        self.control.minimize.connect(lambda:minimized.append(True))
        self.assertTrue(self.send("minimize"))
        self.app.processEvents()
        self.assertEqual(minimized,[True])
        self.assertTrue(self.control.server.isListening())

    def test_capture_diagnostics_do_not_write_to_read_only_app_folder(self):
        root = self.folder / "read-only-installation"
        root.mkdir(mode=0o555)
        cache = self.folder / "user-cache"
        cache.mkdir()
        client = StreamClient(root)
        client.active = True
        with patch("price_lens.stream.cache_directory", return_value=cache), \
                patch.object(client.launcher, "startDetached", return_value=(True, 0)) as launch:
            client.connection_error(None)
        self.assertTrue(launch.called)
        self.assertFalse((root / "evidence").exists())
        root.chmod(0o755)
