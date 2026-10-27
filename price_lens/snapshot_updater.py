"""Launch/hourly refresh scheduling independent of visible item requests."""
import time
import sqlite3

from PySide6.QtCore import QObject, QTimer, Signal

from .domain import age_text
from .snapshot_browser import BrowserSnapshot


class SnapshotUpdater(QObject):
    updated = Signal()
    changed = Signal()

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.enabled = False
        self.closed = False
        self.busy = False
        self.failures = 0
        self.error = ""
        self.browser = BrowserSnapshot(store.cache.path.parent / "market-browser", self)
        self.browser.ready.connect(self.accept)
        self.browser.failed.connect(self.failed)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.refresh)

    def set_enabled(self, enabled):
        if self.closed or self.enabled == enabled:
            return
        self.enabled = enabled
        if enabled:
            # Always refresh once on launch/enable, even with a recent snapshot.
            self.timer.start(0)
        else:
            self.timer.stop()
            self.browser.stop()
            self.busy = False
        self.changed.emit()

    def refresh(self):
        if self.closed or not self.enabled or self.busy:
            return
        self.timer.stop()
        self.busy = True
        self.error = ""
        self.changed.emit()
        self.browser.start()

    def accept(self, document):
        if self.closed or not self.enabled:
            return
        try:
            self.store.save(document)
        except (ValueError, TypeError, OSError, sqlite3.Error) as error:
            self.failed(f"Market snapshot could not be saved: {error}")
            return
        self.busy = False
        self.failures = 0
        self.error = ""
        # Published lists can already be several minutes old when checked. Do
        # not leave a freshness gap before the nominal hourly update. An already
        # old publication still waits an hour, rather than spinning a browser.
        remaining = self.store.meta["published_at"] + 3600 - time.time() - 20
        delay = remaining if 300 <= remaining < 3600 else 3600
        self.timer.start(int(delay * 1000))
        self.updated.emit()
        self.changed.emit()

    def failed(self, message):
        if self.closed or not self.enabled:
            return
        self.busy = False
        self.error = message
        self.failures += 1
        self.timer.start((300, 900, 3600)[min(self.failures-1, 2)] * 1000)
        self.changed.emit()

    def summary(self):
        if self.busy:
            return "Updating the full market in the background…"
        if self.error:
            return self.error
        if self.store.meta:
            meta = self.store.meta
            return f"{meta['priced']:,} market prices cached · checked {age_text(time.time()-meta['checked_at'])} ago"
        return ""

    def close(self):
        self.closed = True
        self.timer.stop()
        self.browser.close()
