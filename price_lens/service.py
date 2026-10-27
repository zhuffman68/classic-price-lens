"""Visible-item HTTP scheduling, bounded concurrency and shared cached results."""
from collections import deque
from concurrent.futures import CancelledError, ThreadPoolExecutor
from dataclasses import dataclass, field
import time

from PySide6.QtCore import QObject, Qt, Signal, Slot

from .data import Cache, MeowProvider, load_catalog
from .http_json import RequestToken, request_scope
from .provider_index import load_index
from .snapshot import SnapshotStore
from .snapshot_updater import SnapshotUpdater


@dataclass
class _Lookup:
    key: tuple
    function: object
    arguments: tuple
    priority: int
    sequence: int
    ttl: int = 900
    early: bool = False
    token: RequestToken = field(default_factory=RequestToken)
    queued_at: float = field(default_factory=time.monotonic)
    started_at: float = 0


class PriceService(QObject):
    catalog_ready = Signal(object)
    quote_ready = Signal(int, object)
    error = Signal(int, str)
    identity_ready = Signal(object, object)
    identity_error = Signal(object, str)
    state_changed = Signal()
    _completed = Signal(object, object)

    MAX_WORKERS = 3
    MAX_QUEUED = 64

    def __init__(self, cache_path, parent=None):
        super().__init__(parent)
        self.cache = Cache(cache_path)
        self.provider = MeowProvider(self.cache)
        self.snapshot = SnapshotStore(self.cache)
        self.snapshot_updater = None
        self.refresh_snapshot = False
        self.pool = ThreadPoolExecutor(max_workers=self.MAX_WORKERS, thread_name_prefix="classic-prices")
        self.pending = set()
        self.retry_at = {}
        self.delivered = {}
        self.loaded = set()
        self.closed = False
        self.refresh_index = False
        self.identity_pending = set()
        self.identity_retry = {}
        self.catalog_pending = False
        self._queued = {}
        self._active = {}
        self._sequence = 0
        self._batching = 0
        self._dirty = False
        self.timings = deque(maxlen=256)
        self.manual_item = None
        self.manual_identity = None
        self.manual_candidates = ()
        self.manual_ttl = 900
        self._screen_demand = ([], 900, {})
        # Workers never change scheduler/UI state. Even instant completions are
        # delivered on this object's Qt thread, after the current batch ends.
        self._completed.connect(self._finish, Qt.ConnectionType.QueuedConnection)

    def start(self):
        if self.closed or self.catalog_pending:
            return
        self._enqueue(("catalog", None), load_catalog, (self.cache,), -10)
        if self.refresh_snapshot:
            self.set_snapshot_enabled(True)
        if self.refresh_index:self._enqueue(("index",None),load_index,(self.cache,),30)
        self._pump()

    def set_snapshot_enabled(self, enabled):
        self.refresh_snapshot = enabled
        if self.closed:
            return
        if not self.snapshot_updater:
            self.snapshot_updater = SnapshotUpdater(self.snapshot, self)
            self.snapshot_updater.updated.connect(self._snapshot_updated)
            self.snapshot_updater.changed.connect(self.state_changed.emit)
        self.snapshot_updater.set_enabled(enabled)

    def _snapshot_updated(self):
        self.loaded.clear()
        items, ttl, options = self._screen_demand
        self.observe(items, ttl, **options)

    def snapshot_summary(self):
        return self.snapshot_updater.summary() if self.snapshot_updater else ""

    @staticmethod
    def refresh_lead(item_id, ttl):
        """Spread early refreshes over 7.5-30 seconds, depending on the TTL."""
        window = min(30.0, ttl * 0.05)
        return window * (0.5 + (item_id * 2654435761 % 1000) / 2000)

    def observe(self, items, ttl, *, hovered_id=None, identities=(), hovered_identity=None):
        """Replace demand, cancelling obsolete queued and running price requests."""
        if self.closed:
            return
        items = list(items)
        identities = list(identities)
        self._screen_demand = (items, ttl, {"hovered_id":hovered_id,"identities":identities,"hovered_identity":hovered_identity})
        items = {item.game_id: item for item in items}
        identities = {identity: candidates for identity, candidates in identities}
        visible = {("quote", item_id) for item_id in items}
        visible.update(("identity", identity) for identity in identities)
        if self.manual_item:
            visible.add(("quote",self.manual_item.game_id))
        if self.manual_identity:
            visible.add(("identity",self.manual_identity))
        self._batching += 1
        try:
            for key in list(self._queued):
                if key[0] != "catalog" and key not in visible:
                    self._cancel(key)
            for key, job in list(self._active.items()):
                if ((key[0] in ("quote", "identity") and key not in visible)
                        or key[0]=="index" and visible):
                    job.token.cancel()
            # Stage the whole view before starting anything, so the hovered
            # item can take the next free slot even in a newly opened shop.
            for item in items.values():
                self.request(item, ttl, priority=0 if item.game_id == hovered_id else 10, early=True)
            if self.manual_item:
                self.request(self.manual_item,self.manual_ttl,priority=-1,early=True)
            if self.manual_identity:
                self.resolve_identity(self.manual_identity,self.manual_candidates,self.manual_ttl,priority=-1)
            for identity, candidates in identities.items():
                self.resolve_identity(identity, candidates, ttl,
                                      priority=0 if identity == hovered_identity else 10)
        finally:
            self._batching -= 1
        self._pump()

    def clear_visible(self):
        self.observe([], 900)

    def set_manual(self, item, ttl=900, *, identity=None, candidates=()):
        """One explicitly selected search result; independent of screen sharing."""
        self.manual_item, self.manual_ttl = item, ttl
        self.manual_identity, self.manual_candidates = identity, candidates
        items, screen_ttl, options = self._screen_demand
        self.observe(items,screen_ttl,**options)

    def request(self, item, ttl, *, priority=10, early=False):
        if self.closed:
            return
        key = ("quote", item.game_id)
        quote = self.delivered.get(item.game_id)
        if item.game_id not in self.loaded:
            quote = self.cache.quote(item.game_id)
            self.loaded.add(item.game_id)
        now = time.time()
        bulk = self.snapshot.quote(item)
        if bulk and (bulk.cache_valid(now, ttl) or quote is None
                     or not quote.cache_valid(now, ttl) and bulk.fetched_at > quote.fetched_at):
            quote = bulk
        if quote:
            if self.delivered.get(item.game_id) != quote:
                self.delivered[item.game_id] = quote
                self.quote_ready.emit(item.game_id, quote)
            if quote.cache_valid(now, ttl):
                if quote.published_at is not None:
                    self._cancel(key)
                    if active := self._active.get(key):
                        active.token.cancel()
                    self._pump()
                    return
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
        if item := self.snapshot.identify(candidates):
            self.identity_retry[identity] = time.monotonic() + ttl
            self.identity_ready.emit(identity, item)
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
        elif kind == "catalog":
            self.catalog_pending = True
        self._dirty = True

    def _forget(self, key):
        kind, identity = key
        if kind == "quote":
            self.pending.discard(identity)
        elif kind == "identity":
            self.identity_pending.discard(identity)
        elif kind == "catalog":
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
            job.started_at = time.monotonic()
            future = self.pool.submit(self._run,job)
            future.add_done_callback(lambda result, key=job.key: self._deliver(key, result))
            self._dirty = True
        if self._dirty:
            self._dirty = False
            self.state_changed.emit()

    @staticmethod
    def _run(job):
        with request_scope(job.token):
            return job.function(*job.arguments)

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
        self.timings.append({"kind":kind,"queue_ms":round((job.started_at-job.queued_at)*1000,1),
                             "request_ms":round((time.monotonic()-job.started_at)*1000,1),
                             "cancelled":job.token.cancelled.is_set()})
        if job.token.cancelled.is_set() or future.cancelled():
            if kind=="quote":self.loaded.discard(identity)
            items,ttl,options = self._screen_demand
            self.observe(items,ttl,**options)
            return
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
            elif kind == "index":
                self.provider.index = result
            else:
                self.catalog_ready.emit(result)
        except CancelledError:
            pass
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
            elif kind == "identity":
                self.identity_error.emit(identity,str(error))
            # Ambiguous identities stay unresolved; never guess a market item.
        self._pump()

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.snapshot_updater:
            self.snapshot_updater.close()
        for key in list(self._queued):
            self._cancel(key)
        for job in self._active.values():job.token.cancel()
        self.pool.shutdown(wait=False, cancel_futures=True)
