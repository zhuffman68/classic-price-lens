"""One reusable OS sharing session, with bounded local-only frame delivery."""
import json
import os
from pathlib import Path
import struct
import sys
import time

from PySide6.QtCore import QObject, QLockFile, QProcess, QRect, QStandardPaths, QTimer, Signal
from PySide6.QtGui import QImage
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from .platform_paths import capture_socket_name, capture_lock_path


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
        self.launched = False
        self.retry_timer = QTimer(self)
        self.retry_timer.setInterval(100)
        self.retry_timer.timeout.connect(self.connect)
        self.launcher = QProcess(self)

    def start(self, screen, desktop):
        self.subscription = {"screen": list(screen.getRect()), "desktop": list(desktop.getRect())}
        self.active = True
        if self.socket.state() == QLocalSocket.LocalSocketState.ConnectedState:
            self.connected()
            return
        self.launched = False
        self.connect()
        self.retry_timer.start()

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
            self.launcher.setArguments(["-m", "price_lens.stream"])
            self.launcher.setWorkingDirectory(str(self.root))
            log_dir = self.root / "evidence"
            log_dir.mkdir(exist_ok=True)
            self.launcher.setStandardOutputFile(str(log_dir / "stream.log"))
            self.launcher.setStandardErrorFile(str(log_dir / "stream.log"))
            self.launcher.startDetached()

    def connected(self):
        self.retry_timer.stop()
        self.header_size = None
        self.metadata = None
        self.next_delivery = 0.0
        self.socket.write((json.dumps(self.subscription) + "\n").encode())
        self.status.emit("OS sharing session connected • full workspace is supported")

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
            image = QImage(pixels, self.metadata["width"], self.metadata["height"], QImage.Format.Format_RGBA8888).copy()
            captured_at = self.metadata["captured_at"]
            self.header_size = self.metadata = None
            self.socket.setReadBufferSize(65536)
            self.next_delivery = time.monotonic() + self.delivery_interval
            if self.active:
                self.frame.emit(image, captured_at)

    def stop(self, keep_session=False):
        self.active = False
        self.retry_timer.stop()
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
        socket.readyRead.connect(lambda: self.command(socket))
        socket.disconnected.connect(lambda: self.disconnect(socket))

    def command(self, socket):
        while socket.canReadLine():
            data = json.loads(bytes(socket.readLine()))
            if data.get("stop"):
                self.capture.stop()
                self.app.quit()
                return
            if "screen" in data and "desktop" in data:
                self.clients[socket] = (QRect(*data["screen"]), QRect(*data["desktop"]))
                if not self.capture.isActive():
                    # Set a valid OS screen before starting. The sharing portal
                    # still chooses the actual source and can return a workspace.
                    target = self.clients[socket][0]
                    screen = next((s for s in self.app.screens() if s.geometry() == target), self.app.primaryScreen())
                    self.capture.setScreen(screen)
                    self.capture.start()
                elif sys.platform != "linux":
                    target = self.clients[socket][0]
                    screen = next((s for s in self.app.screens() if s.geometry() == target), self.app.primaryScreen())
                    self.capture.setScreen(screen)

    def disconnect(self, socket):
        self.clients.pop(socket, None)
        socket.deleteLater()
        if not self.clients:
            # An intentional UI handoff can reconnect without another OS picker.
            self.idle.start()

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
        captured_at = time.monotonic()
        if captured_at - self.last_frame < 0.075 or not self.clients:
            return
        if all(socket.bytesToWrite() for socket in self.clients):
            return
        self.last_frame = captured_at
        image = frame.toImage()
        for socket, target in list(self.clients.items()):
            if not target or socket.bytesToWrite():
                continue
            # The Linux portal can return a whole workspace. Windows/macOS
            # native QScreenCapture already returns the selected monitor.
            selected = screen_pixels(image, *target) if sys.platform == "linux" else image
            image_region = selected.convertToFormat(QImage.Format.Format_RGBA8888)
            if image_region.isNull():
                continue
            metadata = {"width": image_region.width(), "height": image_region.height(), "captured_at": captured_at}
            self.send(socket, metadata, image_region.constBits())


def main():
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication(sys.argv[:1])
    app.setApplicationName("Classic Price Lens")
    app.setOrganizationName("LocalTools")
    app.setDesktopFileName("classic-price-lens")
    lock = QLockFile(capture_lock_path())
    if not lock.tryLock(0):
        return 0
    server = CaptureServer(app)
    result = app.exec()
    server.capture.stop()
    server.server.close()
    lock.unlock()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
