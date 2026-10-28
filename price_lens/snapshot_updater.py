"""Launch and selected-interval full-market refresh, independent of item views."""
import time
import sqlite3

from PySide6.QtCore import QObject, QTimer, Signal

from .domain import age_text
from .snapshot_fetcher import SnapshotFetcher


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
        self.startup_pending = False
        self.interval = 900
        self.fetcher = SnapshotFetcher(store.cache.path.parent / "market-webview", self)
        self.fetcher.ready.connect(self.accept)
        self.fetcher.failed.connect(self.failed)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.refresh)

    def set_enabled(self, enabled):
        if self.closed or self.enabled == enabled:
            return
        self.enabled = enabled
        if enabled:
            # Always refresh once on launch/enable, even with a recent snapshot.
            self.startup_pending = True
            self.timer.start(0)
        else:
            self.timer.stop()
            self.fetcher.stop()
            self.busy = False
        self.changed.emit()

    def refresh(self):
        if self.closed or not self.enabled or self.busy:
            return
        self.timer.stop()
        self.busy = True
        self.error = ""
        self.changed.emit()
        self.fetcher.start()

    def set_interval(self,seconds):
        self.interval=max(300,min(3600,int(seconds)))
        if self.enabled and not self.closed and not self.busy:
            checked=(self.store.meta or {}).get('checked_at',0)
            remaining=max(0,checked+self.interval-time.time())
            self.timer.start(round(remaining*1000))

    def accept(self, document):
        if self.closed or not self.enabled:
            return
        try:
            self.store.save(document)
        except (ValueError, TypeError, OSError, sqlite3.Error) as error:
            self.fetcher.record_failure('validation')
            self.failed(f"Market snapshot could not be saved: {error}", transient=False)
            return
        self.busy = False
        self.failures = 0
        self.error = ""
        self.startup_pending = False
        # Source publication age stays separate from the next fetch. An old
        # publication cannot trigger a browser loop or acquire a false new age.
        self.timer.start(self.interval*1000)
        self.updated.emit()
        self.changed.emit()

    def failed(self, message, transient=True):
        if self.closed or not self.enabled:
            return
        self.busy = False
        self.error = message
        self.failures += 1
        quick_retry = (self.startup_pending and self.failures == 1 and transient
                       and self.fetcher.failure_kind in ("timeout", "network", "source", "initialization"))
        self.startup_pending = False
        if quick_retry:
            self.error += " Retrying shortly…"
            self.failures = 0  # The single startup retry precedes normal backoff.
        self.timer.start((15 if quick_retry else (300, 900, 3600)[min(self.failures-1, 2)]) * 1000)
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
        self.fetcher.close()
