"""Short-lived, independent headless browser for the public market page.

Uses a dedicated local profile and an ephemeral loopback debugging endpoint.
Never opens, enumerates or communicates with a game window/process.
"""
import json
import os
from pathlib import Path
import re
import shutil
import sys

from PySide6.QtCore import QObject, QProcess, QTimer, QUrl, Signal
from PySide6.QtWebSockets import QWebSocket


def find_browser():
    names = ("msedge", "chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "microsoft-edge")
    candidates = [Path(found) for name in names if (found := shutil.which(name))]
    if sys.platform == "win32":
        for location in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            if root := os.environ.get(location):
                candidates.extend(Path(root) / suffix for suffix in
                                  ("Microsoft/Edge/Application/msedge.exe", "Google/Chrome/Application/chrome.exe"))
    elif sys.platform == "darwin":
        candidates.extend(Path(path) for path in
                          ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                           "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"))
    else:
        # Reuse a pre-existing compatible browser; never download one silently.
        candidates.extend(sorted((Path.home()/".cache/ms-playwright").glob("chromium-*/chrome-linux64/chrome"), reverse=True))
    return next((path for path in candidates if path.is_file()), None)


class BrowserSnapshot(QObject):
    ready = Signal(object)
    failed = Signal(str)

    def __init__(self, profile, parent=None):
        super().__init__(parent)
        self.profile = Path(profile)
        self.process = None
        self.socket = None
        self.pending = {}
        self.sequence = 0
        self.session = None
        self.active = False
        self.stderr = b""
        self.deadline = QTimer(self)
        self.deadline.setSingleShot(True)
        self.deadline.timeout.connect(lambda: self.fail("Full-market refresh timed out; saved prices are kept."))
        self.poll = QTimer(self)
        self.poll.setSingleShot(True)
        self.poll.timeout.connect(self.read_page)
        self.delayed_start = QTimer(self)
        self.delayed_start.setSingleShot(True)
        self.delayed_start.timeout.connect(self.start)

    def start(self):
        if self.active:
            return
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            self.delayed_start.start(800)
            return
        if self.process:
            self.process.deleteLater()
            self.process = None
        browser = find_browser()
        if not browser:
            self.failed.emit("Full-market refresh needs Chrome, Edge or Chromium. Per-item prices remain available.")
            return
        self.profile.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.active = True
        self.stderr = b""
        self.session = None
        self.pending.clear()
        self.process = QProcess(self)
        process = self.process
        process.readyReadStandardError.connect(lambda: self.read_error(process) if self.process is process else process.readAllStandardError())
        process.readyReadStandardOutput.connect(lambda: process.readAllStandardOutput())
        process.finished.connect(lambda *_: self.fail("The market browser closed before prices were ready.") if self.active and self.process is process else None)
        process.errorOccurred.connect(lambda *_: self.fail("The market browser could not start; saved prices are kept.") if self.active and self.process is process else None)
        process.stop_timer = QTimer(process)
        process.stop_timer.setSingleShot(True)
        process.stop_timer.timeout.connect(process.kill)
        process.finished.connect(process.stop_timer.stop)
        arguments = ["--headless=new", "--no-startup-window", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
                     "--disable-extensions", "--disable-background-networking", "--disable-component-update",
                     "--disable-sync", "--remote-debugging-address=127.0.0.1", "--remote-debugging-port=0",
                     "--user-data-dir=" + str(self.profile)]
        self.deadline.start(25000)
        process.start(str(browser), arguments)

    def read_error(self, process):
        self.stderr = (self.stderr + bytes(process.readAllStandardError()))[-16000:]
        if self.socket or not self.active:
            return
        match = re.search(rb"DevTools listening on (ws://127\.0\.0\.1:\d+/devtools/browser/[\w-]+)", self.stderr)
        if match:
            self.socket = QWebSocket(parent=self)
            self.socket.setMaxAllowedIncomingMessageSize(8 * 1024 * 1024)
            self.socket.connected.connect(lambda: self.call("Target.createTarget", {"url": "about:blank"}, self.created))
            self.socket.textMessageReceived.connect(self.message)
            self.socket.errorOccurred.connect(lambda *_: self.fail("Market browser connection unavailable; saved prices are kept.") if self.active else None)
            self.socket.open(QUrl(match[1].decode("ascii")))

    def call(self, method, params, callback=None, session=None):
        if not self.active or not self.socket:
            return
        self.sequence += 1
        message = {"id": self.sequence, "method": method, "params": params}
        if session:
            message["sessionId"] = session
        if callback:
            self.pending[self.sequence] = callback
        self.socket.sendTextMessage(json.dumps(message))

    def message(self, body):
        if not self.active:
            return
        try:
            response = json.loads(body)
            callback = self.pending.pop(response.get("id"), None)
            if callback:
                callback(response.get("result"), response.get("error"))
        except (ValueError, TypeError, KeyError):
            self.fail("The market page returned an unexpected response; saved prices are kept.")

    def created(self, result, error):
        if error or not result or not result.get("targetId"):
            self.fail("The market browser could not open its page.")
            return
        self.call("Target.attachToTarget", {"targetId": result["targetId"], "flatten": True}, self.attached)

    def attached(self, result, error):
        if error or not result or not result.get("sessionId"):
            self.fail("The market browser could not load its page.")
            return
        self.session = result["sessionId"]
        self.call("Page.navigate", {"url": "https://meso.watch/"}, self.navigated, self.session)

    def navigated(self, result, error):
        if error or (result or {}).get("errorText"):
            self.fail("The market page is unavailable; saved prices are kept.")
        else:
            self.poll.start(250)

    def read_page(self):
        # Read the same list the ordinary page has loaded. No challenge solving,
        # stealth scripts, login, per-item crawl or desktop browser inputs.
        self.call("Runtime.evaluate", {"expression": "window.MarketData?.doc || null", "returnByValue": True},
                  self.page_result, self.session)

    def page_result(self, result, error):
        value = (result or {}).get("result", {}).get("value")
        if isinstance(value, dict):
            self.stop()
            self.ready.emit(value)
        elif self.active:
            self.poll.start(350)

    def fail(self, message):
        if not self.active:
            return
        self.stop()
        self.failed.emit(message)

    def stop(self):
        self.delayed_start.stop()
        self.deadline.stop()
        self.poll.stop()
        process, socket = self.process, self.socket
        if self.active and socket:
            self.call("Browser.close", {})
        self.active = False
        self.pending.clear()
        self.socket = None
        if socket:
            socket.close()
            socket.deleteLater()
        # Close only the subprocess we created. No global process lookup/kill.
        if process:
            if process.state() != QProcess.ProcessState.NotRunning:
                process.stop_timer.start(700)

    def close(self):
        self.stop()
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.terminate()
            if not self.process.waitForFinished(1000):
                self.process.kill()
                self.process.waitForFinished(500)
