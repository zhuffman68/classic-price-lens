"""Cached, user-selected Classic drop reports. Votes are never drop rates."""
from concurrent.futures import CancelledError,ThreadPoolExecutor
from html.parser import HTMLParser
import math
import re
import time
from urllib.parse import urlencode
from PySide6.QtCore import QObject,Qt,Signal,Slot
from .domain import key as name_key
from .http_json import RequestToken,get_bytes,get_json,request_scope
from .reference_data import DAY

BASE='https://meowdb.com/msclassic/'


class MonsterIndex(HTMLParser):
    """Read the public table's ID/name/level/HP, without scripts or a browser."""
    def __init__(self):
        super().__init__();self.rows={};self.ambiguous=set();self.cells=None;self.cell=None;self.link=None;self.words=[];self.headers=[];self.head=False;self.in_link=False

    def handle_starttag(self,tag,attrs):
        if tag=='tr':self.cells=[];self.link=None
        elif tag in ('td','th') and self.cells is not None:self.cell=[];self.head=tag=='th'
        elif tag=='a' and self.cell is not None:
            href=dict(attrs).get('href','');match=re.fullmatch(r'/msclassic/(?:en/)?monsters/(\d+)',href)
            if match:self.link=(int(match[1]),'');self.words=[];self.in_link=True

    def handle_data(self,data):
        if self.cell is not None:self.cell.append(data)
        if self.in_link:self.words.append(data)

    def handle_endtag(self,tag):
        if tag=='a' and self.in_link:self.link=(self.link[0],''.join(self.words).strip());self.words=[];self.in_link=False
        elif tag in ('td','th') and self.cell is not None:
            self.cells.append(''.join(self.cell).strip());self.cell=None
        elif tag=='tr' and self.cells is not None:
            if self.head and self.cells:self.headers=self.cells
            elif self.link and len(self.cells)>=4 and self.headers and self.headers[2].startswith('LV') and self.headers[3]=='HP':
                try:
                    identity,name=self.link;level=int(self.cells[2].replace(',',''));hp=int(self.cells[3].replace(',',''))
                    key=str(identity);proof={'name':name,'level':level,'hp':hp}
                    if key in self.rows and self.rows[key]!=proof:self.rows.pop(key);self.ambiguous.add(key)
                    if key not in self.ambiguous:self.rows[key]=proof
                except ValueError:pass
            self.cells=None;self.cell=None;self.link=None;self.head=False


