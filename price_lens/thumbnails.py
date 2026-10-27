"""Bounded, cached Classic World item images. Separate from price API demand."""
from collections import OrderedDict,deque
import json
from pathlib import Path
import struct
import time

from PySide6.QtCore import QObject,QUrl,QTimer,Signal,QSize,QRectF,QVariantAnimation,Qt
from PySide6.QtGui import QImage,QPainter,QColor,QPen
from PySide6.QtNetwork import QNetworkAccessManager,QNetworkRequest,QNetworkReply
from PySide6.QtWidgets import QWidget
from .motion import enabled

BASE='https://osmsdataexplorer.com/data/current/images/items/'
TTL=30*86400
FAIL_TTL=6*3600
MAX_BYTES=256*1024


def source_url(item_id):
    if not isinstance(item_id,int) or isinstance(item_id,bool) or not 1<=item_id<=99999999:raise ValueError('Invalid item ID')
    return BASE+f'{item_id:08d}.png'


def decode(data):
    if len(data)<24 or len(data)>MAX_BYTES or data[:8]!=b'\x89PNG\r\n\x1a\n':return QImage()
    width,height=struct.unpack('>II',data[16:24])
    if not 1<=width<=512 or not 1<=height<=512:return QImage()
    return QImage.fromData(data,'PNG')


class ThumbnailCache(QObject):
    ready=Signal(int)

    def __init__(self,folder,parent=None,base_url=None):
        super().__init__(parent);self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True)
        self.base_url=base_url;self.manager=QNetworkAccessManager(self)
        self.memory=OrderedDict();self.queue=deque();self.active={};self.demand=set();self.closed=False
        self.misses={}
        try:
            raw=json.loads((self.folder/'misses.json').read_text())
            self.misses={int(k):float(v) for k,v in raw.items() if 0<=time.time()-float(v)<FAIL_TTL}
        except (OSError,ValueError,TypeError,AttributeError):pass

    def image(self,item_id):
        if item_id in self.memory:
            self.memory.move_to_end(item_id);return self.memory[item_id][0]
        path=self.folder/f'{item_id}.png'
        try:
            if path.stat().st_size>MAX_BYTES:return QImage()
            image=decode(path.read_bytes())
            if not image.isNull():self.remember(item_id,image,path.stat().st_mtime);return image
        except OSError:pass
        return QImage()

    def remember(self,item_id,image,at):
        self.memory[item_id]=(image,at);self.memory.move_to_end(item_id)
        while len(self.memory)>96:self.memory.popitem(last=False)

    def observe(self,items):
        if self.closed:return
        ids=list(dict.fromkeys(item.game_id for item in items))[:16];self.demand=set(ids)
        self.queue=deque(i for i in self.queue if i in self.demand)
        now=time.time()
        for item_id in ids:
            if item_id in self.active or item_id in self.queue:continue
            self.image(item_id)
            if item_id in self.memory and 0<=now-self.memory[item_id][1]<TTL:continue
            if 0<=now-self.misses.get(item_id,-FAIL_TTL)<FAIL_TTL:continue
            self.queue.append(item_id)
        self.pump()

    def pump(self):
        while self.queue and len(self.active)<2 and not self.closed:
            item_id=self.queue.popleft()
            url=(self.base_url+f'{item_id:08d}.png') if self.base_url else source_url(item_id)
            request=QNetworkRequest(QUrl(url));request.setTransferTimeout(8000)
            request.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader,'Lupin (Classic World item thumbnails)')
            reply=self.manager.get(request);reply.setReadBufferSize(MAX_BYTES+1);reply._image_data=bytearray()
            self.active[item_id]=reply
            def receive(reply=reply):
                reply._image_data.extend(bytes(reply.readAll()))
                if len(reply._image_data)>MAX_BYTES:reply.abort()
            reply.readyRead.connect(receive)
            reply.finished.connect(lambda item_id=item_id,reply=reply:self.finish(item_id,reply))

    def finish(self,item_id,reply):
        self.active.pop(item_id,None)
        if self.closed:reply.deleteLater();return
        data=bytes(reply._image_data)+bytes(reply.readAll())
        image=decode(data) if reply.error()==QNetworkReply.NetworkError.NoError else QImage()
        if image.isNull():
            self.misses[item_id]=time.time()
            self.misses=dict(sorted(self.misses.items(),key=lambda p:p[1],reverse=True)[:512])
            try:(self.folder/'misses.json').write_text(json.dumps(self.misses))
            except OSError:pass
        else:
            self.remember(item_id,image,time.time());self.misses.pop(item_id,None)
            try:
                path=self.folder/f'{item_id}.png';temporary=path.with_suffix('.tmp');temporary.write_bytes(data);temporary.replace(path)
                files=sorted(self.folder.glob('*.png'),key=lambda p:p.stat().st_mtime,reverse=True)
                for old in files[512:]:old.unlink(missing_ok=True)
            except OSError:pass
        reply.deleteLater();self.ready.emit(item_id);self.pump()

    def close(self):
        self.closed=True;self.queue.clear()
        for reply in list(self.active.values()):reply.abort();reply.deleteLater()
        self.active.clear()


class ItemImage(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.setFixedSize(42,42);self.image=QImage();self.alpha=1.0
        self.animation=QVariantAnimation(self);self.animation.setDuration(120)
        self.animation.valueChanged.connect(self.advance)
        self.setToolTip('Classic World item image')

    def advance(self,value):self.alpha=float(value);self.update()

    def set_image(self,image):
        if self.image.cacheKey()==image.cacheKey():return
        self.animation.stop();self.image=image
        if enabled(self) and not image.isNull():self.animation.setStartValue(0.0);self.animation.setEndValue(1.0);self.animation.start()
        else:self.alpha=1.0
        self.update()

    def paintEvent(self,event):
        painter=QPainter(self);painter.setPen(QColor('#3c4b5f'));painter.setBrush(QColor('#222c3b'));painter.drawRoundedRect(self.rect().adjusted(1,1,-1,-1),5,5)
        if self.image.isNull():
            painter.setPen(QColor('#718097'));painter.drawRect(14,12,14,17);painter.drawLine(14,24,19,19);painter.drawLine(19,19,28,26)
        else:
            size=self.image.size().scaled(QSize(32,32),Qt.AspectRatioMode.KeepAspectRatio)
            painter.setOpacity(self.alpha);painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform,False)
            painter.drawImage(QRectF((42-size.width())/2,(42-size.height())/2,size.width(),size.height()),self.image)

    def hideEvent(self,event):self.animation.stop();self.alpha=1.0;super().hideEvent(event)
