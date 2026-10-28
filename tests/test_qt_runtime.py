"""Exercise the helper entry point with desktop-wide foreign plugin paths."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class QtRuntimeTests(unittest.TestCase):
    def test_capture_helper_isolates_plugins_and_initializes_backend_without_capture(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            foreign = folder / "foreign-qt-plugins"
            foreign.mkdir()
            script = r'''
import sys, uuid
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtGui import QImage
import price_lens.stream as stream
original = stream.CaptureServer
class Probe(original):
    def __init__(self, app):
        assert sys.argv[1] not in app.libraryPaths(), app.libraryPaths()
        super().__init__(app)
        if sys.platform == 'win32':
            from price_lens.windows_capture import WindowsDesktopCapture
            assert isinstance(self.capture, WindowsDesktopCapture)
            assert self.session is None and self.sink is None
            assert not self.capture.timer.isActive(), 'Desktop capture started during construction'
        else:
            from PySide6.QtMultimedia import QVideoFrame
            image = QImage(2, 2, QImage.Format.Format_RGBA8888)
            image.fill(0xff123456)
            self.sink.setVideoFrame(QVideoFrame(image))
            assert self.sink.videoFrame().isValid(), 'Media backend did not initialize'
        assert not self.capture.isActive(), 'Test must never start OS sharing'
        QTimer.singleShot(0, app.quit)
stream.CaptureServer = Probe
stream.socket_name = lambda: 'ClassicPriceLens-runtime-test-' + identifier
identifier = uuid.uuid4().hex
stream.capture_lock_path = lambda: str(Path(sys.argv[2]) / 'capture.lock')
raise SystemExit(stream.main())
'''
            result = subprocess.run(
                [sys.executable, "-B", "-c", script, str(foreign), temporary],
                cwd=Path(__file__).resolve().parents[1],
                env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_MEDIA_BACKEND": "ffmpeg",
                     "QT_PLUGIN_PATH": str(foreign), "QT_QPA_PLATFORM_PLUGIN_PATH": str(foreign)},
                capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
