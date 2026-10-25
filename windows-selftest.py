"""Offline Windows package checks; never captures a screen or opens a game."""
import json
import os
from pathlib import Path
import subprocess
import sys

from PySide6.QtCore import qVersion, QTimer
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import QScreenCapture
from PySide6.QtNetwork import QLocalSocket
from price_lens.platform_paths import reader_binary, capture_socket_name
from price_lens.overlay import Overlay
from PySide6.QtWidgets import QApplication

root = Path(__file__).resolve().parent
binary = reader_binary(root)
print("Python:", sys.version.split()[0], "Qt:", qVersion(), "platform:", sys.platform)
assert binary.is_file(), f"Missing screen reader: {binary}"
assert ":" not in capture_socket_name() and "/" not in capture_socket_name(), "Invalid Windows pipe name"
fixture = root / "selftest-data/gems-and-ores.png"
image = QImage(str(fixture))
assert not image.isNull(), "Missing OCR fixture"
request = {"path": str(fixture), "at_ms": 1000, "pointer": None}
result = subprocess.run([str(binary)], input=json.dumps(request) + "\n", text=True,
                        capture_output=True, timeout=30, env={**os.environ, "RAYON_NUM_THREADS": "2"})
assert result.returncode == 0, result.stderr
reading = json.loads(result.stdout)
expected = json.loads((root / "selftest-data/gems-and-ores.json").read_text())
actual = [{"name": row["name"], **row["price"]} for row in reading["shop"]["rows"]]
assert actual == expected, (actual, expected)
print("PASS: Windows reader recognizes real item names, quantities and prices")
print("PASS: Qt screen capture, local IPC, image decoder and Windows pipe naming import correctly")
app = QApplication([])
probe = Overlay(root)
points = []
def pointer(x, y):
    if not points:
        points.append((x, y))
        probe.close()
        app.quit()
probe.pointer.connect(pointer)
probe.update([0, 0, 800, 600], [], hover_enabled=True)
QTimer.singleShot(5000, app.quit)
app.exec()
probe.close()
assert points, "The independent overlay helper did not report the OS pointer: " + probe.last_error
print("PASS: independent overlay helper and its local stdin/stdout work")
print("No screen capture, mouse input or game-process interaction occurred.")
