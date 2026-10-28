"""Offline installed-package checks. Never captures a screen or interacts with a game."""
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from .qt_runtime import configure_qt
    configure_qt()
    from PySide6.QtCore import qVersion, QTimer, QLibrary, QLibraryInfo
    from PySide6.QtGui import QImage
    from PySide6.QtMultimedia import QScreenCapture  # noqa: F401
    from PySide6.QtNetwork import QLocalSocket  # noqa: F401
    from PySide6.QtWidgets import QApplication
    from .platform_paths import reader_binary, capture_socket_name
    from .overlay import Overlay

    plugins = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath))
    names = (["multimedia/ffmpegmediaplugin.dll", "platforms/qwindows.dll"] if sys.platform == "win32"
             else ["multimedia/libffmpegmediaplugin.so", "platforms/libqxcb.so", "platforms/libqwayland.so"])
    libraries = []
    for name in names:
        library = QLibrary(str(plugins / name))
        assert library.load(), "Cannot load " + name + ": " + library.errorString()
        libraries.append(library)
    print("PASS: OS capture and desktop platform plugins load", flush=True)
    from .tls import make_context
    import ssl
    context = make_context()
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    print("PASS: HTTPS certificate and hostname verification are enabled", flush=True)

    root = Path(__file__).resolve().parent.parent
    binary = reader_binary(root)
    print("Python:", sys.version.split()[0], "Qt:", qVersion(), "platform:", sys.platform, flush=True)
    if not binary.is_file():
        raise FileNotFoundError("Missing screen reader: " + str(binary))
    if sys.platform == "win32":
        assert ":" not in capture_socket_name() and "/" not in capture_socket_name(), "Invalid Windows pipe name"
    fixture = root / "selftest-data/gems-and-ores.png"
    if not fixture.is_file():
        fixture = root / "vendor/minerva/samples/player-shop/gems-and-ores.png"
    image = QImage(str(fixture))
    assert not image.isNull(), "Missing OCR fixture"
    request = {"path": str(fixture), "at_ms": 1000, "pointer": None}
    result = subprocess.run([str(binary)], input=json.dumps(request) + "\n", text=True,
                            capture_output=True, timeout=30,
                            env={**os.environ, "RAYON_NUM_THREADS": "2"})
    assert result.returncode == 0, result.stderr
    reading = json.loads(result.stdout)
    expected = json.loads(fixture.with_suffix(".json").read_text())
    actual = [{"name": row["name"], **row["price"]} for row in reading["shop"]["rows"]]
    assert actual == expected, (actual, expected)
    print("PASS: reader recognizes real item names, quantities and prices", flush=True)
    print("PASS: Qt screen-capture, local IPC and image decoder modules load", flush=True)
    app = QApplication.instance() or QApplication([])
    from PySide6.QtMultimedia import QMediaCaptureSession, QVideoFrame, QVideoSink
    media = QMediaCaptureSession()
    sink = QVideoSink()
    media.setVideoSink(sink)
    probe_image = QImage(2, 2, QImage.Format.Format_RGBA8888)
    probe_image.fill(0xff123456)
    sink.setVideoFrame(QVideoFrame(probe_image))
    assert sink.videoFrame().isValid(), "The Qt media backend could not initialize"
    media.setVideoSink(None)
    print("PASS: actual Qt media backend accepts a local frame without screen capture", flush=True)
    probe = Overlay(root)
    points = []

    def pointer(x, y):
        if not points:
            points.append((x, y))
            app.quit()

    probe.pointer.connect(pointer)
    probe.update([0, 0, 800, 600], [], hover_enabled=True)
    QTimer.singleShot(5000, app.quit)
    app.exec()
    probe.close()
    assert points, "The independent overlay helper did not report the OS pointer: " + probe.last_error
    print("PASS: independent overlay helper and local stdin/stdout work", flush=True)
    print("No screen capture, mouse input or game-process interaction occurred.", flush=True)
    return 0
