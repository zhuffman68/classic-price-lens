"""Activate or close our own app through user-only local IPC, without OS hooks."""
from PySide6.QtCore import QObject, QLockFile, QTimer, Signal, Slot
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from shiboken6 import isValid

from .platform_paths import cache_directory, control_socket_name


def request(command, name=None, timeout=3000):
    socket = QLocalSocket()
    socket.connectToServer(name or control_socket_name())
    if not socket.waitForConnected(timeout):
        if socket.error() in (QLocalSocket.LocalSocketError.ServerNotFoundError,
                              QLocalSocket.LocalSocketError.ConnectionRefusedError):
            return None
        return False
    socket.write(command.encode("ascii") + b"\n")
    socket.flush()
    if not socket.waitForReadyRead(timeout):
        return False
    accepted = bytes(socket.readLine()) == b"ok\n"
    if accepted and command == "quit" and socket.state() != QLocalSocket.LocalSocketState.UnconnectedState:
        # Upgrade/uninstall may replace files only after the UI has shut down.
        accepted = socket.waitForDisconnected(timeout)
    socket.abort()
    return accepted


class AppControl(QObject):
    activate = Signal()
    quit = Signal()
    toggle = Signal()
    minimize = Signal()

    def __init__(self, parent=None, name=None, lock_path=None):
        super().__init__(parent)
        self.name = name or control_socket_name()
        self.lock = QLockFile(str(lock_path or cache_directory() / "app.lock"))
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self.accept)
        self.connections = {}

    def start(self):
        if not self.lock.tryLock(0):
            return False
        QLocalServer.removeServer(self.name)
        if not self.server.listen(self.name):
            self.lock.unlock()
            raise RuntimeError("Cannot open application control socket: " + self.server.errorString())
        return True

    def accept(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            self.connections[socket] = b""
            socket.readyRead.connect(self.incoming)
            socket.disconnected.connect(self.disconnected)
            self.receive(socket)

    @Slot()
    def incoming(self):
        socket = self.sender()
        if socket in self.connections and isValid(socket):
            self.receive(socket)

    @Slot()
    def disconnected(self):
        socket = self.sender()
        if socket is not None:
            self.discard(socket)

    def receive(self, socket):
        data = self.connections.get(socket, b"") + bytes(socket.readAll())
        if len(data) > 32:
            socket.abort()
            return
        self.connections[socket] = data
        if b"\n" not in data:
            return
        command = data.split(b"\n", 1)[0]
        if command not in (b"activate", b"quit", b"toggle", b"minimize"):
            socket.write(b"error\n")
            socket.disconnectFromServer()
            return
        socket.write(b"ok\n")
        socket.flush()
        if command == b"quit":
            # Keep the client connected until aboutToQuit closes this server.
            QTimer.singleShot(0, self.quit.emit)
        else:
            action = {b"activate": self.activate, b"toggle": self.toggle, b"minimize": self.minimize}[command]
            QTimer.singleShot(0, action.emit)
            socket.disconnectFromServer()

    def discard(self, socket):
        self.connections.pop(socket, None)
        if isValid(socket):
            socket.deleteLater()

    def close(self):
        for socket in list(self.connections):
            socket.disconnectFromServer()
        self.server.close()
        self.lock.unlock()
