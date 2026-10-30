"""A small minimap; markers require independently verified image coordinates."""
from PySide6.QtCore import Qt,QRectF,Signal
from PySide6.QtGui import QBitmap,QColor,QPainter,QPen,QRegion
from PySide6.QtWidgets import QWidget,QToolTip


class MapPreview(QWidget):
    chosen=Signal(int)

    def __init__(self,media,row,parent=None):
        super().__init__(parent);self.media=media;self.row=row;self.geometry_proof=None;self.markers=[];self.names={}
        self.setFixedHeight(128);self.setMouseTracking(True);self.setAccessibleName('Map minimap and verified spawn positions')

    def set_geometry(self,proof,names=None):
        self.geometry_proof=proof;self.names=names or {};self.update()

    def source_bounds(self,image):
        key=image.cacheKey()
        if key!=getattr(self,'_image_key',None):
            self._image_key=key;self._source=image.rect()
            if image.hasAlphaChannel():
                bounds=QRegion(QBitmap.fromImage(image.createAlphaMask())).boundingRect()
                if not bounds.isEmpty():self._source=bounds.adjusted(-2,-2,2,2).intersected(image.rect())
        return self._source

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing,True)
        painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor('#202a38'));painter.drawRoundedRect(self.rect(),8,8)
        image=self.media.image(self.row.get('minimap_url',''));self.markers=[]
        if image.isNull():
            painter.setPen(QColor('#93a5bd'));painter.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'Minimap loading…');return
        source=self.source_bounds(image);size=source.size();size.scale(self.width()-20,self.height()-20,Qt.AspectRatioMode.KeepAspectRatio)
        target=QRectF((self.width()-size.width())/2,(self.height()-size.height())/2,size.width(),size.height())
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform,False);painter.drawImage(target,image,QRectF(source))
        proof=self.geometry_proof
        if not proof or not proof.get('projection_verified'):return
        if abs((image.width()/image.height())/(proof['width']/proof['height'])-1)>.025:return
        for point in self.row.get('mobs',[]):
            if point.get('mob_id') not in self.names:continue
            x=((point['x']+proof['dx'])/proof['width']*image.width()-source.x())/source.width()
            y=((point['y']+proof['dy'])/proof['height']*image.height()-source.y())/source.height()
            if not (0<=x<=1 and 0<=y<=1):continue
            center=target.topLeft();center.setX(target.x()+x*target.width());center.setY(target.y()+y*target.height())
            painter.setPen(QPen(QColor('#171c25'),1.5));painter.setBrush(QColor('#ffc66f'));painter.drawEllipse(center,3.5,3.5)
            self.markers.append((center,point['mob_id']))

    def target_at(self,point):
        return next((identity for center,identity in self.markers if (center-point).manhattanLength()<9),None)

    def mouseMoveEvent(self,event):
        identity=self.target_at(event.position());self.setCursor(Qt.CursorShape.PointingHandCursor if identity else Qt.CursorShape.ArrowCursor)
        if identity:QToolTip.showText(event.globalPosition().toPoint(),self.names[identity],self)
        else:QToolTip.hideText()

    def mousePressEvent(self,event):
        identity=self.target_at(event.position())
        if identity and event.button()==Qt.MouseButton.LeftButton:self.chosen.emit(identity)
