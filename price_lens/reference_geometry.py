"""Lazy, bounded map alignment; retain only coordinates and verification results."""
from concurrent.futures import CancelledError,ThreadPoolExecutor
import hashlib,json,re,time
from PySide6.QtCore import QObject,Signal,Qt,QBuffer,QByteArray,QIODevice
from PySide6.QtGui import QImageReader,QImageIOHandler
from .http_json import RequestToken,request_scope,get_bytes,get_json
from .reference_data import DAY

PORTALS='https://osmsdataexplorer.com/data/current/portals.json'


def geometry_key(row):
    return hashlib.sha256(json.dumps(['projection-v2',row.get('render_url'),row.get('minimap_url'),row.get('portals'),row.get('mobs')],sort_keys=True).encode()).hexdigest()


def alignment(row,portals):
    """The provider's viewer uses these portal positions in native image pixels."""
    matched=[]
    for source in row.get('portals',[]):
        if source.get('type') not in (1,2) or type(source.get('dest_map_id')) is not int:continue
        options=[p for p in portals if p.get('name')==source.get('name') and str(p.get('dest_map'))==str(source['dest_map_id']) and p.get('type')==source['type']]
        if len(options)!=1:continue
        target=options[0]
        if any(type(p.get(axis)) is not int for p in (source,target) for axis in ('x','y')):continue
        matched.append((target['x']-source['x'],target['y']-source['y'],source['x'],source['y']))
    if len({(p[2],p[3]) for p in matched})<2 or len({p[:2] for p in matched})!=1:return None
    return dict(dx=matched[0][0],dy=matched[0][1],anchors=len(matched))


def native_size(data,url):
    match=re.fullmatch(r'https://osmsdataexplorer.com/data/maps/([a-f0-9]{32})\.webp',url or '')
    if not match or not 24<=len(data)<=4*1024*1024 or hashlib.md5(data,usedforsecurity=False).hexdigest()!=match[1]:return None
    buffer=QBuffer();buffer.setData(QByteArray(data));buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    size=QImageReader(buffer,b'webp').size()
    return (size.width(),size.height()) if 0<size.width()<=30000 and 0<size.height()<=30000 else None


def matching_projection(native,minimap):
    """Confirm the minimap is the same full-canvas projection, not a different crop.

    Both palette and terrain-edge evidence must agree. Where the image plugin
    cannot decode at thumbnail resolution, cap the one-time native decode at
    eight million pixels. Uncertain/cropped maps get no markers.
    """
    small_buffer=QBuffer();small_buffer.setData(QByteArray(minimap));small_buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    small_reader=QImageReader(small_buffer);size=small_reader.size()
    if not (8<=size.width()<=512 and 8<=size.height()<=512):return False
    small=small_reader.read()
    if small.isNull():return False
    buffer=QBuffer();buffer.setData(QByteArray(native));buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    reader=QImageReader(buffer,b'webp');full=reader.size()
    if full.isEmpty() or abs((size.width()/size.height())/(full.width()/full.height())-1)>.025:return False
    if not reader.supportsOption(QImageIOHandler.ImageOption.ScaledSize) and full.width()*full.height()>8*1024*1024:return False
    reader.setScaledSize(size);image=reader.read()
    if image.isNull() or image.size()!=size:return False
    compared=colours=edges=edge_matches=0
    rgb=lambda p:((p>>16)&255,(p>>8)&255,p&255)
    for y in range(1,size.height()-1,2):
        for x in range(1,size.width()-1,2):
            p=small.pixel(x,y);a=rgb(p)
            if (p>>24)<128 or max(a)<45:continue
            b=rgb(image.pixel(x,y));compared+=1
            if max(abs(v-w) for v,w in zip(a,b))<=48:colours+=1
            for dx,dy in ((1,0),(0,1)):
                da=sum(abs(v-w) for v,w in zip(a,rgb(small.pixel(x+dx,y+dy))))
                if da<90:continue
                edges+=1;db=sum(abs(v-w) for v,w in zip(b,rgb(image.pixel(x+dx,y+dy))))
                if db>=60:edge_matches+=1
    return compared>=32 and edges>=12 and colours/compared>=.8 and edge_matches/edges>=.75


class MapGeometry(QObject):
    updated=Signal(int)
    _finished=Signal(object)

    def __init__(self,store,parent=None,*,fetch_bytes=None,fetch_json=None):
        super().__init__(parent);self.store=store;self.fetch_bytes=fetch_bytes or get_bytes;self.fetch_json=fetch_json or get_json
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='lupin-map-geometry');self.pending=None;self.closed=False
        self._finished.connect(self.finish,Qt.ConnectionType.QueuedConnection)

    def cached(self,row):
        value=self.store.value('map_geometry',{}).get(str(row['id']))
        return value.get('proof') if value and value.get('key')==geometry_key(row) else None

    def select(self,row):
        key=(row['id'],geometry_key(row)) if row else None
        if self.pending and self.pending[0]==key:return
        if self.pending:self.pending[1].cancel()
        self.pending=None
        if self.closed or row is None:return
        previous=self.store.value('map_geometry',{}).get(str(row['id']))
        if previous and previous.get('key')==key[1] and 0<=time.time()-previous.get('saved',0)<(DAY if previous.get('proof') else 1800):return
        token=RequestToken();self.pending=(key,token)
        future=self.pool.submit(self.load,row,token);future.add_done_callback(lambda result:self._finished.emit((key,token,result)) if not self.closed else None)

    def load(self,row,token):
        proof=None;previous=self.store.value('map_geometry',{}).get(str(row['id']))
        try:
            with request_scope(token):
                state=self.store.value('map_portals',{})
                if not 0<=time.time()-state.get('saved',0)<DAY:
                    rows=self.fetch_json(PORTALS);token.check()
                    if not isinstance(rows,dict) or len(rows)>2000 or any(not isinstance(v,list) or len(v)>1000 for v in rows.values()):raise ValueError('Invalid map alignment index')
                    state={'saved':time.time(),'rows':rows}
                    with self.store.connect() as db:self.store.put_meta(db,'map_portals',state);token.check()
                offsets=alignment(row,state.get('rows',{}).get(f"{row['id']:09d}",[]))
                if offsets:
                    data=self.fetch_bytes(row.get('render_url',''));token.check();size=native_size(data,row.get('render_url'))
                    if size:
                        verified=False
                        minimap=row.get('minimap_url','')
                        if re.fullmatch(r'https://osmsdataexplorer.com/data/current/images/maps/\d+\.png',minimap):
                            small=self.fetch_bytes(minimap);token.check()
                            if len(small)<=1024*1024:verified=matching_projection(data,small)
                        proof=dict(**offsets,width=size[0],height=size[1],projection_verified=verified)
        except CancelledError:raise
        except Exception:
            if previous and previous.get('key')==geometry_key(row):proof=previous.get('proof')
        token.check()
        with self.store.connect() as db:
            saved=dict(self.store.value('map_geometry',{}));saved[str(row['id'])]={'key':geometry_key(row),'saved':time.time(),'proof':proof}
            self.store.put_meta(db,'map_geometry',saved);token.check()
        return proof

    def finish(self,result):
        if self.closed:return
        key,token,future=result
        if self.pending!=(key,token):return
        self.pending=None
        try:future.result()
        except CancelledError:return
        except Exception:return
        self.updated.emit(key[0])

    def close(self):
        self.closed=True
        if self.pending:self.pending[1].cancel()
        self.pool.shutdown(wait=False,cancel_futures=True)
