"""Local, pixel-crisp Lupin animation and a MapleStory-font vector wordmark."""
from PySide6.QtCore import QEvent,QRectF,QSize,Qt
from PySide6.QtGui import QMovie,QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QHBoxLayout,QWidget

from .motion import enabled


class Sprite(QWidget):
    def __init__(self,path,parent=None):
        super().__init__(parent)
        self.setFixedSize(72,60)
        self.movie=QMovie(str(path),parent=self)
        self.movie.setCacheMode(QMovie.CacheMode.CacheAll)
        self.movie.jumpToFrame(0)
        self.movie.frameChanged.connect(lambda *_:self.update())
        self.setAccessibleName("Animated Lupin")

    def paintEvent(self,event):
        image=self.movie.currentImage()
        if image.isNull():return
        painter=QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform,False)
        painter.drawImage((self.width()-image.width())//2,(self.height()-image.height())//2,image)


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
        self.setFixedHeight(60)
        layout=QHBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(8)
        self.sprite=Sprite(root/"price_lens/resources/lupin.webp",self)
        layout.addWidget(self.sprite)
        layout.addWidget(Wordmark(root/"price_lens/resources/wordmark.svg",self))
        layout.addStretch()
        if parent:parent.installEventFilter(self)

    def sync(self):
        if enabled(self):
            if self.sprite.movie.state()==QMovie.MovieState.NotRunning:self.sprite.movie.start()
            else:self.sprite.movie.setPaused(False)
        else:self.sprite.movie.setPaused(True)

    def showEvent(self,event):
        super().showEvent(event);self.sync()

    def hideEvent(self,event):
        self.sprite.movie.setPaused(True);super().hideEvent(event)

    def eventFilter(self,watched,event):
        if event.type() in (QEvent.Type.WindowStateChange,QEvent.Type.Show,QEvent.Type.Hide):self.sync()
        return False
