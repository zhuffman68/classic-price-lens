"""Stable reference rows, nearby-image demand and interruptible navigation."""
from pathlib import Path
from PySide6.QtCore import QSize,Qt,Signal,QRectF,QPointF
from PySide6.QtGui import QColor,QFont,QFontMetrics,QIcon,QImage,QPainter,QPixmap,QTextLayout,QTextOption
from PySide6.QtWidgets import QListWidget,QListWidgetItem,QWidget,QStyledItemDelegate,QStyle
from .motion import ContentArea,enabled
from . import gui_currency
from .number_motion import NumberRoll


def thumbnail(media,url,size=32,dpr=1.0):
    image=QImage(str(Path(__file__).parent/'resources/meso.svg')) if url==':meso' else media.image(url);pixels=round(size*dpr)
    if url==':meso':image=image.scaled(QSize(round(16*dpr),round(16*dpr)),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.FastTransformation)
    tile=QPixmap(pixels,pixels);tile.fill(Qt.GlobalColor.transparent);painter=QPainter(tile)
    if image.isNull():
        painter.setPen(QColor('#bdab86'));unit=pixels/32
        # An open reference book stays recognizable even without remote artwork.
        for side in (-1,1):
            center=16*unit;edge=center+side*9*unit
            painter.drawLine(QPointF(center,10*unit),QPointF(edge,8*unit));painter.drawLine(QPointF(edge,8*unit),QPointF(edge,23*unit))
            painter.drawLine(QPointF(edge,23*unit),QPointF(center,25*unit));painter.drawLine(QPointF(center,10*unit),QPointF(center,25*unit))
    else:
        bounds=QSize(pixels,pixels)
        if image.width()>pixels or image.height()>pixels:
            image=image.scaled(bounds,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
        else:
            factor=1 if url==':meso' else max(1,min(pixels//image.width(),pixels//image.height()))
            image=image.scaled(image.size()*factor,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.FastTransformation)
        painter.drawImage((pixels-image.width())//2,(pixels-image.height())//2,image)
    painter.end();tile.setDevicePixelRatio(dpr);icon=QIcon(tile);icon.addPixmap(tile,QIcon.Mode.Disabled);return icon


def row_surface(painter,option,rect):
    selected=bool(option.state & QStyle.StateFlag.State_Selected);hover=bool(option.state & QStyle.StateFlag.State_MouseOver)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QColor('#788494' if selected else '#4b5b70') if selected or hover else Qt.PenStyle.NoPen)
    painter.setBrush(QColor('#303d50' if selected else '#29364a' if hover else '#202a38'));painter.drawRoundedRect(rect,8,8)
    return selected


def wrapped_name(painter,font,rect,name):
    painter.setFont(font);layout=QTextLayout(name,font);wrap=QTextOption();wrap.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere);layout.setTextOption(wrap)
    layout.beginLayout()
    for index in range(2):
        line=layout.createLine()
        if not line.isValid():break
        line.setLineWidth(rect.width());line.setPosition(QPointF(0,index*15))
    layout.endLayout();painter.save();painter.setClipRect(rect);layout.draw(painter,rect.topLeft());painter.restore()


class CategoryDelegate(QStyledItemDelegate):
    def paint(self,painter,option,index):
        record=index.data(Qt.ItemDataRole.UserRole+3) or {};rect=QRectF(option.rect.adjusted(2,2,-2,-2));painter.save()
        selected=row_surface(painter,option,rect);icon=index.data(Qt.ItemDataRole.DecorationRole)
        if isinstance(icon,QIcon):painter.drawPixmap(round(rect.left()+10),round(rect.center().y()-16),icon.pixmap(32,32))
        left=rect.left()+52;width=max(20,rect.width()-60);font=QFont(option.font);font.setPixelSize(12);font.setWeight(QFont.Weight.Medium)
        painter.setPen(QColor('#f0dbb8' if selected else '#dfe7f2'));wrapped_name(painter,font,QRectF(left,rect.top()+8,width,31),record.get('name',''))
        font.setPixelSize(10);font.setWeight(QFont.Weight.Normal);painter.setFont(font);caption=record.get('subtitle','')
        badge=QRectF(left,rect.bottom()-26,min(width,painter.fontMetrics().horizontalAdvance(caption)+12),18)
        painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor('#303e51'));painter.drawRoundedRect(badge,5,5)
        painter.setPen(QColor('#b9c9de'));painter.drawText(badge.adjusted(6,0,-4,0),Qt.AlignmentFlag.AlignVCenter,painter.fontMetrics().elidedText(caption,Qt.TextElideMode.ElideRight,round(badge.width()-10)));painter.restore()


class DropDelegate(QStyledItemDelegate):
    def paint(self,painter,option,index):
        record=index.data(Qt.ItemDataRole.UserRole+3) or {};rect=option.rect.adjusted(2,2,-2,-2)
        painter.save();painter.setRenderHint(QPainter.RenderHint.Antialiasing,True)
        selected=row_surface(painter,option,rect)
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
        painter.drawText(QRectF(left,rect.bottom()-24,width,17),Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter,QFontMetrics(font).elidedText(caption,Qt.TextElideMode.ElideRight,width));painter.restore()


class SourceDelegate(QStyledItemDelegate):
    """Keep the second line close to its title, independent of native metrics."""
    def paint(self,painter,option,index):
        record=index.data(Qt.ItemDataRole.UserRole+3) or {};rect=option.rect.adjusted(1,1,-1,-1)
        painter.save();painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        selected=row_surface(painter,option,rect)
        icon=index.data(Qt.ItemDataRole.DecorationRole)
        if isinstance(icon,QIcon):painter.drawPixmap(rect.left()+7,rect.top()+(rect.height()-32)//2,icon.pixmap(32,32))
        trailing=record.get('trailing','');right=rect.right()-9
        if trailing:
            font=QFont(option.font);font.setPixelSize(11);font.setWeight(QFont.Weight.DemiBold);painter.setFont(font)
            occupied=min(rect.width()*.28,painter.fontMetrics().horizontalAdvance(trailing)+12);painter.setPen(QColor('#e8cca1'))
            painter.drawText(QRectF(right-occupied,rect.top(),occupied,rect.height()),Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter,trailing);right-=occupied+6
        elif record.get('target'):
            painter.setPen(QColor('#899fb9'));painter.drawText(QRectF(right-10,rect.top(),10,rect.height()),Qt.AlignmentFlag.AlignVCenter,'›');right-=14
        left=rect.left()+48;width=max(10,right-left);font=QFont(option.font);font.setPixelSize(12);painter.setFont(font)
        top=rect.top()+(9 if record.get('subtitle') else (rect.height()-16)//2)
        painter.setPen(QColor('#e4dfd4' if selected else '#d9e2ef'))
        painter.drawText(QRectF(left,top,width,15),Qt.AlignmentFlag.AlignVCenter,painter.fontMetrics().elidedText(record.get('name',''),Qt.TextElideMode.ElideRight,width))
        if record.get('subtitle'):
            font.setPixelSize(10);painter.setFont(font);painter.setPen(QColor('#adbed3'))
            caption=gui_currency.visual_text(record['subtitle']);roll=NumberRoll(caption)
            roll.paint(painter,QRectF(left,top+15,width,14),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,gui_currency.paint_icon)
        painter.restore()


class ReferenceList(QListWidget):
    chosen=Signal(object)
    viewport_changed=Signal()

    def __init__(self,media,parent=None,*,tiles=False,drop_tiles=False):
        super().__init__(parent);self.media=media;self.tiles=tiles or drop_tiles;self.drop_tiles=drop_tiles;self.records=[];self.current_structure=()
        self.icon_size=32
        self.setIconSize(QSize(self.icon_size,self.icon_size));self.setSpacing(5 if self.tiles else 3)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet('QListWidget{background:transparent;border:0;} QListWidget::item{background:#202a38;padding:8px;border:1px solid transparent;border-radius:8px;} QListWidget::item:hover{background:#29374b;border-color:#475970;} QListWidget::item:selected{background:#303d51;border-color:#718098;color:#f1e1c6;}')
        if self.tiles:
            self.setViewMode(QListWidget.ViewMode.IconMode);self.setResizeMode(QListWidget.ResizeMode.Adjust)
            self.setMovement(QListWidget.Movement.Static);self.setWordWrap(True)
        if drop_tiles:self.setItemDelegate(DropDelegate(self))
        elif self.tiles:self.setItemDelegate(CategoryDelegate(self))
        else:self.setItemDelegate(SourceDelegate(self))
        self.setMouseTracking(True)
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
                item.setTextAlignment(Qt.AlignmentFlag.AlignLeft);item.setSizeHint(QSize(max(110,self.gridSize().width()-10),86 if self.drop_tiles else 76))
            else:item.setSizeHint(QSize(0,54 if record.get('subtitle') else 42))
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
            width=max(120,(self.viewport().width()-18)//2);self.setGridSize(QSize(width,91 if self.drop_tiles else 81))
            for i in range(self.count()):self.item(i).setSizeHint(QSize(width-10,86 if self.drop_tiles else 76))
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
