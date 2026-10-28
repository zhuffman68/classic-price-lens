"""One bounded background refresh; all reference browsing is local SQLite."""
from concurrent.futures import CancelledError,ThreadPoolExecutor
import hashlib
import time
from PySide6.QtCore import QObject,QTimer,Qt,Signal,Slot
from .http_json import get_bytes,get_json,RequestToken,request_scope
from .reference_data import ReferenceStore,API,FILES,DAY,drop_url,validate_meta
from .reference_community import CommunityDrops


class ReferenceService(QObject):
    updated=Signal()
    changed=Signal()
    _finished=Signal(object)

    def __init__(self,path,parent=None,*,fetch_bytes=None,fetch_json=None):
        super().__init__(parent);self.store=ReferenceStore(path)
        self.fetch_bytes=fetch_bytes or get_bytes;self.fetch_json=fetch_json or get_json
        self.extra=CommunityDrops(self.store,self,fetch_bytes=fetch_bytes,fetch_json=fetch_json)
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='lupin-reference')
        self.busy=False;self.closed=False;self.error='';self.drop_error='';self.token=None
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.start)
        self._finished.connect(self.finish,Qt.ConnectionType.QueuedConnection)

    def start(self,force=False):
        if self.closed or self.busy:return
        self.timer.stop();self.busy=True;self.error=self.drop_error='';self.token=RequestToken()
        self.extra.enabled=True
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
                if previous==meta:self.store.checked(meta,time.time())
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
            errors=future.result();self.error=errors.get('core','');self.drop_error=errors.get('drops','')
        except CancelledError:return
        except Exception:self.error='Reference update unavailable'
        self.updated.emit();self.changed.emit()
        self.timer.start((15*60 if self.error or self.drop_error else DAY)*1000)

    def close(self):
        self.closed=True;self.timer.stop()
        self.extra.close()
        if self.token:self.token.cancel()
        self.pool.shutdown(wait=False,cancel_futures=True)
