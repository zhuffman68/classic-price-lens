"""One shared market snapshot; item views never issue individual price requests."""
from concurrent.futures import CancelledError,ThreadPoolExecutor
import time
from PySide6.QtCore import QObject,Qt,QTimer,Signal,Slot
from .data import Cache,load_catalog
from .domain import DEFAULT_TTL,Quote
from .http_json import RequestToken,request_scope
from .snapshot import SnapshotStore
from .snapshot_updater import SnapshotUpdater
from .tls import retryable_catalog_error


class PriceService(QObject):
    catalog_ready=Signal(object)
    quote_ready=Signal(int,object)
    error=Signal(int,str)
    identity_ready=Signal(object,object)
    identity_error=Signal(object,str)
    state_changed=Signal()
    _completed=Signal(object)

    def __init__(self,cache_path,parent=None):
        super().__init__(parent)
        self.cache=Cache(cache_path);self.snapshot=SnapshotStore(self.cache)
        self.snapshot_updater=None;self.refresh_snapshot=False;self.interval=DEFAULT_TTL
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='lupin-catalog')
        self.closed=False;self.catalog_pending=False;self.catalog_retries=0;self.catalog_token=None
        self.delivered={};self.identity_outcomes={}
        self.manual_item=None;self.manual_identity=None;self.manual_candidates=()
        self._screen_demand=([],DEFAULT_TTL,{})
        self.catalog_retry_timer=QTimer(self);self.catalog_retry_timer.setSingleShot(True)
        self.catalog_retry_timer.setInterval(1500);self.catalog_retry_timer.timeout.connect(self._request_catalog)
        self._completed.connect(self._finish_catalog,Qt.ConnectionType.QueuedConnection)

    def start(self):
        if self.closed or self.catalog_pending:return
        self.catalog_retry_timer.stop();self.catalog_retries=0;self._request_catalog()
        if self.refresh_snapshot:self.set_snapshot_enabled(True)

    @property
    def catalog_retrying(self):return self.catalog_retry_timer.isActive()

    def _request_catalog(self):
        if self.closed or self.catalog_pending:return
        self.catalog_pending=True;self.catalog_token=RequestToken()
        token=self.catalog_token
        def load():
            with request_scope(token):return load_catalog(self.cache)
        future=self.pool.submit(load)
        future.add_done_callback(lambda result:self._completed.emit(result) if not self.closed else None)
        self.state_changed.emit()

    @Slot(object)
    def _finish_catalog(self,future):
        if self.closed:return
        self.catalog_pending=False
        try:self.catalog_ready.emit(future.result())
        except CancelledError:pass
        except Exception as error:
            if self.catalog_retries==0 and retryable_catalog_error(error):
                self.catalog_retries=1;self.catalog_retry_timer.start()
            self.error.emit(0,'Item catalog unavailable: '+str(error))
        self.state_changed.emit()

    def set_refresh_interval(self,seconds):
        self.interval=max(300,min(3600,int(seconds)))
        if self.snapshot_updater:self.snapshot_updater.set_interval(self.interval)

    def set_snapshot_enabled(self,enabled):
        self.refresh_snapshot=bool(enabled)
        if self.closed:return
        if self.snapshot_updater is None:
            self.snapshot_updater=SnapshotUpdater(self.snapshot,self)
            self.snapshot_updater.set_interval(self.interval)
            self.snapshot_updater.updated.connect(self._snapshot_updated)
            self.snapshot_updater.changed.connect(self.state_changed.emit)
        self.snapshot_updater.set_enabled(enabled)

    def snapshot_summary(self):
        return self.snapshot_updater.summary() if self.snapshot_updater else ''

    def _snapshot_updated(self):
        self.identity_outcomes.clear()
        items,ttl,options=self._screen_demand;self.observe(items,ttl,**options)
        self.state_changed.emit()

    def cached(self,item):
        """Exact-ID, name and unit validation, using the in-memory generation only."""
        return self.snapshot.quote(item) if item else None

    def reference(self,item):
        """Read this generation, including an explicit reference for missing data."""
        quote=self.cached(item)
        if quote is None:
            checked=(self.snapshot.meta or {}).get('checked_at',0)
            published=(self.snapshot.meta or {}).get('published_at')
            quote=Quote(item.game_id,None,checked,None,0,'MesoWatch','https://meso.watch/','no data',
                        basis='No price in the market snapshot',per_set=item.per_set,uncertain=True,published_at=published)
        return quote

    def request(self,item,ttl):
        if self.closed:return
        quote=self.reference(item)
        if self.delivered.get(item.game_id)!=quote:
            self.delivered[item.game_id]=quote;self.quote_ready.emit(item.game_id,quote)

    def observe(self,items,ttl,*,hovered_id=None,identities=(),hovered_identity=None):
        if self.closed:return
        items=list(items);identities=list(identities)
        self._screen_demand=(items,ttl,dict(hovered_id=hovered_id,identities=identities,hovered_identity=hovered_identity))
        demands={item.game_id:item for item in items}
        if self.manual_item:demands[self.manual_item.game_id]=self.manual_item
        for item in demands.values():self.request(item,ttl)
        checks=dict(identities)
        if self.manual_identity:checks[self.manual_identity]=self.manual_candidates
        for identity,candidates in checks.items():self.resolve_identity(identity,candidates,ttl)

    def clear_visible(self):self.observe([],self.interval)

    def set_manual(self,item,ttl=DEFAULT_TTL,*,identity=None,candidates=()):
        self.manual_item=item;self.manual_identity,self.manual_candidates=identity,candidates
        items,screen_ttl,options=self._screen_demand;self.observe(items,screen_ttl,**options)

    def resolve_identity(self,identity,candidates,ttl=DEFAULT_TTL):
        if self.closed:return
        generation=(self.snapshot.meta or {}).get('checked_at')
        key=(identity,tuple(item.game_id for item in candidates),generation)
        if key in self.identity_outcomes:return
        self.identity_outcomes[key]=True
        item=self.snapshot.identify(candidates)
        if item:self.identity_ready.emit(identity,item)
        else:self.identity_error.emit(identity,'No unique matching item in the market snapshot.')
        if len(self.identity_outcomes)>512:self.identity_outcomes={key:True}

    def state_for(self,item_id):
        updater=self.snapshot_updater
        if updater and updater.busy:return 'refreshing'
        if updater and updater.error:return 'retry'
        return ''

    def invalidate(self):
        self.delivered.clear()
        if self.snapshot_updater:self.snapshot_updater.refresh()

    def close(self):
        if self.closed:return
        self.closed=True;self.catalog_retry_timer.stop()
        if self.catalog_token:self.catalog_token.cancel()
        if self.snapshot_updater:self.snapshot_updater.close()
        self.pool.shutdown(wait=False,cancel_futures=True)
