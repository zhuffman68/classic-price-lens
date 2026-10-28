"""One reusable OS sharing session, with bounded local-only frame delivery."""
import json
import os
from pathlib import Path
import struct
import sys
import time

from PySide6.QtCore import QObject, QLockFile, QProcess, QRect, QStandardPaths, QTimer, Signal, Slot
from shiboken6 import isValid
from PySide6.QtGui import QImage
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from .platform_paths import cache_directory, capture_socket_name, capture_lock_path
from .capture_platform import uses_system_picker, screen_for_rectangle


def socket_name():
    return capture_socket_name()


def screen_pixels(image, screen, desktop):
    """A workspace is cropped to the selected monitor; a shared monitor passes through."""
    if image.isNull():
        return image
    workspace_ratio = desktop.width() / desktop.height()
    if abs(image.width() / image.height() - workspace_ratio) < 0.01:
        region = screen.translated(-desktop.x(), -desktop.y())
        sx, sy = image.width() / desktop.width(), image.height() / desktop.height()
        return image.copy(QRect(round(region.x() * sx), round(region.y() * sy),
                                round(region.width() * sx), round(region.height() * sy)))
    return image


class StreamClient(QObject):
    frame = Signal(QImage, float)
    status = Signal(str)

    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.root = Path(root)
        self.socket = QLocalSocket(self)
        self.socket.connected.connect(self.connected)
        self.socket.readyRead.connect(self.receive)
        self.socket.errorOccurred.connect(self.connection_error)
        self.socket.setReadBufferSize(65536)
        self.delivery_interval = 0.15
        self.next_delivery = 0.0
        self.delivery_timer = QTimer(self)
        self.delivery_timer.setSingleShot(True)
        self.delivery_timer.timeout.connect(self.receive)
        self.header_size = None
        self.metadata = None
        self.next_delivery = 0.0
        self.subscription = None
        self.active = False
        self.paused = False
        self.launched = False
        self.retry_timer = QTimer(self)
        self.retry_timer.setInterval(100)
        self.retry_timer.timeout.connect(self.connect)
        self.connect_timer = QTimer(self)
        self.connect_timer.setSingleShot(True)
        self.connect_timer.setInterval(10000)
        self.connect_timer.timeout.connect(self.connection_timed_out)
        self.launcher = QProcess(self)

    def start(self, screen, desktop):
        self.paused = False
        self.subscription = {"screen": list(screen.getRect()), "desktop": list(desktop.getRect()), "paused": False}
        self.active = True
        if self.socket.state() == QLocalSocket.LocalSocketState.ConnectedState:
            self.send_subscription()
            return
        self.launched = False
        self.retry_timer.start()
        self.connect_timer.start()
        self.connect()

    def connect(self):
        if not self.active:
            return
        state = self.socket.state()
        if state == QLocalSocket.LocalSocketState.ConnectedState:
            self.retry_timer.stop()
            return
        if state == QLocalSocket.LocalSocketState.ConnectingState:
            return
        self.socket.abort()
        self.socket.connectToServer(socket_name())

    def connection_error(self, error):
        if self.active and not self.launched:
            self.launched = True
            # A lock in the server prevents simultaneous launchers creating extra
            # sharing sessions. A running server is reused across a UI restart.
            self.launcher.setProgram(sys.executable)
            self.launcher.setArguments(["-B", "-m", "price_lens.stream"])
            self.launcher.setWorkingDirectory(str(self.root))
            log_dir = cache_directory()
            log_path = log_dir / "stream.log"
            # Bound persistent diagnostics; ordinary capture produces little output.
            if log_path.exists() and log_path.stat().st_size > 1024 * 1024:
                log_path.replace(log_dir / "stream.previous.log")
            self.launcher.setStandardOutputFile(str(log_path))
            self.launcher.setStandardErrorFile(str(log_path))
            result = self.launcher.startDetached()
            started = result[0] if isinstance(result, tuple) else result
            if not started:
                self.stop()
                self.status.emit("OS capture: The screen-sharing helper could not start. Open Connection details for diagnostics.")

    def connection_timed_out(self):
        if self.active and self.socket.state() != QLocalSocket.LocalSocketState.ConnectedState:
            self.stop()
            self.status.emit("OS capture: The screen-sharing helper did not connect. Open Connection details for diagnostics.")

    def connected(self):
        self.retry_timer.stop()
        self.connect_timer.stop()
        self.header_size = None
        self.metadata = None
        self.next_delivery = 0.0
        self.send_subscription()

    def send_subscription(self):
        self.socket.write((json.dumps(self.subscription) + "\n").encode())
        self.status.emit("OS sharing session connected • full workspace is supported"
                         if uses_system_picker() else "Display capture connected")

    def receive(self):
        while True:
            if self.header_size is None:
                delay = self.next_delivery - time.monotonic()
                if delay > 0:
                    if not self.delivery_timer.isActive():
                        self.delivery_timer.start(max(1, round(delay * 1000)))
                    return
                if self.socket.bytesAvailable() < 4:
                    return
                self.header_size = struct.unpack("!I", bytes(self.socket.read(4)))[0]
                if self.header_size > 4096:
                    self.status.emit("Invalid local capture header")
                    self.stop()
                    return
            if self.metadata is None:
                if self.socket.bytesAvailable() < self.header_size:
                    return
                self.metadata = json.loads(bytes(self.socket.read(self.header_size)))
                if self.metadata.get("error"):
                    self.status.emit(self.metadata["error"])
                    self.header_size = self.metadata = None
                    continue
                width, height = self.metadata["width"], self.metadata["height"]
                if not (0 < width <= 16384 and 0 < height <= 16384 and width * height <= 16_777_216):
                    self.status.emit("Capture dimensions exceed limit")
                    self.stop()
                    return
                self.socket.setReadBufferSize(width * height * 4 + 4096)
            size = self.metadata["width"] * self.metadata["height"] * 4
            if self.socket.bytesAvailable() < size:
                return
            pixels = bytes(self.socket.read(size))
            captured_at = self.metadata["captured_at"]
            wrong_monitor = self.metadata.get("screen") is not None and self.metadata["screen"] != self.subscription["screen"]
            image = None if self.paused or wrong_monitor else QImage(pixels, self.metadata["width"], self.metadata["height"], QImage.Format.Format_RGBA8888).copy()
            self.header_size = self.metadata = None
            self.socket.setReadBufferSize(65536)
            self.next_delivery = time.monotonic() + self.delivery_interval
            if self.active and not self.paused and not wrong_monitor:
                self.frame.emit(image, captured_at)

    def set_paused(self, paused):
        self.paused = paused
        if self.subscription is not None:
            self.subscription["paused"] = paused
        if self.socket.state() == QLocalSocket.LocalSocketState.ConnectedState:
            self.socket.write((json.dumps({"paused": paused}) + "\n").encode())

    def stop(self, keep_session=False):
        self.active = False
        self.retry_timer.stop()
        self.connect_timer.stop()
        self.delivery_timer.stop()
        self.launched = False
        if self.socket.state() == QLocalSocket.LocalSocketState.ConnectedState:
            if not keep_session:
                self.socket.write(b'{"stop":true}\n')
                self.socket.flush()
                self.socket.waitForBytesWritten(100)
            self.socket.disconnectFromServer()


