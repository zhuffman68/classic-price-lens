"""Exercise helper pipes, cancellation and bounds without requesting any screen."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent, QProcess
from PySide6.QtWidgets import QApplication

from price_lens.platform_paths import market_binary
from price_lens.snapshot_fetcher import SnapshotFetcher


class SnapshotFetcherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.fetcher = SnapshotFetcher(Path(self.directory.name) / "profile")
        self.ready, self.errors = [], []
        self.fetcher.ready.connect(self.ready.append)
        self.fetcher.failed.connect(self.errors.append)

    def tearDown(self):
        self.fetcher.close()
        self.fetcher.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.directory.cleanup()

    def command(self, script):
        self.fetcher.command = lambda: [sys.executable, "-B", "-u", "-c", script]

    def until(self, predicate, timeout=3):
        end = time.monotonic() + timeout
        while not predicate() and time.monotonic() < end:
            self.app.processEvents()
            time.sleep(.001)
        self.assertTrue(predicate(), self.errors)

    def test_split_unicode_document_is_published_once_after_helper_exit(self):
        value = {"name": "한글", "items": list(range(100))}
        payload = json.dumps(value, ensure_ascii=False).encode()
        self.command(f"import sys,time; data={payload!r}; "
                     "sys.stdout.buffer.write(data[:11]);sys.stdout.flush();time.sleep(.01);"
                     "sys.stdout.buffer.write(data[11:]);sys.stdout.flush();time.sleep(.1)")
        self.fetcher.start()
        self.until(lambda: bool(self.fetcher.output))
        self.assertFalse(self.ready)
        self.until(lambda: bool(self.ready))
        self.assertEqual(self.ready, [value])
        self.assertFalse(self.errors)
        self.assertEqual(self.fetcher.process.state(), QProcess.ProcessState.NotRunning)

    def test_missing_helper_fails_once_without_a_picker_or_retry_loop(self):
        self.fetcher.command = lambda: [str(Path(self.directory.name)/"missing-helper")]
        self.fetcher.start()
        self.until(lambda: bool(self.errors))
        self.assertEqual(len(self.errors), 1)
        self.assertFalse(self.fetcher.active)
        self.assertFalse(self.fetcher.deadline.isActive())
        self.assertFalse(self.fetcher.delayed_start.isActive())

    def test_runtime_failure_preserves_actionable_error_instead_of_a_price(self):
        self.command("raise SystemExit(10)")
        self.fetcher.start()
        self.until(lambda: bool(self.errors))
        self.assertIn("installer", self.errors[0])
        self.assertFalse(self.ready)

    def test_native_timeout_retains_only_bounded_stage_diagnostics(self):
        self.command("import sys;print('Market helper: controller (0x80004005)',file=sys.stderr);"
                     "print('private page or user text',file=sys.stderr);raise SystemExit(20)")
        self.fetcher.start();self.until(lambda:bool(self.errors))
        self.assertEqual(self.fetcher.failure_kind,'timeout')
        saved=json.loads((Path(self.directory.name)/'market-last-error.json').read_text())
        self.assertEqual(saved['exit_code'],20)
        self.assertEqual(saved['stages'],[['controller','0x80004005']])
        self.assertNotIn('private',json.dumps(saved))
        self.assertIn('too long',self.errors[0]);self.assertFalse(self.ready)

    def test_cancelled_start_failure_cannot_kill_a_later_request(self):
        self.fetcher.command = lambda: [str(Path(self.directory.name)/"missing-helper")]
        self.fetcher.start()
        self.fetcher.stop()
        self.until(lambda: self.fetcher.process.state() == QProcess.ProcessState.NotRunning)
        self.errors.clear()
        self.command("import time;time.sleep(1);print('{\"new\":true}')")
        self.fetcher.start()
        self.until(lambda: bool(self.ready))
        self.assertEqual(self.ready, [{"new": True}])
        self.assertFalse(self.errors)

    def test_malformed_non_object_or_multiple_documents_are_rejected(self):
        for payload in (b"", b"[]", b"{}\n{}\n", b"\xff"):
            with self.subTest(payload=payload):
                self.errors.clear()
                self.command(f"import sys;sys.stdout.buffer.write({payload!r})")
                self.fetcher.start()
                self.until(lambda: bool(self.errors))
                self.assertFalse(self.ready)

    def test_oversized_document_stops_the_helper_and_does_not_publish(self):
        self.command("import sys,time;sys.stdout.write('x'*4096);sys.stdout.flush();time.sleep(5)")
        with patch("price_lens.snapshot_fetcher.MAX_DOCUMENT", 1024):
            self.fetcher.start()
            self.until(lambda: bool(self.errors))
            self.until(lambda: self.fetcher.process.state() == QProcess.ProcessState.NotRunning)
        self.assertIn("too large", self.errors[0])
        self.assertEqual(len(self.errors), 1)
        self.assertFalse(self.ready)
        self.assertFalse(self.fetcher.output)

    def test_deadline_cancels_without_leaving_an_active_worker(self):
        self.command("import time;time.sleep(5)")
        self.fetcher.deadline.setInterval(30)
        self.fetcher.start()
        self.until(lambda: bool(self.errors))
        self.until(lambda: self.fetcher.process.state() == QProcess.ProcessState.NotRunning)
        self.assertIn("timed out", self.errors[0])
        self.assertFalse(self.ready)

    def test_cancelled_result_cannot_replace_a_new_request(self):
        self.command("import sys,time;sys.stdout.write('{\"old\":true}');sys.stdout.flush();time.sleep(.2)")
        self.fetcher.start()
        self.until(lambda: bool(self.fetcher.output))
        self.fetcher.stop()
        self.command("print('{\"new\":true}')")
        self.fetcher.start()
        self.until(lambda: bool(self.ready))
        self.assertEqual(self.ready, [{"new": True}])
        self.assertFalse(self.errors)

    def test_repeated_start_coalesces_and_closed_fetcher_cannot_restart(self):
        self.command("import time;time.sleep(.1);print('{}')")
        self.fetcher.start()
        for _ in range(50):
            self.fetcher.start()
        self.until(lambda: bool(self.ready))
        self.assertEqual(self.ready, [{}])
        self.fetcher.close()
        self.fetcher.start()
        self.app.processEvents()
        self.assertEqual(self.fetcher.process.state(), QProcess.ProcessState.NotRunning)


class NativeMarketHelperTests(unittest.TestCase):
    def test_native_self_test_reads_local_page_and_unicode_without_network(self):
        binary = market_binary(Path(__file__).resolve().parents[1])
        if not binary.is_file():
            self.skipTest("Build the native market helper first")
        if sys.platform != "win32" and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            self.skipTest("Native web view initialization needs a desktop; package checks run it in Xvfb")
        if sys.platform == "win32":
            check = subprocess.run([str(binary), "--runtime-check"], capture_output=True, timeout=10)
            if check.returncode == 10:
                self.skipTest("WebView2 runtime absent in this test environment")
            self.assertEqual(check.returncode, 0)
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([str(binary), "--profile", directory, "--self-test"],
                                    capture_output=True, timeout=25)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        self.assertEqual(json.loads(result.stdout), {"lupinMarketSelfTest": True, "text": "한글"})
