"""Bounded IPC with a short-lived native system web view. No browser discovery."""
import json
from pathlib import Path
import re
import sys
import time

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from .platform_paths import market_binary

MAX_DOCUMENT = 8 * 1024 * 1024


class SnapshotFetcher(QObject):
    ready = Signal(object)
    failed = Signal(str)

    def __init__(self, profile, parent=None):
        super().__init__(parent)
        self.profile = Path(profile)
        self.root = Path(__file__).resolve().parent.parent
        self.active = False
        self.closed = False
        self.output = bytearray()
        self.stderr = b""
        self.failure_kind = ""
        self.last_failure = None
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.readyReadStandardError.connect(self.read_error)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.process_error)
        self.deadline = QTimer(self)
        self.deadline.setSingleShot(True)
        self.deadline.setInterval(25000)
        self.deadline.timeout.connect(lambda: self.fail("Full-market refresh timed out; saved prices are kept.", "timeout"))
        self.kill_timer = QTimer(self)
        self.kill_timer.setSingleShot(True)
        self.kill_timer.setInterval(800)
        self.kill_timer.timeout.connect(self.process.kill)
        self.delayed_start = QTimer(self)
        self.delayed_start.setSingleShot(True)
        self.delayed_start.setInterval(100)
        self.delayed_start.timeout.connect(self.start)

    def command(self):
        command = [str(market_binary(self.root)), "--profile", str(self.profile)]
        return command + (["--diagnostic"] if sys.platform == "win32" else [])

    def start(self):
        if self.closed or self.active:
            return
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.delayed_start.start()
            return
        self.kill_timer.stop()
        if sys.platform == "win32":
            try:
                self.profile.mkdir(parents=True, exist_ok=True)
            except OSError:
                self.record_failure('storage')
                self.failed.emit("The market updater could not prepare its data folder; saved prices are kept.")
                return
        self.output.clear()
        self.stderr = b""
        self.failure_kind = ""
        self.active = True
        command = self.command()
        self.process.setProgram(command[0])
        self.process.setArguments(command[1:])
        self.process.setWorkingDirectory(str(self.root))
        self.deadline.start()
        self.process.start()

    def read_output(self):
        chunk = bytes(self.process.readAllStandardOutput())
        if not self.active:
            return
        if len(self.output) + len(chunk) > MAX_DOCUMENT:
            self.fail("The market document was too large; saved prices are kept.")
            return
        self.output.extend(chunk)

    def read_error(self):
        self.stderr = (self.stderr + bytes(self.process.readAllStandardError()))[-16000:]

    def process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.kill_timer.stop()
            if self.active:
                self.fail("The market updater could not start. Reinstall Lupin; saved prices are kept.", "start")

    def record_failure(self, kind, code=None):
        # Retain only fixed helper stages/error codes, never page contents,
        # returned market data, paths, browser profiles or user text.
        stages = re.findall(r"Market helper: ([A-Za-z ]{1,40}) \((0x[0-9A-Fa-f]{8})\)",
                            self.stderr.decode("utf-8", errors="replace"))[-12:]
        self.failure_kind = kind
        self.last_failure = {"at": time.time(), "kind": kind, "exit_code": code,
                             "stages": stages}
        try:
            self.profile.parent.mkdir(parents=True, exist_ok=True)
            path = self.profile.parent / "market-last-error.json"
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.last_failure), encoding="utf-8")
            temporary.replace(path)
        except OSError:
            pass

    def finished(self, code, status):
        self.kill_timer.stop()
        self.read_error()
        self.read_output()
        if not self.active:
            return
        self.active = False
        self.deadline.stop()
        if code or status != QProcess.ExitStatus.NormalExit:
            kind = "source"
            if code == 10:
                kind = "runtime"
                message = "The market updater needs its Windows runtime. Run Lupin's installer once; saved prices are kept."
            elif code == 11:
                kind = "desktop"
                message = "The market updater needs a desktop connection; saved prices are kept."
            elif code == 20:
                kind = "timeout"
                message = "The market source took too long to respond; saved prices are kept."
            elif code == 22:
                kind = "network"
                message = "The market connection failed; saved prices are kept."
            elif code == 12:
                kind = "initialization"
                message = "The market reader could not finish initializing; saved prices are kept."
            elif code == 127:
                kind = "runtime"
                message = "The market updater needs a system component. Reinstall Lupin with your package manager; saved prices are kept."
            else:
                message = "The market source could not be loaded; saved prices are kept."
            self.record_failure(kind, code)
            self.failed.emit(message)
            return
        try:
            document = json.loads(self.output.decode("utf-8"))
            if not isinstance(document, dict):
                raise ValueError("Expected a market document")
        except (UnicodeError, ValueError, RecursionError):
            self.record_failure("document", code)
            self.failed.emit("The market returned an unreadable document; saved prices are kept.")
            return
        self.ready.emit(document)

    def fail(self, message, kind="output"):
        if not self.active:
            return
        self.record_failure(kind)
        self.stop()
        self.failed.emit(message)

    def stop(self):
        self.active = False
        self.deadline.stop()
        self.delayed_start.stop()
        self.output.clear()
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.terminate()
            self.kill_timer.start()

    def close(self):
        self.closed = True
        self.stop()
        if self.process.state() != QProcess.ProcessState.NotRunning and not self.process.waitForFinished(1000):
            self.process.kill()
            self.process.waitForFinished(1000)
