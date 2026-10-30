"""Launches only our own annotation process; no game window ownership or attachment."""
import json
import os
import sys

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Signal


class Overlay(QObject):
    pointer = Signal(int, int)
    writer_event = Signal(dict)
    writer_lost = Signal()
    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.process = QProcess(self)
        self.buffer = b""
        self.last_state = None
        self.writer_state = None
        self.last_error = ""
        self.layout_boxes=[]
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.readyReadStandardError.connect(self.read_error)
        self.process.started.connect(self.flush_state)
        self.process.finished.connect(self.writer_disconnected)
        self.process.errorOccurred.connect(self.writer_disconnected)
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
        if self.writer_state is not None and self.process.state() == QProcess.ProcessState.Running:
            if self.writer_state.get('operation')=='open':self.allow_writer_foreground()
            self.process.write((json.dumps({'writer':self.writer_state},ensure_ascii=False)+'\n').encode('utf-8'))

    def writer_disconnected(self,*_):
        self.writer_state=None
        self.writer_lost.emit()

    def allow_writer_foreground(self):
        if sys.platform=='win32' and self.process.processId():
            # Delegate our shortcut activation privilege only to our own helper.
            # No foreign HWND/PID lookup or keyboard synthesis is involved.
            import ctypes
            try:ctypes.windll.user32.AllowSetForegroundWindow(int(self.process.processId()))
            except (AttributeError,OSError):pass

    @property
    def writer_available(self):
        # Until startup is confirmed, use the ordinary native writer. This
        # avoids queuing a surface whose close could precede its first opening.
        return self.process.state() == QProcess.ProcessState.Running

    def update_writer(self,state):
        self.writer_state=state
        if self.process.state() == QProcess.ProcessState.Running:
            if state.get('operation')=='open':self.allow_writer_foreground()
            self.process.write((json.dumps({'writer':state},ensure_ascii=False)+'\n').encode('utf-8'))

    def read_output(self):
        self.buffer += bytes(self.process.readAllStandardOutput())
        if len(self.buffer)>131072:
            self.buffer=b''
            return
        while b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            try:
                report=json.loads(line)
                if not isinstance(report,dict):continue
                if isinstance(report.get('writer'),dict):self.writer_event.emit(report['writer'])
                if 'layout' in report:self.layout_boxes=report['layout'][:48]
                point = report.get("pointer")
                if point:
                    self.pointer.emit(*point)
            except (ValueError, TypeError):
                pass

    def update(self, geometry, rows, hover_enabled=False):
        self.last_state = {"geometry": geometry, "rows": rows, "hover_enabled": hover_enabled,
                           "reduce_motion":getattr(self,"reduce_motion",False)}
        # Do not replay an 'open' writer command with every annotation frame.
        if self.process.state() == QProcess.ProcessState.Running:
            self.process.write((json.dumps(self.last_state) + "\n").encode())

    def close(self):
        if self.process.state() == QProcess.ProcessState.NotRunning:
            return
        self.update([0, 0, 1, 1], [])
        self.process.closeWriteChannel()
        if not self.process.waitForFinished(1000):
            self.process.kill()
            self.process.waitForFinished(1000)
