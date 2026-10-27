"""Launches only our own annotation process; no game window ownership or attachment."""
import json
import os
import sys

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Signal


class Overlay(QObject):
    pointer = Signal(int, int)
    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.process = QProcess(self)
        self.buffer = b""
        self.last_state = None
        self.last_error = ""
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.readyReadStandardError.connect(self.read_error)
        self.process.started.connect(self.flush_state)
        environment = QProcessEnvironment.systemEnvironment()
        # Wayland does not let an ordinary client position a window globally.
        # XWayland lets our independent transparent window use desktop coordinates.
        if (sys.platform.startswith("linux") and os.environ.get("WAYLAND_DISPLAY") and os.environ.get("DISPLAY")
                and os.environ.get("QT_QPA_PLATFORM") != "offscreen"):
            environment.insert("QT_QPA_PLATFORM", "xcb")
        self.process.setProcessEnvironment(environment)
        self.process.setWorkingDirectory(str(root))
        self.process.start(sys.executable, ["-B", "-m", "price_lens.annotations"])

    def read_error(self):
        self.last_error = (self.last_error + bytes(self.process.readAllStandardError()).decode(errors="replace"))[-3000:]

    def flush_state(self):
        if self.last_state is not None and self.process.state() == QProcess.ProcessState.Running:
            self.process.write((json.dumps(self.last_state) + "\n").encode())

    def read_output(self):
        self.buffer += bytes(self.process.readAllStandardOutput())
        while b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            try:
                point = json.loads(line).get("pointer")
                if point:
                    self.pointer.emit(*point)
            except (ValueError, TypeError):
                pass

    def update(self, geometry, rows, hover_enabled=False):
        self.last_state = {"geometry": geometry, "rows": rows, "hover_enabled": hover_enabled,
                           "reduce_motion":getattr(self,"reduce_motion",False)}
        self.flush_state()

    def close(self):
        if self.process.state() == QProcess.ProcessState.NotRunning:
            return
        self.update([0, 0, 1, 1], [])
        self.process.closeWriteChannel()
        if not self.process.waitForFinished(1000):
            self.process.kill()
            self.process.waitForFinished(1000)