class CommunityDrops(QObject):
    updated=Signal(object)
    changed=Signal()
    _finished=Signal(object)

    def __init__(self,store,parent=None,*,fetch_json=None,fetch_bytes=None):
        super().__init__(parent);self.store=store;self.enabled=False;self.closed=False;self.current=None;self.pending=None
        self.fetch_json=fetch_json or get_json;self.fetch_bytes=fetch_bytes or get_bytes
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='lupin-drop-reports')
        self._finished.connect(self.finish,Qt.ConnectionType.QueuedConnection)

    def select(self,entry,force=False):
        if entry and entry.kind=='items':
            record=self.store.entry('items',entry.id)
            if record and record[1].get('cash'):entry=None
        key=entry.key if entry and entry.kind in ('items','monsters') else None
        if key==self.current and (self.pending is not None or key is None):return
        self.cancel();self.current=key
        if self.closed or not self.enabled or key is None:return
        previous=self.store.community_check(*key)
        if not force and previous and 0<=time.time()-previous[0]<(1800 if previous[1].get('error') else DAY):return
        token=RequestToken();self.pending=(key,token)
        future=self.pool.submit(self.load,entry,token)
        future.add_done_callback(lambda result:self._finished.emit((key,token,result)) if not self.closed else None)
        self.changed.emit()

    def cancel(self):
        if self.pending:self.pending[1].cancel()
        self.pending=None;self.current=None

    def index(self,token):
        state=self.store.metadata();cached=state.get('community_monsters')
        if cached and 0<=time.time()-cached.get('saved',0)<DAY:return cached['rows']
        raw=self.fetch_bytes(BASE+'monsters');token.check()
        if len(raw)>3*1024*1024:raise ValueError('Monster index too large')
        parser=MonsterIndex();parser.feed(raw.decode('utf-8'))
        if len(parser.rows)<10:raise ValueError('Monster index unavailable')
        with self.store.connect() as db:
            self.store.put_meta(db,'community_monsters',{'saved':time.time(),'rows':parser.rows});token.check()
        return parser.rows

    def verified_monster(self,identity,index):
        record=self.store.entry('monsters',identity);proof=index.get(str(identity))
        if not record or not proof:return None
        entry,body=record
        if (name_key(entry.name)==name_key(proof['name']) and body.get('level')==proof.get('level') and body.get('hp')==proof.get('hp')):return entry
        return None

    def item_identity(self,entry,token):
        matches={}
        for page in range(1,6):
            doc=self.fetch_json(BASE+'api/items?'+urlencode({'search':entry.name,'page':page}));token.check()
            if not isinstance(doc,dict) or not isinstance(doc.get('items'),list) or len(doc['items'])>100:raise ValueError('Item index unavailable')
            for row in doc['items']:
                if not isinstance(row,dict):continue
                if str(row.get('iconKey'))==str(entry.id) and name_key(row.get('name',''))==name_key(entry.name) and type(row.get('id')) is int and 0<row['id']<=2147483647:
                    matches[row['id']]=row
            if not doc.get('hasMore'):break
        else:return None
        return next(iter(matches)) if len(matches)==1 else None

    def load(self,entry,token):
        with request_scope(token):
            try:
                index=self.index(token);token.check()
                if entry.kind=='monsters':
                    if self.verified_monster(entry.id,index) is None:raise ValueError('Unverified monster')
                    provider_id=entry.id;parameter='monsterId';source=BASE+'monsters/'+str(provider_id)
                else:
                    provider_id=self.item_identity(entry,token)
                    if provider_id is None:raise ValueError('Unverified item')
                    parameter='itemId';source=BASE+'item-db/'+str(provider_id)
                doc=self.fetch_json(BASE+'api/drops?'+urlencode({parameter:provider_id}));token.check()
                raw=doc.get('drops') if isinstance(doc,dict) else None
                if not isinstance(raw,list) or len(raw)>1000:raise ValueError('Drop feed unavailable')
                results=[]
                for row in raw:
                    if not isinstance(row,dict):continue
                    if entry.kind=='monsters':
                        text=row.get('itemIconKey');item_id=int(text) if isinstance(text,str) and re.fullmatch(r'\d{1,10}',text) else None
                        record=self.store.entry('items',item_id) if item_id else None
                        if not record or name_key(record[0].name)!=name_key(row.get('itemName','')):continue
                        item=record[0];monster=entry
                    else:
                        identity=row.get('monsterId');monster=self.verified_monster(identity,index) if type(identity) is int else None
                        if monster is None:continue
                        item=entry
                    up,down=row.get('upvotes',0),row.get('downvotes',0)
                    if any(type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=1000000 for value in (up,down)):continue
                    results.append({'monster_id':monster.id,'monster_name':monster.name,'item_id':item.id,'item_name':item.name,
                        'category':{'Equipment':'equip','Consumable':'use'}.get(item.category,item.category.casefold()),
                        'source':'meow','source_url':source,'rate':None,'upvotes':up,'downvotes':down,'disputed':down>up})
                self.store.save_community(entry.kind,entry.id,results,{'source_url':source},guard=token.check)
            except CancelledError:raise
            except Exception:self.store.save_community(entry.kind,entry.id,[],{'error':True},guard=token.check)
        return entry.key

    @Slot(object)
    def finish(self,result):
        if self.closed:return
        key,token,future=result
        if self.pending!=(key,token):return
        self.pending=None
        try:future.result()
        except CancelledError:return
        except Exception:self.changed.emit();return
        self.updated.emit(key);self.changed.emit()

    def close(self):
        self.closed=True;self.cancel();self.pool.shutdown(wait=False,cancel_futures=True)
