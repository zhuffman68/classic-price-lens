"""A Windows upgrade must await our own process exit, not just pipe closure."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

from price_lens.platform_paths import market_binary


@unittest.skipUnless(sys.platform == "win32", "Windows installer process wait")
class NativeShutdownTests(unittest.TestCase):
    def test_closes_only_our_test_pipe_and_waits_for_delayed_process_exit(self):
        root = Path(__file__).resolve().parents[1]
        binary = market_binary(root)
        if not binary.is_file():
            self.skipTest("Build the native market helper first")
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            # Setup can close an older panel before the loader/runtime exists.
            client = folder / "lupin-close.exe"
            shutil.copy2(binary, client)
            marker = folder / "ready"
            env = {**os.environ, "LOGNAME": "LupinShutdownTest" + uuid.uuid4().hex}
            script = ("import sys,time;from pathlib import Path;"
                      f"sys.path.insert(0,{str(root)!r});"
                      "from PySide6.QtCore import QCoreApplication;"
                      "from price_lens.control import AppControl;"
                      "app=QCoreApplication([]);"
                      f"control=AppControl(lock_path=Path({str(folder/'fixture.lock')!r}));"
                      "assert control.start();control.quit.connect(app.quit);"
                      f"Path({str(marker)!r}).touch();app.exec();control.close();time.sleep(1)")
            server = subprocess.Popen([sys.executable, "-B", "-u", "-c", script], env=env,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 15
                while not marker.exists() and server.poll() is None and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertTrue(marker.exists(), "Own fixture control server did not start")
                started = time.monotonic()
                result = subprocess.run([str(client), "--close-panel"], env=env, capture_output=True, timeout=20)
                elapsed = time.monotonic() - started
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(server.poll(), 0, "Pipe closed before our process finished unloading")
                self.assertGreaterEqual(elapsed, .9)
                server.communicate(timeout=2)
                # No server is a successful no-op; never look for another PID.
                result = subprocess.run([str(client), "--close-panel"], env=env, capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
            finally:
                if server.poll() is None:
                    server.terminate()
                    server.communicate(timeout=5)
