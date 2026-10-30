"""Bounded thumbnail prefetch and one source-timed visible monster animation."""
from collections import OrderedDict,deque
import hashlib
import json
from pathlib import Path
import time
from PySide6.QtCore import QByteArray,QBuffer,QIODevice,QObject,QRect,QSize,QUrl,Qt,Signal,QEvent
from PySide6.QtGui import QColor,QImage,QImageReader,QMovie,QPainter
from PySide6.QtNetwork import QNetworkAccessManager,QNetworkReply,QNetworkRequest
from PySide6.QtWidgets import QWidget
from .reference_data import image_url
from .motion import enabled

MAX_BYTES=4*1024*1024
TTL=30*86400
FAIL_TTL=6*3600


def decode(data):
    if not 24<=len(data)<=MAX_BYTES:return QImage()
    if not (data.startswith(b'\x89PNG\r\n\x1a\n') or data[:4]==b'RIFF' and data[8:12]==b'WEBP'):return QImage()
    buffer=QBuffer();buffer.setData(QByteArray(data));buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    reader=QImageReader(buffer);size=reader.size();frames=max(1,reader.imageCount())
    if not(0<size.width()<=1024 and 0<size.height()<=1024 and frames<=160
            and size.width()*size.height()*frames*4<=32*1024*1024):return QImage()
    return reader.read()


class ReferenceMedia(QObject):
    ready=Signal(str)

    def __init__(self,folder,parent=None):
        super().__init__(parent);self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True)
        self.manager=QNetworkAccessManager(self);self.memory=OrderedDict();self.active={};self.queue=deque();self.closed=False
        self.memory_bytes=0;self.disk_checked=0
        self.disk_bytes=0;self.disk_files=set()
        for path in (*self.folder.glob('*.png'),*self.folder.glob('*.webp')):
            try:self.disk_bytes+=path.stat().st_size;self.disk_files.add(path.name)
            except OSError:pass
        self.demand=set();self.misses={}
        try:
            saved=json.loads((self.folder/'misses.json').read_text())
            self.misses={url:at for url,at in saved.items() if image_url(url) and type(at) in (int,float) and 0<=time.time()-at<FAIL_TTL}
        except (OSError,ValueError,TypeError,AttributeError):pass

    def filename(self,url):return self.folder/(hashlib.sha256(url.encode()).hexdigest()+Path(url).suffix)

    def image(self,url):
        if not image_url(url):return QImage()
        if url in self.memory:self.memory.move_to_end(url);return self.memory[url]
        path=self.filename(url)
        try:
            if path.stat().st_size>MAX_BYTES:return QImage()
            image=decode(path.read_bytes())
            if not image.isNull():self.remember(url,image);return self.memory[url]
        except OSError:pass
        return QImage()

    def path(self,url):
        return self.filename(url) if image_url(url) and not self.image(url).isNull() else None

    def remember(self,url,image):
        # Keep source pixels: rescaling every icon to 64 and then down to 32
        # unnecessarily damaged small, non-square monster sprites.
        old=self.memory.pop(url,None)
        if old is not None:self.memory_bytes-=old.sizeInBytes()
        self.memory[url]=image;self.memory_bytes+=image.sizeInBytes()
        self.memory.move_to_end(url)
        while len(self.memory)>128 or self.memory_bytes>8*1024*1024:
            self.memory_bytes-=self.memory.popitem(last=False)[1].sizeInBytes()

    def observe(self,urls):
        if self.closed:return
        urls=list(dict.fromkeys(url for url in urls if image_url(url)))[:80];self.demand=set(urls)
        # The caller orders visible rows before nearby rows. Reorder queued work
        # on every scroll so yesterday's viewport cannot block today's icons.
        self.queue=deque()
        now=time.time()
        for url in urls:
            if url in self.active:continue
            path=self.path(url)
            if path is not None and 0<=now-path.stat().st_mtime<TTL:continue
            if 0<=now-self.misses.get(url,-FAIL_TTL)<FAIL_TTL:continue
            self.queue.append(url)
        for url,reply in list(self.active.items()):
            if url not in self.demand:
                reply._reference_cancelled=True;reply.abort()
        self.pump()

    def pump(self):
        while self.queue and len(self.active)<4 and not self.closed:
            url=self.queue.popleft();request=QNetworkRequest(QUrl(url));request.setTransferTimeout(10000)
            request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,QNetworkRequest.RedirectPolicy.SameOriginRedirectPolicy)
            request.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader,'Lupin (Classic World reference images)')
            reply=self.manager.get(request);reply.setReadBufferSize(MAX_BYTES+1);reply._reference_data=bytearray();self.active[url]=reply
            def receive(reply=reply):
                reply._reference_data.extend(bytes(reply.readAll()))
                if len(reply._reference_data)>MAX_BYTES:reply.abort()
            reply.readyRead.connect(receive);reply.finished.connect(lambda url=url,reply=reply:self.finish(url,reply))

    def finish(self,url,reply):
        self.active.pop(url,None)
        if self.closed:reply.deleteLater();return
        if getattr(reply,'_reference_cancelled',False):
            reply.deleteLater();self.pump();return
        data=bytes(reply._reference_data)+bytes(reply.readAll())
        image=decode(data) if reply.error()==QNetworkReply.NetworkError.NoError else QImage()
        if image.isNull():
            self.misses[url]=time.time();self.misses=dict(sorted(self.misses.items(),key=lambda r:r[1],reverse=True)[:512])
        else:
            self.remember(url,image);self.misses.pop(url,None)
            try:
                path=self.filename(url);old_size=path.stat().st_size if path.exists() else 0
                temporary=path.with_suffix('.tmp');temporary.write_bytes(data);temporary.replace(path)
                self.disk_bytes+=len(data)-old_size;self.disk_files.add(path.name)
                if self.disk_bytes>64*1024*1024 or len(self.disk_files)>1024 or time.monotonic()-self.disk_checked>30:
                    self.disk_checked=time.monotonic()
                    files=sorted([*self.folder.glob('*.png'),*self.folder.glob('*.webp')],key=lambda p:p.stat().st_mtime,reverse=True)
                    total=0;kept=set()
                    for index,path in enumerate(files):
                        total+=path.stat().st_size
                        if index>=1024 or total>64*1024*1024:path.unlink(missing_ok=True)
                        else:kept.add(path.name)
                    self.disk_files=kept;self.disk_bytes=sum(path.stat().st_size for path in files if path.name in kept)
            except OSError:pass
        try:(self.folder/'misses.json').write_text(json.dumps(self.misses))
        except OSError:pass
        reply.deleteLater();self.ready.emit(url);self.pump()

    def close(self):
        self.closed=True;self.queue.clear()
        for reply in list(self.active.values()):reply.abort();reply.deleteLater()
        self.active.clear()


