"""Named NPC shops and reported reward boxes, cached independently of prices."""
from concurrent.futures import CancelledError,ThreadPoolExecutor
from html.parser import HTMLParser
import re
import time
from PySide6.QtCore import QObject,Qt,Signal,Slot
from .domain import key as name_key
from .http_json import RequestToken,get_bytes,request_scope
from .reference_data import DAY

BASE='https://meowdb.com/msclassic/'


class Node:
    def __init__(self,tag='',attrs=(),parent=None):
        self.tag=tag;self.attrs=dict(attrs);self.parent=parent;self.parts=[]
    def text(self):return ''.join(p.text() if isinstance(p,Node) else p for p in self.parts)
    def walk(self,tag):
        if self.tag==tag:yield self
        for part in self.parts:
            if isinstance(part,Node):yield from part.walk(tag)


class Document(HTMLParser):
    def __init__(self,raw):
        super().__init__(convert_charrefs=True)
        if not isinstance(raw,bytes) or len(raw)>2*1024*1024:raise ValueError('Source page too large')
        self.root=Node();self.stack=[self.root];self.feed(raw.decode('utf-8'))
    def handle_starttag(self,tag,attrs):
        node=Node(tag,attrs,self.stack[-1]);self.stack[-1].parts.append(node)
        if tag not in ('img','br','hr','meta','input','link','source','wbr'):self.stack.append(node)
    def handle_endtag(self,tag):
        for index in range(len(self.stack)-1,0,-1):
            if self.stack[index].tag==tag:self.stack=self.stack[:index];break
    def handle_data(self,data):
        if self.stack[-1].tag not in ('script','style'):self.stack[-1].parts.append(data)


def links(node,kind):
    for link in node.walk('a'):
        match=re.fullmatch('/msclassic/'+kind+r'/(\d{1,10})',link.attrs.get('href',''))
        if match:yield int(match[1]),link.text().strip()


def npc_shops(raw,store):
    document=Document(raw);records={}
    for table in document.root.walk('table'):
        owner=table.parent
        while owner and not list(links(owner,'npcs')):owner=owner.parent
        if owner is None or owner is document.root:continue
        npcs=[(i,n) for i,n in links(owner,'npcs') if n]
        if not npcs:continue
        nid,name=npcs[0];npc=store.entry('npcs',nid)
        if not npc or name_key(npc[0].name)!=name_key(name):continue
        maps=list(links(owner,'maps'));mid,mname=maps[0] if maps else (None,'')
        basis='Launch prices' if 'Launch prices' in owner.text()[:800] else 'Published shop inventory'
        for tr in table.walk('tr'):
            cells=list(tr.walk('td'));items=list(links(tr,'item-db'))
            if len(cells)<3 or len(items)!=1:continue
            icons=[img.attrs.get('src','') for img in tr.walk('img')]
            identities=[int(m[1]) for url in icons if (m:=re.fullmatch(r'/msclassic/api/assets/icons/(\d{1,10})',url))]
            if len(identities)!=1:continue
            iid=identities[0];item=store.entry('items',iid)
            if not item or name_key(item[0].name)!=name_key(items[0][1]):continue
            match=re.fullmatch(r'([\d,]+)\s*mesos',cells[-1].text().strip())
            if not match or not re.fullmatch(r'\d{1,3}(?:,\d{3})*|\d+',match[1]):continue
            price=int(match[1].replace(',',''))
            if price>2_147_483_647:continue
            row=dict(kind='npc',id=nid,name=npc[0].name,item_id=iid,item_name=item[0].name,
                price=price,map_id=mid,map_name=mname,basis=basis,source_url=BASE+'npc-shops')
            records[(iid,nid,mid)]=row
    if not records:raise ValueError('No verified NPC shops')
    return list(records.values())


def reward_boxes(raw):
    document=Document(raw);found={}
    for node in document.root.walk('span'):
        if not node.text().strip().startswith('Found in:'):continue
        for identity,name in links(node,'item-db'):
            if name:found[identity]=name
    return list(found.items())[:20]


class ItemSources(QObject):
    updated=Signal(object)
    _finished=Signal(object)
    def __init__(self,store,resolver,parent=None,fetch_bytes=None):
        super().__init__(parent);self.store=store;self.resolver=resolver;self.fetch_bytes=fetch_bytes or get_bytes
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='lupin-item-sources')
        self.closed=False;self.pending=None;self.current=None;self.enabled=False
        self._finished.connect(self.finish,Qt.ConnectionType.QueuedConnection)
    def refresh_shops(self,token,force=False):
        previous=self.store.value('npc_shops_checked',0)
        if not force and 0<=time.time()-previous<DAY:return
        raw=self.fetch_bytes(BASE+'npc-shops');token.check();rows=npc_shops(raw,self.store)
        self.store.save_sources('npc',rows,guard=token.check)
    def select(self,entry):
        key=entry.key if entry and entry.kind=='items' else None
        if self.current==key and (self.pending is not None or key is None):return
        if self.pending:self.pending[1].cancel()
        self.pending=None;self.current=key
        if self.closed or not self.enabled or key is None:return
        previous=self.store.source_check(entry.id)
        if previous and 0<=time.time()-previous[0]<(1800 if previous[1] else DAY):return
        token=RequestToken();self.pending=(key,token)
        future=self.pool.submit(self.load,entry,token)
        future.add_done_callback(lambda result:self._finished.emit((key,token,result)) if not self.closed else None)
    def load(self,entry,token):
        with request_scope(token):
            try:
                provider=self.resolver(entry,token)
                if provider is None:raise ValueError('Unverified source item')
                raw=self.fetch_bytes(BASE+'item-db/'+str(provider));token.check();boxes=reward_boxes(raw);rows=[]
                for pid,name in boxes:
                    matches=self.store.search('items',name,limit=100)[0]
                    matches=[e for e in matches if name_key(e.name)==name_key(name)]
                    if len(matches)!=1:continue
                    box=matches[0]
                    if self.resolver(box,token)!=pid:continue
                    rows.append(dict(kind='box',id=box.id,name=box.name,item_id=entry.id,item_name=entry.name,
                        basis='Player reported',source_url=BASE+'item-db/'+str(provider)))
                token.check();self.store.save_sources('box',rows,item_id=entry.id,guard=token.check)
            except CancelledError:raise
            except Exception:self.store.source_failed(entry.id,guard=token.check)
    @Slot(object)
    def finish(self,result):
        key,token,future=result
        if self.closed or self.pending!=(key,token):return
        self.pending=None
        try:future.result()
        except CancelledError:return
        except Exception:return
        self.updated.emit(key)
    def close(self):
        self.closed=True
        if self.pending:self.pending[1].cancel()
        self.pool.shutdown(wait=False,cancel_futures=True)