class CaptureServer(QObject):
    def __init__(self, app):
        super().__init__(app)
        from PySide6.QtMultimedia import QMediaCaptureSession, QScreenCapture, QVideoSink
        self.app = app
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self.accept)
        self.clients = {}
        self.paused_clients = set()
        self.closing = False
        self.last_frame = 0.0
        self.session = QMediaCaptureSession(self)
        self.capture = QScreenCapture(self)
        if hasattr(self.capture, "setMaximumFrameRate"):
            self.capture.setMaximumFrameRate(10.0)
        self.sink = QVideoSink(self)
        self.session.setScreenCapture(self.capture)
        self.session.setVideoSink(self.sink)
        self.sink.videoFrameChanged.connect(self.on_frame)
        self.capture.errorOccurred.connect(self.error)
        self.idle = QTimer(self)
        self.idle.setSingleShot(True)
        self.idle.setInterval(60000)
        self.idle.timeout.connect(app.quit)
        QLocalServer.removeServer(socket_name())
        if not self.server.listen(socket_name()):
            raise RuntimeError(self.server.errorString())
        self.idle.start()

    def accept(self):
        socket = self.server.nextPendingConnection()
        self.clients[socket] = None
        self.idle.stop()
        socket.readyRead.connect(self.client_ready)
        socket.disconnected.connect(self.client_disconnected)

    @Slot()
    def client_ready(self):
        socket = self.sender()
        if not self.closing and socket in self.clients and isValid(socket):
            self.command(socket)

    @Slot()
    def client_disconnected(self):
        socket = self.sender()
        if not self.closing and socket in self.clients:
            self.disconnect(socket)

    def command(self, socket):
        while socket.canReadLine():
            data = json.loads(bytes(socket.readLine()))
            if data.get("stop"):
                self.capture.stop()
                self.app.quit()
                return
            if "paused" in data:
                if data["paused"]:
                    self.paused_clients.add(socket)
                else:
                    self.paused_clients.discard(socket)
                self.update_frame_rate()
            if "screen" in data and "desktop" in data:
                target = QRect(*data["screen"])
                screen = screen_for_rectangle(self.app.screens(), target)
                if screen is None:
                    self.clients[socket] = None
                    self.send(socket, {"error": "OS capture: The selected display is no longer available. Choose a connected display and start reading again."})
                    return
                self.clients[socket] = (target, QRect(*data["desktop"]))
                if not self.capture.isActive():
                    from PySide6.QtMultimedia import QScreenCapture
                    # Constructor errors happen before errorOccurred is wired.
                    if self.capture.error() != QScreenCapture.Error.NoError:
                        self.send(socket, {"error": "OS capture: " + self.capture.errorString()})
                        return
                    # Set a valid OS screen before starting. The sharing portal
                    # still chooses the actual source and can return a workspace.
                    self.capture.setScreen(screen)
                    self.capture.start()
                elif sys.platform != "linux":
                    self.capture.setScreen(screen)

    def disconnect(self, socket):
        self.clients.pop(socket, None)
        self.paused_clients.discard(socket)
        self.update_frame_rate()
        if isValid(socket):
            socket.deleteLater()
        if not self.clients:
            # An intentional UI handoff can reconnect without another OS picker.
            self.idle.start()

    def update_frame_rate(self):
        if self.closing:
            return
        if hasattr(self.capture, "setMaximumFrameRate"):
            paused = bool(self.clients) and all(socket in self.paused_clients for socket in self.clients)
            self.capture.setMaximumFrameRate(1.0 if paused else 10.0)

    @staticmethod
    def send(socket, metadata, pixels=None):
        # PySide advertises a memoryview overload, but Qt 6.11 rejects QImage's
        # constBits view. Materialize bytes before writing any part of the packet.
        payload = bytes(pixels) if pixels is not None else None
        encoded = json.dumps(metadata, separators=(",", ":")).encode()
        socket.write(struct.pack("!I", len(encoded)))
        socket.write(encoded)
        if payload is not None:
            socket.write(payload)

    def error(self, error, description):
        for socket in self.clients:
            self.send(socket, {"error": "OS capture: " + description})

    def on_frame(self, frame):
        if self.closing:
            return
        captured_at = time.monotonic()
        if captured_at - self.last_frame < 0.075 or not self.clients or all(s in self.paused_clients for s in self.clients):
            return
        if all(socket.bytesToWrite() for socket in self.clients):
            return
        self.last_frame = captured_at
        image = frame.toImage()
        for socket, target in list(self.clients.items()):
            if not target or socket.bytesToWrite() or socket in self.paused_clients:
                continue
            # The Linux portal can return a whole workspace. Windows/macOS
            # native QScreenCapture already returns the selected monitor.
            selected = screen_pixels(image, *target) if sys.platform == "linux" else image
            image_region = selected.convertToFormat(QImage.Format.Format_RGBA8888)
            if image_region.isNull():
                continue
            metadata = {"width": image_region.width(), "height": image_region.height(), "captured_at": captured_at,
                        "screen": list(target[0].getRect())}
            self.send(socket, metadata, image_region.constBits())

    def close(self):
        if self.closing:
            return
        self.closing = True
        self.idle.stop()
        self.server.close()
        for socket in list(self.clients):
            if isValid(socket):
                socket.readyRead.disconnect(self.client_ready)
                socket.disconnected.disconnect(self.client_disconnected)
                socket.abort()
                socket.deleteLater()
        self.clients.clear()
        self.paused_clients.clear()
        capture = self.session.screenCapture()
        if capture is not None:
            capture.stop()
        self.session.setScreenCapture(None)
        self.session.setVideoSink(None)


def main():
    from . import APP_NAME, LEGACY_APP_NAME
    from .qt_runtime import configure_qt
    configure_qt()
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication(sys.argv[:1])
    app.setApplicationName(LEGACY_APP_NAME)
    app.setOrganizationName("LocalTools")
    app.setApplicationDisplayName(APP_NAME)
    app.setDesktopFileName("io.github.zhuffman68.ClassicPriceLens")
    lock = QLockFile(capture_lock_path())
    if not lock.tryLock(0):
        return 0
    server = CaptureServer(app)
    result = app.exec()
    server.close()
    lock.unlock()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
