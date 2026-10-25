"""Bounded background HTTP lookups; repeated screen readings share one request."""
from concurrent.futures import ThreadPoolExecutor
import time

from PySide6.QtCore import QObject, Signal

from .data import Cache, MeowProvider, load_catalog


class PriceService(QObject):
    catalog_ready = Signal(object)
    quote_ready = Signal(int, object)
    error = Signal(int, str)
    identity_ready = Signal(object, object)

    def __init__(self, cache_path, parent=None):
        super().__init__(parent)
        self.cache = Cache(cache_path)
        self.provider = MeowProvider(self.cache)
        self.pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="classic-prices")
        self.pending = set()
        self.retry_at = {}
        self.delivered = {}
        self.loaded = set()
        self.closed = False
        self.identity_pending = set()
        self.identity_retry = {}

    def start(self):
        future = self.pool.submit(load_catalog, self.cache)
        def done(result):
            if self.closed:
                return
            try:
                self.catalog_ready.emit(result.result())
            except Exception as error:
                self.error.emit(0, f"Item catalog unavailable: {error}")
        future.add_done_callback(done)

    def request(self, item, ttl):
        quote = self.delivered.get(item.game_id)
        if item.game_id not in self.loaded:
            quote = self.cache.quote(item.game_id)
            self.loaded.add(item.game_id)
        if quote:
            if self.delivered.get(item.game_id) != quote:
                self.delivered[item.game_id] = quote
                self.quote_ready.emit(item.game_id, quote)
            if quote.cache_valid(ttl=ttl):
                return
        now = time.time()
        if item.game_id in self.pending or now < self.retry_at.get(item.game_id, 0):
            return
        # A successful response without a fresh observation is also cooled down.
        self.pending.add(item.game_id)
        self.retry_at[item.game_id] = now + 120
        future = self.pool.submit(self.provider.fetch, item)
        def done(result):
            if self.closed:
                return
            try:
                quote = result.result()
                self.delivered[item.game_id] = quote
                self.quote_ready.emit(item.game_id, quote)
            except Exception as error:
                self.error.emit(item.game_id, str(error))
            finally:
                # Signal delivery and GUI calls are serialized by the Qt event loop;
                # set.discard is safe under Python's GIL.
                self.pending.discard(item.game_id)
        future.add_done_callback(done)

    def invalidate(self):
        self.loaded.clear()
        self.delivered.clear()

    def resolve_identity(self, identity, candidates, ttl=15 * 60):
        if identity in self.identity_pending or time.monotonic() < self.identity_retry.get(identity, 0):
            return
        self.identity_pending.add(identity)
        self.identity_retry[identity] = time.monotonic() + ttl
        future = self.pool.submit(self.provider.resolve_name, identity[0], candidates)
        def done(result):
            if self.closed:
                return
            try:
                self.identity_ready.emit(identity, result.result())
            except Exception:
                pass  # Ambiguity stays explicit on the row, never becomes a guess.
            finally:
                self.identity_pending.discard(identity)
        future.add_done_callback(done)

    def close(self):
        self.closed = True
        self.pool.shutdown(wait=False, cancel_futures=True)
