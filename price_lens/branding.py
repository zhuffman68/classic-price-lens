"""Native-timed, pixel-crisp Lupin animations and a local vector wordmark."""
from PySide6.QtCore import QEvent,QRectF,QSize,Qt,QTimer
from PySide6.QtGui import QMovie,QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QHBoxLayout,QWidget

from .motion import enabled


class Sprite(QWidget):
    def __init__(self,path,parent=None):
        super().__init__(parent)
        self.setFixedSize(80,68)
        self.movie=QMovie(str(path),parent=self)
        self.movie.setCacheMode(QMovie.CacheMode.CacheAll)
        self.movie.jumpToFrame(0)
        self.movie.frameChanged.connect(lambda *_:self.update())
        self.attack=QMovie(str(path.with_name("lupin-attack.gif")),parent=self)
        self.attack.setCacheMode(QMovie.CacheMode.CacheAll)
        self.attack.jumpToFrame(0)
        self.current=self.movie
        self.loops=0
        self.previous=-1
        self.movie.frameChanged.connect(self.walk_frame)
        self.attack.frameChanged.connect(self.attack_frame)
        self.setAccessibleName("Animated Lupin")

    def walk_frame(self,frame):
        if frame==0 and self.previous>0:
            self.loops+=1
            if self.loops>=18 and self.attack.isValid():
                self.loops=0;QTimer.singleShot(0,self.throw)
        self.previous=frame

    def throw(self):
        if not enabled(self):return
        self.movie.setPaused(True);self.current=self.attack;self.attack.start();self.update()

    def attack_frame(self,frame):
        self.update()
        if self.current is self.attack and frame==0 and getattr(self,"last_attack",-1)>0:
            QTimer.singleShot(0,self.walk)
        self.last_attack=frame

    def walk(self):
        self.attack.stop();self.last_attack=-1;self.current=self.movie
        if enabled(self):self.movie.setPaused(False)
        self.update()

    def paintEvent(self,event):
        image=self.current.currentImage()
        if image.isNull():return
        painter=QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform,False)
        painter.drawImage((self.width()-image.width())//2,max(0,self.height()-image.height()),image)


class Wordmark(QWidget):
    def __init__(self,path,parent=None):
        super().__init__(parent)
        self.renderer=QSvgRenderer(str(path),self)
        self.setFixedSize(self.renderer.defaultSize())
        self.setAccessibleName("Lupin")

    def paintEvent(self,event):
        painter=QPainter(self)
        self.renderer.render(painter,QRectF(self.rect()))


class Brand(QWidget):
    def __init__(self,root,parent=None):
        super().__init__(parent)
        self.setFixedHeight(68)
        layout=QHBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(8)
        self.sprite=Sprite(root/"price_lens/resources/lupin.gif",self)
        layout.addWidget(self.sprite)
        layout.addWidget(Wordmark(root/"price_lens/resources/wordmark.svg",self))
        layout.addStretch()
        if parent:parent.installEventFilter(self)

    def sync(self):
        if enabled(self):
            if self.sprite.current.state()==QMovie.MovieState.NotRunning:self.sprite.current.start()
            else:self.sprite.current.setPaused(False)
        else:
            self.sprite.movie.setPaused(True);self.sprite.attack.setPaused(True)

    def showEvent(self,event):
        super().showEvent(event);self.sync()

    def hideEvent(self,event):
        self.sprite.movie.setPaused(True);self.sprite.attack.setPaused(True);super().hideEvent(event)

    def eventFilter(self,watched,event):
        if event.type() in (QEvent.Type.WindowStateChange,QEvent.Type.Show,QEvent.Type.Hide):self.sync()
        return False
