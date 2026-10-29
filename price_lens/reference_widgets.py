"""Stable reference rows, nearby-image demand and interruptible navigation."""
from pathlib import Path
from PySide6.QtCore import QSize,Qt,Signal
from PySide6.QtGui import QColor,QFont,QFontMetrics,QIcon,QImage,QPainter,QPixmap,QTextLayout,QTextOption
from PySide6.QtWidgets import QListWidget,QListWidgetItem,QWidget,QStyledItemDelegate,QStyle
from .motion import ContentArea,enabled


def thumbnail(media,url,size=32,dpr=1.0):
    image=QImage(str(Path(__file__).parent/'resources/meso.svg')) if url==':meso' else media.image(url);pixels=round(size*dpr)
    if url==':meso':image=image.scaled(QSize(round(16*dpr),round(16*dpr)),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.FastTransformation)
    tile=QPixmap(pixels,pixels);tile.fill(Qt.GlobalColor.transparent);painter=QPainter(tile)
    if image.isNull():
        painter.setPen(QColor('#687b95'));margin=round(pixels*.27)
        painter.drawRoundedRect(margin,margin,pixels-2*margin,pixels-2*margin,3,3)
    else:
        bounds=QSize(pixels,pixels)
        if image.width()>pixels or image.height()>pixels:
            image=image.scaled(bounds,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
        else:
            factor=1 if url==':meso' else max(1,min(pixels//image.width(),pixels//image.height()))
            image=image.scaled(image.size()*factor,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.FastTransformation)
        painter.drawImage((pixels-image.width())//2,(pixels-image.height())//2,image)
    painter.end();tile.setDevicePixelRatio(dpr);icon=QIcon(tile);icon.addPixmap(tile,QIcon.Mode.Disabled);return icon


class DropDelegate(QStyledItemDelegate):
    def paint(self,painter,option,index):
        record=index.data(Qt.ItemDataRole.UserRole+3) or {};rect=option.rect.adjusted(2,2,-2,-2)
        painter.save();painter.setRenderHint(QPainter.RenderHint.Antialiasing,True)
        selected=bool(option.state & QStyle.StateFlag.State_Selected);hovered=bool(option.state & QStyle.StateFlag.State_MouseOver)
        painter.setPen(QColor('#718098' if selected else '#475970' if hovered else '#2e3b4e'))
        painter.setBrush(QColor('#303d51' if selected else '#29374b' if hovered else '#202a38'));painter.drawRoundedRect(rect,8,8)
        icon=index.data(Qt.ItemDataRole.DecorationRole)
        if isinstance(icon,QIcon):painter.drawPixmap(rect.left()+8,rect.top()+10,icon.pixmap(32,32))
        left=rect.left()+48;width=max(20,rect.width()-56);top=rect.top()+9
        font=QFont(option.font);font.setPixelSize(11);painter.setFont(font);metrics=QFontMetrics(font)
        name=record.get('name','');layout=QTextLayout(name,font);wrap=QTextOption();wrap.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere);layout.setTextOption(wrap)
        layout.beginLayout();line=layout.createLine();line.setLineWidth(width);length=line.textLength();layout.endLayout()
        painter.setPen(QColor('#e6d9c4' if selected else '#d9e2ef'))
        painter.drawText(left,top+metrics.ascent(),name[:length].rstrip())
        if length<len(name):painter.drawText(left,top+metrics.height()+metrics.ascent(),metrics.elidedText(name[length:].strip(),Qt.TextElideMode.ElideRight,width))
        caption=record.get('rate') or record.get('subtitle','');font.setPixelSize(10);painter.setFont(font);painter.setPen(QColor('#dfbd86'))
        painter.drawText(left,rect.bottom()-10,QFontMetrics(font).elidedText(caption,Qt.TextElideMode.ElideRight,width));painter.restore()


class ReferenceList(QListWidget):
    chosen=Signal(object)
    viewport_changed=Signal()

    def __init__(self,media,parent=None,*,tiles=False,drop_tiles=False):
        super().__init__(parent);self.media=media;self.tiles=tiles or drop_tiles;self.drop_tiles=drop_tiles;self.records=[];self.current_structure=()
        self.icon_size=40 if tiles and not drop_tiles else 32
        self.setIconSize(QSize(self.icon_size,self.icon_size));self.setSpacing(5 if self.tiles else 3)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet('QListWidget{background:transparent;border:0;} QListWidget::item{background:#202a38;padding:8px;border:1px solid transparent;border-radius:8px;} QListWidget::item:hover{background:#29374b;border-color:#475970;} QListWidget::item:selected{background:#303d51;border-color:#718098;color:#f1e1c6;}')
        if self.tiles:
            self.setViewMode(QListWidget.ViewMode.IconMode);self.setResizeMode(QListWidget.ResizeMode.Adjust)
            self.setMovement(QListWidget.Movement.Static);self.setWordWrap(True)
        if drop_tiles:self.setItemDelegate(DropDelegate(self));self.setMouseTracking(True)
        self.itemClicked.connect(self.activate_row);self.itemActivated.connect(self.activate_row)
        self.verticalScrollBar().valueChanged.connect(lambda *_:self.viewport_changed.emit())

    def activate_row(self,item):
        if item and item.data(Qt.ItemDataRole.UserRole) is not None:self.chosen.emit(item.data(Qt.ItemDataRole.UserRole))

    def populate(self,records):
        """Update matching rows in place; imagery arriving later never reflows them."""
        structure=tuple(repr(r['key']) for r in records);old={self.item(i).data(Qt.ItemDataRole.UserRole+2):self.item(i) for i in range(self.count())}
        self.blockSignals(True)
        for key,item in list(old.items()):
            if key not in structure:self.takeItem(self.row(item));old.pop(key)
        for index,record in enumerate(records):
            key=repr(record['key']);item=old.get(key)
            if item is None:item=QListWidgetItem();self.insertItem(index,item)
            elif self.row(item)!=index:self.takeItem(self.row(item));self.insertItem(index,item)
            caption=record['name']+('\n'+record['subtitle'] if record.get('subtitle') else '')
            if item.text()!=caption:item.setText(caption)
            prior=item.data(Qt.ItemDataRole.UserRole+1)
            if prior!=record.get('icon',''):item.setIcon(thumbnail(self.media,record.get('icon',''),self.icon_size,self.devicePixelRatioF()))
            item.setData(Qt.ItemDataRole.UserRole,record.get('target'));item.setData(Qt.ItemDataRole.UserRole+1,record.get('icon',''))
            item.setData(Qt.ItemDataRole.UserRole+2,key);item.setToolTip(record.get('tip') or record['name'])
            item.setData(Qt.ItemDataRole.UserRole+3,record)
            if self.tiles:
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter);item.setSizeHint(QSize(max(110,self.gridSize().width()-10),86 if self.drop_tiles else 94))
            else:item.setSizeHint(QSize(0,58 if record.get('subtitle') else 43))
        self.records=records;self.current_structure=structure;self.blockSignals(False);self.viewport_changed.emit()

    def nearby_urls(self):
        viewport=self.viewport().rect();near=viewport.adjusted(0,-viewport.height(),0,2*viewport.height());visible=[];prefetch=[]
        for i in range(self.count()):
            item=self.item(i);rect=self.visualItemRect(item);url=item.data(Qt.ItemDataRole.UserRole+1)
            if not url:continue
            if rect.intersects(viewport):visible.append(url)
            elif rect.intersects(near):prefetch.append((abs(rect.center().y()-viewport.center().y()),url))
        return visible+[url for distance,url in sorted(prefetch)]

    def image_ready(self,url):
        for index in range(self.count()):
            item=self.item(index)
            if item.data(Qt.ItemDataRole.UserRole+1)==url:item.setIcon(thumbnail(self.media,url,self.icon_size,self.devicePixelRatioF()))

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if self.tiles:
            width=max(120,(self.viewport().width()-18)//2);self.setGridSize(QSize(width,91 if self.drop_tiles else 99))
            for i in range(self.count()):self.item(i).setSizeHint(QSize(width-10,86 if self.drop_tiles else 94))
        self.viewport_changed.emit()


class _Slide(QWidget):
    def __init__(self,before,after,direction,parent):
        super().__init__(parent);self.before=before;self.after=after;self.direction=direction;self.progress=0.0
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self,event):
        painter=QPainter(self);offset=round(self.width()*self.progress)*self.direction
        painter.drawPixmap(-offset,0,self.before);painter.drawPixmap(self.direction*self.width()-offset,0,self.after)


class BrowserContent(ContentArea):
    def complete(self,direction=0):
        if not direction:self.animation.setDuration(150);return super().complete()
        pixels=self.before;self.before=None
        if pixels is None or not enabled(self):return
        if self.layout():self.layout().activate()
        self.outgoing=_Slide(pixels,self.grab(),direction,self);self.outgoing.setGeometry(self.rect())
        self.outgoing.show();self.outgoing.raise_();self.animation.setDuration(230)
        self.animation.setStartValue(0.0);self.animation.setEndValue(1.0);self.animation.start()
