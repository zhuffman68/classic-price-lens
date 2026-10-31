"""Launch and selected-interval full-market refresh, independent of item views."""
import time
import sqlite3
from math import ceil

from PySide6.QtCore import QObject, QTimer, Signal, Qt

from .domain import MAX_SNAPSHOT_AGE, age_text
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
        self.retry_at = None
        self.stale_publication = None
        self.stale_checks = 0
        self.fetcher = SnapshotFetcher(store.cache.path.parent / "market-webview", self)
        self.fetcher.ready.connect(self.accept)
        self.fetcher.failed.connect(self.failed)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        # A coarse timer can fire before publication expiry and repeatedly
        # fetch the same still-valid document as that deadline approaches.
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
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
        self.retry_at = None
        self.busy = True
        self.error = ""
        self.changed.emit()
        self.fetcher.start()

    def set_interval(self,seconds):
        self.interval=max(300,min(3600,int(seconds)))
        if self.enabled and not self.closed and not self.busy:
            self.schedule()

    def schedule(self):
        now = time.time()
        if self.startup_pending:
            deadline = now
        elif self.retry_at is not None:
            deadline = self.retry_at
        else:
            meta = self.store.meta or {}
            deadline = meta.get('checked_at', 0) + self.interval
            published = meta.get('published_at')
            if published is not None:
                deadline = min(deadline, published + MAX_SNAPSHOT_AGE)
        self.timer.start(max(0, ceil((deadline-now)*1000)))

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
        published = self.store.meta['published_at']
        now = time.time()
        if now >= published + MAX_SNAPSHOT_AGE:
            # The source may publish just after expiry. Retry soon, then back
            # off independently of transport failures; never refresh its age.
            self.stale_checks = self.stale_checks + 1 if published == self.stale_publication else 1
            self.stale_publication = published
            delay = min(self.interval, (60, 300, 900)[min(self.stale_checks-1, 2)])
            self.retry_at = now + delay
        else:
            self.stale_publication = None
            self.stale_checks = 0
            self.retry_at = None
        self.schedule()
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
        self.retry_at = time.time() + (15 if quick_retry else (300, 900, 3600)[min(self.failures-1, 2)])
        self.schedule()
        self.changed.emit()

    def summary(self):
        if self.busy:
            return "Updating the full market in the background…"
        if self.error:
            return self.error
        if self.store.meta:
            meta = self.store.meta
            now = time.time()
            summary = f"{meta['priced']:,} market prices cached · checked {age_text(now-meta['checked_at'])} ago"
            if now >= meta['published_at'] + MAX_SNAPSHOT_AGE:
                summary += " · source snapshot old"
            return summary
        return ""

    def close(self):
        self.closed = True
        self.timer.stop()
        self.fetcher.close()
