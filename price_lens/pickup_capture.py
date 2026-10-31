"""A bounded, crop-only reader; it never starts or owns screen sharing."""
from collections import deque
from pathlib import Path
import json
import time

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal
from PySide6.QtGui import QImage

from .platform_paths import reader_binary


class PickupWorker(QObject):
    result = Signal(dict)
    MAX_RESULT_BYTES = 128 * 1024
    TIMEOUT = 1.5

    def __init__(self, root, directory, parent=None):
        super().__init__(parent)
        self.root = Path(root)
        self.path = Path(directory) / "pickup-worker.rgba"
        self.process = QProcess(self)
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("RAYON_NUM_THREADS", "1")
        environment.insert("OMP_NUM_THREADS", "1")
        self.process.setProcessEnvironment(environment)
        self.process.readyReadStandardOutput.connect(self.on_output)
        self.process.readyReadStandardError.connect(self.drain_errors)
        self.process.finished.connect(self.on_finished)
        self.process.errorOccurred.connect(self.on_error)
        self.buffer = b""
        self.pending = False
        self.context = None
        self.started_at = 0.0
        self.last_start = float("-inf")
        self.closed = False
        self.timings = deque(maxlen=120)
        self.watchdog = QTimer(self)
        self.watchdog.setInterval(100)
        self.watchdog.timeout.connect(self.check_timeout)

    def submit(self, image, captured_at, generation, epoch, name_proof=None):
        if self.closed or self.pending or image.isNull():
            return False
        now = time.monotonic()
        if self.process.state() != QProcess.ProcessState.Running:
            if (self.process.state() == QProcess.ProcessState.NotRunning
                    and now - self.last_start >= 2):
                self.buffer = b""
                self.last_start = now
                self.process.start(str(reader_binary(self.root)))
            return False
        image = image.convertToFormat(QImage.Format.Format_RGBA8888)
        self.path.write_bytes(image.constBits())
        self.context = (generation, epoch, int(captured_at * 1000), name_proof)
        self.pending = True
        self.started_at = now
        self.watchdog.start()
        request = {"path": str(self.path), "width": image.width(),
                   "height": image.height(), "at_ms": self.context[2],
                   "pickups_only": True}
        self.process.write((json.dumps(request) + "\n").encode())
        return True

    def invalidate(self):
        # Leave the one in-flight buffer owned by its current read. Its result
        # is discarded; a newer frame is submitted only after it has finished.
        self.context = None

    def on_output(self):
        self.buffer += bytes(self.process.readAllStandardOutput())
        if len(self.buffer) > self.MAX_RESULT_BYTES:
            self.context = None
            self.process.kill()
            self.buffer = b""
            return
        while b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            context, self.context = self.context, None
            self.pending = False
            self.watchdog.stop()
            if context is None or self.closed:
                continue
            try:
                result = json.loads(line)
                if (not isinstance(result, dict) or result.get("error")
                        or result.get("pickupsRead") is not True
                        or result.get("atMs") != context[2]):
                    continue
            except (ValueError, TypeError):
                continue
            self.timings.append((time.monotonic() - self.started_at) * 1000)
            result["captureGeneration"] = context[0]
            result["trackingEpoch"] = context[1]
            result["pickupNameProof"] = context[3]
            self.result.emit(result)

    def check_timeout(self):
        if self.pending and time.monotonic() - self.started_at > self.TIMEOUT:
            self.context = None
            self.process.kill()

    def drain_errors(self):
        # Do not expose OCR text, captured messages or private paths in logs.
        self.process.readAllStandardError()

    def on_error(self, _error):
        self.context = None
        if self.process.state() == QProcess.ProcessState.NotRunning:
            self.pending = False

    def on_finished(self, _code, _status):
        self.pending = False
        self.context = None
        self.buffer = b""
        self.watchdog.stop()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.watchdog.stop()
        self.context = None
        self.process.closeWriteChannel()
        if not self.process.waitForFinished(400):
            self.process.kill()
            self.process.waitForFinished(600)
