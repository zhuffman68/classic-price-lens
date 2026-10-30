"""Our independent annotation helper, with versioned startup and bounded recovery."""
import json
import os
from pathlib import Path
import sys
import time

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

from . import __version__
from .desktop_environment import recovered_environment
from .platform_paths import cache_directory
from .updates import atomic_json


class Overlay(QObject):
    pointer = Signal(int, int)
    writer_event = Signal(dict)
    writer_lost = Signal()
    status = Signal(str)

    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.root = Path(root)
        self.process = QProcess(self)
        self.buffer = b''
        self.last_state = None
        self.writer_state = None
        self.last_error = ''
        self.layout_boxes = []
        self.ready = False
        self.closed = False
        self.retries = 0
        self.loss_handled = False
        self.failure_reason = ''
        self.retry_timer = QTimer(self)
        self.retry_timer.setSingleShot(True)
        self.retry_timer.timeout.connect(self.start)
        self.startup_timer = QTimer(self)
        self.startup_timer.setSingleShot(True)
        self.startup_timer.setInterval(4000)
        self.startup_timer.timeout.connect(self.startup_timed_out)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.readyReadStandardError.connect(self.read_error)
        self.process.started.connect(self.flush_state)
        self.process.finished.connect(self.writer_disconnected)
        self.process.errorOccurred.connect(self.process_error)
        self.process.setWorkingDirectory(str(self.root))
        self.start()

    def start(self):
        if self.closed or self.process.state() != QProcess.ProcessState.NotRunning:
            return
        self.ready = False
        self.loss_handled = False
        self.failure_reason = ''
        self.buffer = b''
        self.last_error = ''
        environment = QProcessEnvironment.systemEnvironment()
        for key, value in recovered_environment().items():
            environment.insert(key, value)
        # Position only our independent canvas through XWayland. No game
        # window handles, parenting, hooks or input synthesis are involved.
        if (sys.platform.startswith('linux') and os.environ.get('WAYLAND_DISPLAY')
                and os.environ.get('DISPLAY') and os.environ.get('QT_QPA_PLATFORM') != 'offscreen'):
            environment.insert('QT_QPA_PLATFORM', 'xcb')
        self.process.setProcessEnvironment(environment)
        self.startup_timer.start()
        self.process.start(sys.executable, ['-B', '-m', 'price_lens.annotations'])

    def read_error(self):
        self.last_error = (self.last_error + bytes(self.process.readAllStandardError()).decode(errors='replace'))[-3000:]

    def record_failure(self, reason, code=None):
        # No stderr, captured text, draft or personal path is persisted.
        try:
            atomic_json(cache_directory() / 'overlay-startup.json', dict(
                at=time.time(), version=__version__, reason=reason,
                exit_code=code, retries=self.retries,
            ))
        except OSError:
            pass

    def process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.failure_reason = 'start-failed'
            self.writer_disconnected()

    def startup_timed_out(self):
        if self.closed or self.ready:
            return
        self.failure_reason = 'startup-timeout'
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()
        else:
            self.writer_disconnected()

    def writer_disconnected(self, code=None, *_):
        if self.loss_handled:
            return
        self.loss_handled = True
        self.ready = False
        self.layout_boxes = []
        self.writer_state = None
        self.startup_timer.stop()
        self.writer_lost.emit()
        if self.closed:
            return
        self.read_error()
        reason = self.failure_reason or ('display-authentication' if 'Authorization required' in self.last_error else 'unexpected-exit')
        self.record_failure(reason, code if type(code) is int else None)
        if self.retries < 2:
            self.retry_timer.start(500 * 2 ** self.retries)
            self.retries += 1
            self.status.emit('Restoring overlay labels…')
        else:
            self.status.emit('Overlay labels could not start. Retry overlays or restart Lupin from the application launcher.')

    def retry(self):
        if self.closed or self.process.state() != QProcess.ProcessState.NotRunning:
            return
        self.retry_timer.stop()
        self.retries = 0
        self.status.emit('Restoring overlay labels…')
        self.start()

    def flush_state(self):
        if self.last_state is not None and self.process.state() == QProcess.ProcessState.Running:
            self.process.write((json.dumps(self.last_state) + '\n').encode())
        if self.writer_state is not None and self.writer_available:
            if self.writer_state.get('operation') == 'open':
                self.allow_writer_foreground()
            self.process.write((json.dumps({'writer': self.writer_state}, ensure_ascii=False) + '\n').encode('utf-8'))

    def allow_writer_foreground(self):
        if sys.platform == 'win32' and self.process.processId():
            import ctypes
            try:
                ctypes.windll.user32.AllowSetForegroundWindow(int(self.process.processId()))
            except (AttributeError, OSError):
                pass

    @property
    def writer_available(self):
        return self.ready and self.process.state() == QProcess.ProcessState.Running

    @property
    def recovering(self):
        return not self.closed and not self.ready and (self.retry_timer.isActive() or self.startup_timer.isActive())

    def update_writer(self, state):
        self.writer_state = state
        if self.writer_available:
            if state.get('operation') == 'open':
                self.allow_writer_foreground()
            self.process.write((json.dumps({'writer': state}, ensure_ascii=False) + '\n').encode('utf-8'))

    def read_output(self):
        self.buffer += bytes(self.process.readAllStandardOutput())
        if len(self.buffer) > 131072:
            self.buffer = b''
            return
        while b'\n' in self.buffer:
            line, self.buffer = self.buffer.split(b'\n', 1)
            try:
                report = json.loads(line)
                if not isinstance(report, dict):
                    continue
                if report.get('ready') is True:
                    if report.get('version') != __version__:
                        self.failure_reason = 'version-mismatch'
                        self.process.kill()
                        return
                    self.ready = True
                    self.startup_timer.stop()
                    self.status.emit('')
                if isinstance(report.get('writer'), dict):
                    self.writer_event.emit(report['writer'])
                if isinstance(report.get('layout'), list):
                    self.layout_boxes = report['layout'][:48]
                point = report.get('pointer')
                if (isinstance(point, list) and len(point) == 2
                        and all(type(value) is int for value in point)):
                    self.pointer.emit(*point)
            except (ValueError, TypeError):
                pass

    def update(self, geometry, rows, hover_enabled=False):
        self.last_state = dict(geometry=geometry, rows=rows, hover_enabled=hover_enabled,
                               reduce_motion=getattr(self, 'reduce_motion', False))
        if self.process.state() == QProcess.ProcessState.Running:
            self.process.write((json.dumps(self.last_state) + '\n').encode())

    def close(self):
        self.closed = True
        self.ready = False
        self.retry_timer.stop()
        self.startup_timer.stop()
        if self.process.state() == QProcess.ProcessState.NotRunning:
            return
        self.update([0, 0, 1, 1], [])
        self.process.closeWriteChannel()
        if not self.process.waitForFinished(1000):
            self.process.kill()
            self.process.waitForFinished(1000)
