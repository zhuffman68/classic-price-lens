"""OS screen sharing only. No process discovery, game APIs, hooks or input APIs."""
from pathlib import Path
from collections import deque
import hashlib
import os
import tempfile
import time
import sys

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal, QRect, QPoint, Qt
from PySide6.QtGui import QImage
import json
from .stream import StreamClient, screen_pixels
from .platform_paths import reader_binary
from .capture_platform import uses_system_picker


class PixelReader(QObject):
    reading = Signal(dict)
    status = Signal(str)
    image_ready = Signal(QImage)
    area_changed = Signal()
    experience = Signal(dict)

    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.root = Path(root)
        self.temp = tempfile.TemporaryDirectory(prefix="classic-price-lens-", dir=os.environ.get("XDG_RUNTIME_DIR"))
        self.image = QImage()
        self.last_frame = 0.0
        self.image_sequence = 0
        self.submitted_sequence = -1
        self.latest_latency_ms = None
        self.experience_enabled = False
        self.prices_enabled = True
        self.pending_locate_only = False
        self.last_experience = 0.0
        self.last_map_read = 0.0
        self.last_pickup = self.last_pickup_frame = 0.0
        self.pending_experience = False
        self.pending_pickups = False
        self.exclude_regions = lambda: []
        self.timings = deque(maxlen=240)
        self.last_metrics = 0
        self.shop_rect = None
        self.shop_fingerprint = None
        self.tooltip_enabled = False
        self.pointer = None
        self.last_pointer = None
        self.tooltip_rect = None
        self.tooltip_fingerprint = None
        self.tooltip_retry_requested = False
        self.tooltip_retry_key = None
        self.tooltip_retry_at = 0.0
        self.using_roi = False
        self.roi_clean = True
        self.shop_context = None
        self.crop = None
        self.auto_enabled = True
        self.live_source = False
        self.game_area = None
        self.game_guards = []
        self.submitted_image = QImage()
        self.next_area_search = 0.0
        self.last_geometry_check = 0.0
        self.last_locator_check = 0.0
        self.pending_local_roi = False
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
        self.live_source = True
        self.reset_area()
        self.timer.start()
        self.screenshot_timer.stop()
        self.shop_rect = self.shop_fingerprint = None
        self.shop_context = None
        self.tooltip_rect = self.tooltip_fingerprint = None
        self.status.emit("Choose a monitor or full workspace in the system sharing dialog"
                         if uses_system_picker() else "Capturing the selected display")
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
        self.live_source = True
        self.reset_area()
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
        self.validate_area()
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
            self.validate_area()
            self.image_sequence += 1
            self.image_ready.emit(self.image)
            self.scan()

    def load_image(self, path):
        self.pause()
        self.paused = False
        self.live_source = False
        self.reset_area()
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

    @property
    def auto_active(self):
        return self.auto_enabled and self.live_source and self.crop is None

    def reset_area(self):
        self.game_area = None
        self.game_guards = []
        self.next_area_search = 0
        self.shop_rect = self.shop_fingerprint = self.shop_context = None
        self.tooltip_rect = self.tooltip_fingerprint = None
        self.last_experience = self.last_map_read = self.last_pickup = self.last_pickup_frame = 0
        self.area_changed.emit()

    def set_auto_area(self, enabled):
        self.auto_enabled = enabled
        if enabled:
            self.crop = None
        self.generation += 1
        self.reset_area()
        self.image_sequence += 1
        self.scan()

    def set_crop(self, area):
        self.generation += 1
        self.crop = area
        self.reset_area()
        self.image_sequence += 1
        self.scan()

    @staticmethod
    def fingerprint(image, area):
        # constBits() borrows storage; retain the QImage until hashing completes.
        patch = image.copy(area)
        return hashlib.blake2b(patch.constBits(), digest_size=8).digest()

    def validate_area(self):
        if self.auto_active and self.game_area and any(
                not self.guard_matches(self.image, area, digest) for area, digest in self.game_guards):
            # Discard results from the old position before drawing another label.
            self.generation += 1
            self.reset_area()

    @staticmethod
    def guard_signature(image, area):
        if image.isNull() or not image.rect().contains(area):return None
        patch=image.copy(area).scaled(16,16,Qt.AspectRatioMode.IgnoreAspectRatio,
             Qt.TransformationMode.SmoothTransformation).convertToFormat(QImage.Format.Format_Grayscale8)
        return bytes(patch.constBits())

    @classmethod
    def guard_matches(cls,image,area,reference):
        current=cls.guard_signature(image,area)
        if current is None or reference is None:return False
        gain=sum(current)/max(1,sum(reference))
        if not .80<=gain<=1.20:return False
        return sum(abs(a-b*gain) for a,b in zip(current,reference))/len(current)<8

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
        now = time.monotonic()
        exp_due = (self.experience_enabled and self.live_source and now-self.last_frame < 3
                and now-self.last_experience >= 1
                and (self.game_area is not None if self.auto_active else self.crop is not None))
        pickups_due = (self.experience_enabled and self.live_source and now-self.last_frame < 1.5
                and now-self.last_pickup >= .2 and self.last_frame > self.last_pickup_frame
                and (self.game_area is not None if self.auto_active else self.crop is not None))
        if self.image_sequence == self.submitted_sequence:
            if exp_due:self.scan_experience(now)
            elif pickups_due:self.scan_pickups(now)
            return
        if self.auto_active and self.game_area is None and time.monotonic() < self.next_area_search:
            return
        if not self.prices_enabled:
            if self.auto_active and (self.game_area is None or now-self.last_locator_check>=1):
                self.scan_location(now)
            elif exp_due:self.scan_experience(now)
            elif pickups_due:self.scan_pickups(now)
            else:self.submitted_sequence=self.image_sequence
            return
        image = self.image.copy(self.crop) if self.crop else self.image
        pointer = self.pointer
        if pointer and self.crop:
            pointer = (pointer[0] - self.crop.x(), pointer[1] - self.crop.y())
        in_shop = pointer_in_shop(pointer, self.shop_context)
        hover_check = self.tooltip_enabled and pointer is not None and not in_shop
        if self.auto_active:
            hover_check = bool(hover_check and self.game_area and self.game_area.contains(QPoint(*pointer)))
        tooltip_same = False
        if hover_check and not self.tooltip_retry_requested and self.tooltip_rect and self.tooltip_fingerprint is not None and self.pointer == self.last_pointer:
            tooltip_same = self.fingerprint(image, self.tooltip_rect) == self.tooltip_fingerprint
        if self.shop_rect and self.shop_fingerprint is not None:
            patch = image.copy(self.shop_context or self.shop_rect)
            fingerprint = hashlib.blake2b(patch.constBits(), digest_size=8).digest()
            shop_hover_due = in_shop and (self.pointer != self.last_pointer or time.monotonic() - self.last_geometry_check >= 0.2)
            if (fingerprint == self.shop_fingerprint and not shop_hover_due and (not hover_check or tooltip_same)
                    and (not self.auto_active or now-self.last_locator_check<1.0)):
                self.submitted_sequence = self.image_sequence
                if exp_due:self.scan_experience(now)
                elif pickups_due:self.scan_pickups(now)
                return
        elif self.shop_rect is None and tooltip_same:
            self.submitted_sequence = self.image_sequence
            if exp_due:self.scan_experience(now)
            elif pickups_due:self.scan_pickups(now)
            return
        if self.shop_rect is None and time.monotonic() - self.pending_since < 0.2:
            return
        if exp_due and now-self.last_experience>=1.6:
            self.scan_experience(now)
            return
        if pickups_due and now-self.last_pickup>=.45:
            self.scan_pickups(now)
            return
        origin = {"x": 0, "y": 0}
        self.using_roi = bool(self.shop_rect and self.roi_clean and not hover_check)
        self.pending_local_roi=bool(self.auto_active and self.using_roi and self.game_area
                                   and now-self.last_locator_check<1.0)
        if self.using_roi:
            region = (self.shop_context or self.shop_rect).adjusted(-16, -16, 16, 16).intersected(image.rect())
            if not self.auto_active or self.pending_local_roi:
                origin = {"x": region.x(), "y": region.y()}
                image = image.copy(region)
        if self.auto_active and not self.pending_local_roi:self.last_locator_check=now
        image = image.convertToFormat(QImage.Format.Format_RGBA8888)
        path = Path(self.temp.name) / "frame.rgba"
        path.write_bytes(image.constBits())
        self.pending = True
        self.pending_locate_only=False
        self.pending_experience = False
        self.pending_pickups = False
        self.pending_generation = self.generation
        self.pending_since = time.monotonic()
        self.last_geometry_check = self.pending_since
        self.submitted_sequence = self.image_sequence
        self.submitted_image = self.image
        self.last_pointer = self.pointer
        request = {"path": str(path), "at_ms": int(self.last_frame * 1000),
                   "pointer": {"x": pointer[0], "y": pointer[1]} if pointer is not None else None,
                   "tooltip": bool(hover_check),
                   "tooltip_retry": bool(hover_check and self.tooltip_retry_requested),
                   "origin": origin,
                   "auto_game": self.auto_active and not self.pending_local_roi,
                   "roi": {"x": region.x(), "y": region.y(), "width": region.width(), "height": region.height()} if self.auto_active and self.using_roi and not self.pending_local_roi else None,
                   "width": image.width(), "height": image.height()}
        self.tooltip_retry_requested = False
        self.process.write((json.dumps(request) + "\n").encode())

    def retry_tooltip(self, key):
        now=time.monotonic()
        if key is None or key==self.tooltip_retry_key or now-self.tooltip_retry_at<.5:return
        self.tooltip_retry_key=key;self.tooltip_retry_at=now
        self.tooltip_retry_requested=True;self.image_sequence+=1
        QTimer.singleShot(0,self.scan)

    def scan_location(self,now):
        image=self.image.convertToFormat(QImage.Format.Format_RGBA8888)
        path=Path(self.temp.name)/'location.rgba';path.write_bytes(image.constBits())
        self.pending=True;self.pending_experience=False;self.pending_pickups=False;self.pending_locate_only=True
        self.pending_local_roi=False;self.pending_generation=self.generation
        self.pending_since=self.last_locator_check=now
        self.submitted_sequence=self.image_sequence;self.submitted_image=self.image
        self.process.write((json.dumps({'path':str(path),'at_ms':int(self.last_frame*1000),
             'auto_game':True,'locate_only':True,'width':image.width(),'height':image.height()})+'\n').encode())

    def scan_experience(self, now):
        # Reuse this capture and this OCR process. Map search is infrequent;
        # ordinary EXP samples transport only the bottom 256 pixels.
        area = self.game_area if self.auto_active else self.crop
        if area is None:
            return
        area = area.intersected(self.image.rect())
        read_map = now-self.last_map_read >= 5
        if not read_map:
            area = QRect(area.x(), max(area.y(), area.bottom()+1-256), area.width(), min(256, area.height()))
        image = self.image.copy(area).convertToFormat(QImage.Format.Format_RGBA8888)
        if image.isNull():
            return
        path = Path(self.temp.name)/"experience.rgba"
        path.write_bytes(image.constBits())
        self.pending = self.pending_experience = True
        self.pending_pickups = self.pending_locate_only = False
        self.pending_generation = self.generation
        self.pending_since = self.last_experience = now
        if read_map:
            self.last_map_read = now
        request = {"path":str(path),"width":image.width(),"height":image.height(),
                   "at_ms":int(self.last_frame*1000),"experience_only":True,"read_map":read_map,
                   "origin":{"x":area.x(),"y":area.y()}}
        self.process.write((json.dumps(request)+"\n").encode())

    @staticmethod
    def pickup_area(game):
        """Keep the footer and our bottom-left tracking cards outside the ROI."""
        width=min(640,max(180,round(game.width()*.48)))
        height=min(300,max(40,round(game.height()*.32)))
        footer=min(64,max(28,round(game.height()*.08)))
        return QRect(game.right()+1-width,max(game.y(),game.bottom()+1-footer-height),width,height).intersected(game)

    def scan_pickups(self,now):
        game=self.game_area if self.auto_active else self.crop
        if game is None:return
        area=self.pickup_area(game).intersected(self.image.rect())
        if any(area.intersects(region) for region in self.exclude_regions()):
            self.last_pickup=now;self.last_pickup_frame=self.last_frame
            self.experience.emit({'atMs':int(self.last_frame*1000),'pickupsRead':True,
                                  'pickups':{'valid':False,'covered':True,'lines':[]}})
            return
        image=self.image.copy(area).convertToFormat(QImage.Format.Format_RGBA8888)
        if image.isNull():return
        path=Path(self.temp.name)/'pickups.rgba';path.write_bytes(image.constBits())
        self.pending=self.pending_pickups=True
        self.pending_experience=self.pending_locate_only=False
        self.pending_generation=self.generation;self.pending_since=self.last_pickup=now
        self.last_pickup_frame=self.last_frame
        self.process.write((json.dumps({'path':str(path),'width':image.width(),'height':image.height(),
            'at_ms':int(self.last_frame*1000),'pickups_only':True})+'\n').encode())

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
                    if self.pending_experience or self.pending_pickups:
                        if self.experience_enabled and time.monotonic()*1000-result.get("atMs",0) < 3000:
                            self.experience.emit(result)
                        continue
                    if self.auto_active and not self.pending_local_roi:
                        area = result.get("gameArea")
                        guards = [QRect(r["x"], r["y"], r["width"], r["height"]) for r in result.get("gameGuards") or []]
                        fingerprints = [(r, self.guard_signature(self.submitted_image, r)) for r in guards]
                        if area and (not fingerprints or any(not self.guard_matches(self.image, r, digest) for r, digest in fingerprints)):
                            self.reset_area()
                            continue
                        selected = QRect(area["x"], area["y"], area["width"], area["height"]) if area else None
                        changed = selected != self.game_area
                        self.game_area, self.game_guards = selected, fingerprints
                        if selected is None:
                            self.next_area_search = time.monotonic() + 0.4
                        if changed:
                            self.area_changed.emit()
                    if self.pending_locate_only:continue
                    area = (result.get("shop") or {}).get("area")
                    rows = (result.get("shop") or {}).get("rows") or []
                    clean = all(row.get("covered") or row.get("name") and row.get("price") for row in rows)
                    if self.using_roi and area and not clean:
                        # A slightly moved shop can still be found inside the old
                        # crop while the tail of each price is clipped. Read the
                        # full current frame before publishing incomplete rows.
                        self.shop_rect = self.shop_fingerprint = None
                        self.image_sequence += 1
                        self.pending_since = 0
                        continue
                    self.roi_clean = bool(clean)
                    if self.using_roi and area is None and (not self.auto_active or self.game_area):
                        # A moved/closed shop triggers an immediate full search
                        # in the same captured frame, not another polling delay.
                        self.image_sequence += 1
                        self.pending_since = 0
                    self.shop_rect = QRect(area["x"], area["y"], area["width"], area["height"]) if area else None
                    # NPC buy/sell tables can share the player's shop palette
                    # without any readable player listings. That rectangle
                    # alone must not suppress the independent tooltip reader.
                    if self.shop_rect and rows:
                        if self.shop_context is None or abs(self.shop_context.x() - self.shop_rect.x()) > 4 or not self.shop_context.intersects(self.shop_rect):
                            self.shop_context = self.shop_rect
                        else:
                            self.shop_context = self.shop_context.united(self.shop_rect)
                    else:
                        self.shop_context = None
                    if self.shop_rect:
                        source = self.submitted_image.copy(self.crop) if self.crop else self.submitted_image
                        # Compare later frames with the frame actually recognised.
                        # New captures arriving during OCR must not disable caching.
                        self.shop_fingerprint = self.fingerprint(source, self.shop_context or self.shop_rect)
                    else:
                        self.shop_fingerprint = None
                    tooltip = (result.get("tooltip") or {})
                    found = tooltip.get("found") if isinstance(tooltip, dict) else None
                    tooltip_area = found.get("area") if found else None
                    self.tooltip_rect = QRect(tooltip_area["x"], tooltip_area["y"], tooltip_area["width"], tooltip_area["height"]) if tooltip_area else None
                    if self.tooltip_rect and self.image_sequence == self.submitted_sequence:
                        source = self.image.copy(self.crop) if self.crop else self.image
                        self.tooltip_fingerprint = self.fingerprint(source, self.tooltip_rect)
                    else:
                        self.tooltip_fingerprint = None
                    self.latest_latency_ms = time.monotonic() * 1000 - result["atMs"]
                    self.timings.append({"capture_to_read_ms": round(self.latest_latency_ms, 1),
                                         "ocr_ms": round(result.get("ocrMs", 0), 1),
                                         "rows": len((result.get("shop") or {}).get("rows", []))})
                    result["pointerAtRead"] = list(self.last_pointer) if self.last_pointer is not None else None
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
        self.paused=True
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