class ReferenceSprite(QWidget):
    def __init__(self,media,parent=None):
        super().__init__(parent);self.media=media;self.movie=None;self.url='';self.icon='';self.active=False;self.image=QImage()
        self.setFixedSize(56,56);self.setAccessibleName('Reference image')
        media.ready.connect(self.received)

    def set_source(self,icon,animation=''):
        target=animation or icon
        if target==self.url and icon==self.icon:self.sync();return
        if self.movie:self.movie.stop();self.movie.deleteLater();self.movie=None
        self.url=target;self.icon=icon;self.image=self.media.image(icon);self.received(target);self.update()

    def received(self,url):
        if url not in (self.url,self.icon):return
        self.image=self.media.image(self.icon)
        if url==self.url:
            path=self.media.path(url)
            if path is not None:
                if self.movie:self.movie.stop();self.movie.deleteLater()
                self.movie=QMovie(str(path),parent=self);self.movie.setCacheMode(QMovie.CacheMode.CacheNone)
                self.movie.frameChanged.connect(lambda *_:self.update());self.movie.jumpToFrame(0)
        self.sync();self.update()

    def sync(self):
        if self.movie:
            if self.active and enabled(self):
                if self.movie.state()==QMovie.MovieState.NotRunning:self.movie.start()
                else:self.movie.setPaused(False)
            else:self.movie.setPaused(True)

    def showEvent(self,event):
        super().showEvent(event);self.window().installEventFilter(self);self.sync()

    def hideEvent(self,event):
        if self.movie:self.movie.setPaused(True)
        super().hideEvent(event)

    def eventFilter(self,watched,event):
        if event.type() in (QEvent.Type.WindowStateChange,QEvent.Type.Show,QEvent.Type.Hide):self.sync()
        return False

    def paintEvent(self,event):
        image=self.movie.currentImage() if self.movie else self.image
        painter=QPainter(self)
        if image.isNull():
            painter.setPen(QColor('#728198'));painter.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'—');return
        size=image.size()
        # Integer enlargement keeps small skill/item icons crisp; large mobs fit.
        limit=self.width()-8;factor=min(2,limit//max(size.width(),size.height()))
        if factor>=1:size*=factor
        else:size=size.scaled(QSize(limit,limit),Qt.AspectRatioMode.KeepAspectRatio)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform,factor<1)
        painter.drawImage(QRect((self.width()-size.width())//2,(self.height()-size.height())//2,size.width(),size.height()),image)
