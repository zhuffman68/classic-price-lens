"""One bounded background refresh; all reference browsing is local SQLite."""
from concurrent.futures import CancelledError,ThreadPoolExecutor
import hashlib
import time
from PySide6.QtCore import QObject,QTimer,Qt,Signal,Slot
from .http_json import get_bytes,get_json,RequestToken,request_scope
from .reference_data import ReferenceStore,API,FILES,DAY,drop_url,validate_meta
from .reference_community import CommunityDrops
from .reference_availability import AvailabilityLoader,market_proofs,screen_proof,user_confirmed_proofs
from .reference_recipes import RecipeAvailability
from .reference_geometry import MapGeometry
from .reference_sources import ItemSources


class ReferenceService(QObject):
    updated=Signal()
    changed=Signal()
    _finished=Signal(object)

    def __init__(self,path,parent=None,*,fetch_bytes=None,fetch_json=None):
        super().__init__(parent);self.store=ReferenceStore(path)
        self.fetch_bytes=fetch_bytes or get_bytes;self.fetch_json=fetch_json or get_json
        self.extra=CommunityDrops(self.store,self,fetch_bytes=fetch_bytes,fetch_json=fetch_json)
        self.geometry=MapGeometry(self.store,self,fetch_bytes=fetch_bytes,fetch_json=fetch_json)
        self.sources=ItemSources(self.store,self.extra.item_identity,self,fetch_bytes=fetch_bytes)
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='lupin-reference')
        self.busy=False;self.closed=False;self.error='';self.drop_error='';self.availability_error='';self.token=None
        self.core_changed=False;self.manifest_before=None
        self.market_signature=None
        self.screen_known=set();self.screen_notification_pending=False
        proofs=user_confirmed_proofs(self.store)
        if proofs:self.store.confirm(proofs,'user-confirmed')
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.start)
        self._finished.connect(self.finish,Qt.ConnectionType.QueuedConnection)

    def start(self,force=False):
        if self.closed or self.busy:return
        self.timer.stop();self.busy=True;self.error=self.drop_error=self.availability_error='';self.token=RequestToken()
        self.manifest_before=self.store.metadata().get('manifest')
        self.extra.enabled=True
        self.sources.enabled=True
        token=self.token
        future=self.pool.submit(self.refresh,token,force)
        future.add_done_callback(lambda result:self._finished.emit(result) if not self.closed else None)
        self.changed.emit()

    def refresh(self,token,force):
        errors={}
        with request_scope(token):
            try:
                meta=validate_meta(self.fetch_json(API+'meta.json'));token.check()
                previous=self.store.metadata().get('manifest')
                if previous==meta and self.store.has_payloads(meta):self.store.checked(meta,time.time())
                else:
                    payloads={}
                    for name in FILES:
                        token.check();info=meta['files'][name];raw=self.store.payload(name,info['sha256'])
                        if raw is None or hashlib.sha256(raw).hexdigest()!=info['sha256']:raw=self.fetch_bytes(API+name)
                        payloads[name]=raw
                    self.store.replace(meta,payloads,guard=token.check)
            except CancelledError:raise
            except Exception:errors['core']='Reference update unavailable'
            token.check();state=self.store.metadata()
            if state.get('counts'):
                proofs=user_confirmed_proofs(self.store)
                if proofs:self.store.confirm(proofs,'user-confirmed',guard=token.check)
                try:AvailabilityLoader(self.store,self.fetch_json,self.fetch_bytes).refresh(token,force)
                except CancelledError:raise
                except Exception:errors['availability']='Release availability update unavailable'
                if not errors.get('core'):
                    try:RecipeAvailability(self.store,self.fetch_bytes).refresh(token)
                    except CancelledError:raise
                    except Exception:errors['availability']='Recipe availability update unavailable'
                try:self.sources.refresh_shops(token,force)
                except CancelledError:raise
                except Exception:errors['sources']='Shop sources update unavailable'
            if state.get('counts') and (force or not 0<=time.time()-state.get('drops_checked_at',0)<DAY):
                try:
                    rows=[]
                    for offset in range(0,10000,500):
                        token.check();doc=self.fetch_json(drop_url(offset));page=doc.get('cargoquery') if isinstance(doc,dict) else None
                        if not isinstance(page,list) or len(page)>500:raise ValueError('Drop report format changed')
                        if any(not isinstance(r,dict) or not isinstance(r.get('title'),dict) for r in page):raise ValueError('Invalid drop report')
                        rows.extend(r['title'] for r in page)
                        if len(page)<500:break
                    else:raise ValueError('Drop report limit reached')
                    if not rows and state.get('drop_count'):raise ValueError('Empty drop generation')
                    self.store.save_drops(rows,guard=token.check)
                except CancelledError:raise
                except Exception:errors['drops']='Drop reports unavailable'
        return errors

    @Slot(object)
    def finish(self,future):
        if self.closed:return
        self.busy=False
        try:
            errors=future.result();self.error=errors.get('core','');self.drop_error=errors.get('drops','');self.availability_error=errors.get('availability','')
        except CancelledError:return
        except Exception:self.error='Reference update unavailable'
        self.core_changed=not self.error and self.manifest_before!=self.store.metadata().get('manifest')
        if self.core_changed:self.screen_known.clear()
        self.updated.emit();self.changed.emit()
        self.timer.start((15*60 if self.error or self.drop_error or self.availability_error else DAY)*1000)

    def close(self):
        self.closed=True;self.timer.stop()
        self.extra.close()
        self.sources.close()
        self.geometry.close()
        if self.token:self.token.cancel()
        self.pool.shutdown(wait=False,cancel_futures=True)

    def observe_market(self,catalog,snapshot,*,notify=True):
        signature=((snapshot.meta or {}).get('checked_at'),id(catalog),self.store.metadata().get('generation')) if snapshot and catalog else None
        if signature is None or signature==self.market_signature:return False
        self.market_signature=signature;proofs=market_proofs(self.store,catalog,snapshot)
        changed=bool(proofs and self.store.confirm(proofs,'market'))
        if changed and notify:self.updated.emit()
        return changed

    def observe_screen(self,catalog,*,game_id,visible_name,tier,surface,captured_at,game_verified,panel_verified,
                       mode='live',notify=True):
        """Called by accepted native OCR, never by manual search or chat names."""
        if self.closed:return False
        # Repeated frames do not touch SQLite or emit refresh/render signals.
        if type(game_id) is not int or not isinstance(visible_name,str) or tier is not None and not isinstance(tier,str):return False
        signature=(id(catalog),game_id,visible_name,tier)
        if signature in self.screen_known:return False
        proof=screen_proof(self.store,catalog,game_id=game_id,visible_name=visible_name,tier=tier,surface=surface,
            captured_at=captured_at,game_verified=game_verified,panel_verified=panel_verified,mode=mode)
        if not proof:return False
        changed=False
        if not self.store.available('items',game_id):changed=bool(self.store.confirm([proof],'screen',at=captured_at))
        if len(self.screen_known)>=1024:self.screen_known.clear()
        self.screen_known.add(signature)
        if changed and notify and not self.screen_notification_pending:
            self.screen_notification_pending=True;QTimer.singleShot(0,self._notify_screen)
        return changed

    def _notify_screen(self):
        self.screen_notification_pending=False
        if not self.closed:self.updated.emit()
