"""Visible-item HTTP scheduling, bounded concurrency and shared cached results."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import time

from PySide6.QtCore import QObject, Qt, Signal, Slot

from .data import Cache, MeowProvider, load_catalog


@dataclass
class _Lookup:
    key: tuple
    function: object
    arguments: tuple
    priority: int
    sequence: int
    ttl: int = 900
    early: bool = False


class PriceService(QObject):
    catalog_ready = Signal(object)
    quote_ready = Signal(int, object)
    error = Signal(int, str)
    identity_ready = Signal(object, object)
    state_changed = Signal()
    _completed = Signal(object, object)

    MAX_WORKERS = 3
    MAX_QUEUED = 64

    def __init__(self, cache_path, parent=None):
        super().__init__(parent)
        self.cache = Cache(cache_path)
        self.provider = MeowProvider(self.cache)
        self.pool = ThreadPoolExecutor(max_workers=self.MAX_WORKERS, thread_name_prefix="classic-prices")
        self.pending = set()
        self.retry_at = {}
        self.delivered = {}
        self.loaded = set()
        self.closed = False
        self.identity_pending = set()
        self.identity_retry = {}
        self.catalog_pending = False
        self._queued = {}
        self._active = {}
        self._sequence = 0
        self._batching = 0
        self._dirty = False
        # Workers never change scheduler/UI state. Even instant completions are
        # delivered on this object's Qt thread, after the current batch ends.
        self._completed.connect(self._finish, Qt.ConnectionType.QueuedConnection)

    def start(self):
        if self.closed or self.catalog_pending:
            return
        self._enqueue(("catalog", None), load_catalog, (self.cache,), -10)
        self._pump()

    @staticmethod
    def refresh_lead(item_id, ttl):
        """Spread early refreshes over 7.5-30 seconds, depending on the TTL."""
        window = min(30.0, ttl * 0.05)
        return window * (0.5 + (item_id * 2654435761 % 1000) / 2000)

    def observe(self, items, ttl, *, hovered_id=None, identities=(), hovered_identity=None):
        """Replace the visible demand; abandon only queued, unseen requests."""
        if self.closed:
            return
        items = {item.game_id: item for item in items}
        identities = {identity: candidates for identity, candidates in identities}
        visible = {("quote", item_id) for item_id in items}
        visible.update(("identity", identity) for identity in identities)
        self._batching += 1
        try:
            for key in list(self._queued):
                if key[0] != "catalog" and key not in visible:
                    self._cancel(key)
            # Stage the whole view before starting anything, so the hovered
            # item can take the next free slot even in a newly opened shop.
            for item in items.values():
                self.request(item, ttl, priority=0 if item.game_id == hovered_id else 10, early=True)
            for identity, candidates in identities.items():
                self.resolve_identity(identity, candidates, ttl,
                                      priority=0 if identity == hovered_identity else 10)
        finally:
            self._batching -= 1
        self._pump()

    def clear_visible(self):
        self.observe([], 900)

    def request(self, item, ttl, *, priority=10, early=False):
        if self.closed:
            return
        key = ("quote", item.game_id)
        quote = self.delivered.get(item.game_id)
        if item.game_id not in self.loaded:
            quote = self.cache.quote(item.game_id)
            self.loaded.add(item.game_id)
        now = time.time()
        if quote:
            if self.delivered.get(item.game_id) != quote:
                self.delivered[item.game_id] = quote
                self.quote_ready.emit(item.game_id, quote)
            if quote.cache_valid(now, ttl):
                eligible = (early and quote.price is not None and quote.sample_count >= 5
                            and not quote.uncertain and quote.fresh(now, ttl))
                if not eligible or now < quote.fetched_at + ttl - self.refresh_lead(item.game_id, ttl):
                    self._cancel(key)
                    self._pump()
                    return
                priority += 20  # A still-valid price never jumps ahead of a missing/expired one.
            else:
                early = False
        else:
            early = False
        if key in self._active or now < self.retry_at.get(item.game_id, 0):
            return
        self._enqueue(key, self.provider.fetch, (item,), priority, ttl, early)
        self._pump()

    def state_for(self, item_id):
        key = ("quote", item_id)
        if key in self._active:
            return "refreshing"
        if key in self._queued:
            return "queued"
        if time.time() < self.retry_at.get(item_id, 0):
            return "retry"
        return ""

    def invalidate(self):
        self.loaded.clear()
        self.delivered.clear()

    def resolve_identity(self, identity, candidates, ttl=900, *, priority=10):
        if self.closed or time.monotonic() < self.identity_retry.get(identity, 0):
            return
        self._enqueue(("identity", identity), self.provider.resolve_name,
                      (identity[0], candidates), priority, ttl)
        self._pump()

    def _enqueue(self, key, function, arguments, priority, ttl=900, early=False):
        if key in self._active:
            return
        if key in self._queued:
            job = self._queued[key]
            job.priority, job.ttl, job.early = priority, ttl, early
            return
        if len(self._queued) >= self.MAX_QUEUED:
            worst = max(self._queued.values(), key=lambda job: (job.priority, job.sequence))
            if priority >= worst.priority:
                return
            self._cancel(worst.key)
        self._sequence += 1
        self._queued[key] = _Lookup(key, function, arguments, priority, self._sequence, ttl, early)
        kind, identity = key
        if kind == "quote":
            self.pending.add(identity)
        elif kind == "identity":
            self.identity_pending.add(identity)
        else:
            self.catalog_pending = True
        self._dirty = True

    def _forget(self, key):
        kind, identity = key
        if kind == "quote":
            self.pending.discard(identity)
        elif kind == "identity":
            self.identity_pending.discard(identity)
        else:
            self.catalog_pending = False
        self._dirty = True

    def _cancel(self, key):
        if self._queued.pop(key, None) is not None:
            self._forget(key)
        # Cancellation never sets a retry cooldown. Revisiting is immediate.

    def _pump(self):
        if self.closed or self._batching:
            return
        while self._queued and len(self._active) < self.MAX_WORKERS:
            job = min(self._queued.values(), key=lambda job: (job.priority, job.sequence))
            del self._queued[job.key]
            self._active[job.key] = job
            future = self.pool.submit(job.function, *job.arguments)
            future.add_done_callback(lambda result, key=job.key: self._deliver(key, result))
            self._dirty = True
        if self._dirty:
            self._dirty = False
            self.state_changed.emit()

    def _deliver(self, key, future):
        if not self.closed:
            self._completed.emit(key, future)

    @Slot(object, object)
    def _finish(self, key, future):
        if self.closed:
            return
        job = self._active.pop(key, None)
        if job is None:
            return
        self._forget(key)
        kind, identity = key
        if kind == "identity":
            self.identity_retry[identity] = time.monotonic() + job.ttl
        try:
            result = future.result()
            if kind == "quote":
                self.delivered[identity] = result
                self.retry_at.pop(identity, None)
                self.quote_ready.emit(identity, result)
            elif kind == "identity":
                self.identity_ready.emit(identity, result)
            else:
                self.catalog_ready.emit(result)
        except Exception as error:
            if kind == "quote":
                now = time.time()
                quote = self.delivered.get(identity)
                # A failed early check gets one retry at expiry, then normal
                # failures back off for two minutes. Existing ages stay honest.
                self.retry_at[identity] = (max(now + 10, quote.fetched_at + job.ttl)
                                           if job.early and quote else now + 120)
                self.error.emit(identity, str(error))
            elif kind == "catalog":
                self.error.emit(0, f"Item catalog unavailable: {error}")
            # Ambiguous identities stay unresolved; never guess a market item.
        self._pump()

    def close(self):
        if self.closed:
            return
        self.closed = True
        for key in list(self._queued):
            self._cancel(key)
        self.pool.shutdown(wait=False, cancel_futures=True)
