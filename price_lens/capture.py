"""OS screen sharing only. No process discovery, game APIs, hooks or input APIs."""
from pathlib import Path
from collections import deque
import hashlib
import os
import tempfile
import time
import sys

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal, QRect, QPoint
from PySide6.QtGui import QImage
import json
from .stream import StreamClient, screen_pixels
from .platform_paths import reader_binary


class PixelReader(QObject):
    reading = Signal(dict)
    status = Signal(str)
    image_ready = Signal(QImage)

    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.root = Path(root)
        self.temp = tempfile.TemporaryDirectory(prefix="classic-price-lens-", dir=os.environ.get("XDG_RUNTIME_DIR"))
        self.image = QImage()
        self.last_frame = 0.0
        self.image_sequence = 0
        self.submitted_sequence = -1
        self.latest_latency_ms = None
        self.timings = deque(maxlen=240)
        self.last_metrics = 0
        self.shop_rect = None
        self.shop_fingerprint = None
        self.tooltip_enabled = False
        self.pointer = None
        self.last_pointer = None
        self.tooltip_rect = None
        self.tooltip_fingerprint = None
        self.using_roi = False
        self.shop_context = None
        self.crop = None
        self.pending = False
        self.paused = False
        self.generation = 0
        self.pending_generation = 0
        self.pending_since = 0.0
        self.buffer = b""
        self.kde_screen = None
        self.kde_desktop = None
        self.stream = StreamClient(root, self)
        self.stream.frame.connect(self.on_stream_frame)
        self.stream.status.connect(self.status)
        self.process = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("RAYON_NUM_THREADS", "2")
        env.insert("OMP_NUM_THREADS", "2")
        self.process.setProcessEnvironment(env)
        self.process.readyReadStandardOutput.connect(self.on_output)
        self.process.readyReadStandardError.connect(self.on_stderr)
        self.process.errorOccurred.connect(lambda error: self.status.emit("Reader could not start; run ./setup.sh"))
        self.process.finished.connect(self.on_finished)
        self.process.start(str(reader_binary(self.root)))
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.scan)
        self.timer.start()
        self.screenshot = QProcess(self)
        self.screenshot.finished.connect(self.on_screenshot)
        self.screenshot.errorOccurred.connect(lambda error: self.status.emit("KDE screen capture failed"))
        self.screenshot_timer = QTimer(self)
        self.screenshot_timer.setInterval(300)
        self.screenshot_timer.timeout.connect(self.take_screenshot)

    def start(self, screen, desktop):
        self.generation += 1
        self.paused = False
        self.timer.start()
        self.screenshot_timer.stop()
        self.shop_rect = self.shop_fingerprint = None
        self.shop_context = None
        self.tooltip_rect = self.tooltip_fingerprint = None
        self.status.emit("Capturing the selected monitor" if sys.platform == "win32" else "Choose a monitor or full workspace in the OS sharing dialog")
        self.stream.start(screen, desktop)

    def pause(self, keep_stream=False):
        self.generation += 1
        self.paused = True
        self.timer.stop()
        self.screenshot_timer.stop()
        if keep_stream:
            self.stream.set_paused(True)
        else:
            self.stream.stop()

    def start_kde(self, screen, desktop):
        self.pause()
        self.paused = False
        self.timer.start()
        self.shop_rect = self.shop_fingerprint = None
        self.kde_screen = screen
        self.kde_desktop = desktop
        self.screenshot_timer.start()
        self.status.emit("KDE screenshot fallback • continuous, one capture at a time")
        self.take_screenshot()

    def take_screenshot(self):
        if self.screenshot.state() != QProcess.ProcessState.NotRunning:
            return
        path = str(Path(self.temp.name) / "desktop.bmp")
        self.screenshot.start("spectacle", ["-b", "-n", "-f", "-o", path])

    def on_screenshot(self, code, status):
        if code or not self.screenshot_timer.isActive():
            return
        path = Path(self.temp.name) / "desktop.bmp"
        image = QImage(str(path))
        if image.isNull():
            self.status.emit("KDE returned an empty screenshot")
            return
        self.image = screen_pixels(image, self.kde_screen, self.kde_desktop)
        path.unlink(missing_ok=True)
        self.last_frame = time.monotonic()
        self.image_sequence += 1
        self.image_ready.emit(self.image)
        self.scan()

    def on_stream_frame(self, image, captured_at):
        if self.paused:
            return
        if not image.isNull():
            self.last_frame = captured_at
            self.image = image
            self.image_sequence += 1
            self.image_ready.emit(self.image)
            self.scan()

    def load_image(self, path):
        self.pause()
        self.paused = False
        self.timer.start()
        self.image = QImage(str(path))
        if self.image.isNull():
            self.status.emit("Could not open screenshot")
            return
        self.crop = None
        self.shop_rect = self.shop_fingerprint = None
        self.last_frame = time.monotonic()
        self.image_sequence += 1
        self.image_ready.emit(self.image)
        self.status.emit("Screenshot mode • saved image, not a live capture")
        self.scan()

    def scan(self):
        if self.paused:
            return
        if self.pending:
            if time.monotonic() - self.pending_since > 25:
                self.process.kill()
                self.status.emit("Screen reader timed out; restart the app")
            return
        if self.image.isNull() or self.process.state() != QProcess.ProcessState.Running:
            return
        if self.image_sequence == self.submitted_sequence:
            return
        image = self.image.copy(self.crop) if self.crop else self.image
        pointer = self.pointer
        if pointer and self.crop:
            pointer = (pointer[0] - self.crop.x(), pointer[1] - self.crop.y())
        in_shop = pointer_in_shop(pointer, self.shop_context)
        hover_check = self.tooltip_enabled and pointer is not None and not in_shop
        tooltip_same = False
        if hover_check and self.tooltip_rect and self.tooltip_fingerprint is not None and self.pointer == self.last_pointer:
            tooltip_same = hashlib.blake2b(image.copy(self.tooltip_rect).constBits(), digest_size=8).digest() == self.tooltip_fingerprint
        if self.shop_rect and self.shop_fingerprint is not None:
            patch = image.copy(self.shop_rect)
            fingerprint = hashlib.blake2b(patch.constBits(), digest_size=8).digest()
            if fingerprint == self.shop_fingerprint and (not hover_check or tooltip_same):
                self.submitted_sequence = self.image_sequence
                return
        elif self.shop_rect is None and tooltip_same:
            self.submitted_sequence = self.image_sequence
            return
        if self.shop_rect is None and time.monotonic() - self.pending_since < 0.2:
            return
        origin = {"x": 0, "y": 0}
        self.using_roi = bool(self.shop_rect and not hover_check)
        if self.using_roi:
            region = self.shop_rect.adjusted(-8, -8, 8, 8).intersected(image.rect())
            origin = {"x": region.x(), "y": region.y()}
            image = image.copy(region)
        image = image.convertToFormat(QImage.Format.Format_RGBA8888)
        path = Path(self.temp.name) / "frame.rgba"
        path.write_bytes(image.constBits())
        self.pending = True
        self.pending_generation = self.generation
        self.pending_since = time.monotonic()
        self.submitted_sequence = self.image_sequence
        self.last_pointer = self.pointer
        request = {"path": str(path), "at_ms": int(self.last_frame * 1000),
                   "pointer": {"x": pointer[0], "y": pointer[1]} if pointer and self.tooltip_enabled else None,
                   "tooltip": bool(hover_check),
                   "origin": origin,
                   "width": image.width(), "height": image.height()}
        self.process.write((json.dumps(request) + "\n").encode())

    def on_output(self):
        self.buffer += bytes(self.process.readAllStandardOutput())
        while b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            self.pending = False
            try:
                result = json.loads(line)
                if self.paused or self.pending_generation != self.generation:
                    continue
                if result.get("error"):
                    self.status.emit("Reader: " + result["error"])
                else:
                    area = (result.get("shop") or {}).get("area")
                    if self.using_roi and area is None:
                        # A moved/closed shop triggers an immediate full search
                        # in the same captured frame, not another polling delay.
                        self.image_sequence += 1
                        self.pending_since = 0
                    self.shop_rect = QRect(area["x"], area["y"], area["width"], area["height"]) if area else None
                    if self.shop_rect:
                        if self.shop_context is None or abs(self.shop_context.x() - self.shop_rect.x()) > 4 or not self.shop_context.intersects(self.shop_rect):
                            self.shop_context = self.shop_rect
                        else:
                            self.shop_context = self.shop_context.united(self.shop_rect)
                    else:
                        point = self.pointer
                        if point and self.crop:
                            point = (point[0] - self.crop.x(), point[1] - self.crop.y())
                        if not pointer_in_shop(point, self.shop_context):
                            self.shop_context = None
                    if self.shop_rect:
                        source = self.image.copy(self.crop) if self.crop else self.image
                        # Only bind a fingerprint to the exact frame that was read.
                        self.shop_fingerprint = (hashlib.blake2b(source.copy(self.shop_rect).constBits(), digest_size=8).digest()
                                                 if self.image_sequence == self.submitted_sequence else None)
                    else:
                        self.shop_fingerprint = None
                    tooltip = (result.get("tooltip") or {})
                    found = tooltip.get("found") if isinstance(tooltip, dict) else None
                    tooltip_area = found.get("area") if found else None
                    self.tooltip_rect = QRect(tooltip_area["x"], tooltip_area["y"], tooltip_area["width"], tooltip_area["height"]) if tooltip_area else None
                    if self.tooltip_rect and self.image_sequence == self.submitted_sequence:
                        source = self.image.copy(self.crop) if self.crop else self.image
                        self.tooltip_fingerprint = hashlib.blake2b(source.copy(self.tooltip_rect).constBits(), digest_size=8).digest()
                    else:
                        self.tooltip_fingerprint = None
                    self.latest_latency_ms = time.monotonic() * 1000 - result["atMs"]
                    self.timings.append({"capture_to_read_ms": round(self.latest_latency_ms, 1),
                                         "ocr_ms": round(result.get("ocrMs", 0), 1),
                                         "rows": len((result.get("shop") or {}).get("rows", []))})
                    self.reading.emit(result)
                    metrics = os.environ.get("CLASSIC_LENS_METRICS")
                    if metrics and time.monotonic() - self.last_metrics > 1:
                        Path(metrics).write_text(json.dumps(list(self.timings), indent=2) + "\n")
                        self.last_metrics = time.monotonic()
            except (ValueError, TypeError) as error:
                self.status.emit(f"Reader returned an invalid result: {error}")
        if self.image_sequence != self.submitted_sequence:
            QTimer.singleShot(0, self.scan)

    def on_stderr(self):
        # Keep the stream drained; no game pixels or OCR strings are sent anywhere.
        message = bytes(self.process.readAllStandardError()).decode(errors="replace")
        if message.strip():
            self.status.emit("Reader: " + message[-300:].strip())

    def on_finished(self, code, status):
        self.pending = False
        if code:
            self.status.emit(f"Screen reader stopped ({code}); restart the app")

    def close(self, keep_stream=False):
        self.timer.stop()
        self.screenshot_timer.stop()
        if self.screenshot.state() != QProcess.ProcessState.NotRunning:
            self.screenshot.kill()
            self.screenshot.waitForFinished(1000)
        self.stream.stop(keep_session=keep_stream)
        self.process.closeWriteChannel()
        if not self.process.waitForFinished(1500):
            self.process.kill()
            self.process.waitForFinished(1000)
        self.temp.cleanup()


def pointer_in_shop(pointer, shop_context):
    return bool(pointer is not None and shop_context is not None and shop_context.contains(QPoint(*pointer)))
