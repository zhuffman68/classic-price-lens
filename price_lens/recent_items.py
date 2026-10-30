"""Bounded session-only sightings; no frames, disk history or market requests."""
from collections import OrderedDict
from copy import deepcopy
import math
import time
from PySide6.QtCore import Qt,QSize,QRectF,QRect,QPoint,QObject,QTimer,Signal,QVariantAnimation,QEasingCurve
from PySide6.QtGui import QColor,QFont,QIcon,QPixmap,QPainter,QRegion
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QListWidget,QListWidgetItem,QPushButton,QStyledItemDelegate,QStyle,QStyleOptionViewItem
from .motion import MotionLabel,enabled
from .domain import age_text,compare
from .gui_currency import paint_icon
from .number_motion import NumberRoll


class ActiveCards(QObject):
    """GUI-only retention; never supplies screen labels or verified offers."""
    changed=Signal()
    grace=2.0

    def __init__(self,parent=None):
        super().__init__(parent);self.groups={True:(),False:()};self.actual={True:(),False:()};self.deadlines={};self.due=None
        self.context=None;self.page=None
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.changed.emit)

    @staticmethod
    def slot(row,index):
        slot=row.get('shop_slot')
        return (row.get('shop_page'),tuple(slot)) if slot is not None else ('row',index,row.get('name'),row.get('tier'))

    def discard(self,hovered):
        self.groups[hovered]=()
        for key in list(self.deadlines):
            if key[0]==hovered:self.deadlines.pop(key)

    def observe(self,rows,tooltip,*,retain=True,now=None,context=None,page=None,identity=None):
        now=time.monotonic() if now is None else now
        incoming={True:(tooltip,) if tooltip else (),False:tuple(rows)}
        if self.context is not None and context!=self.context:
            self.discard(True);self.discard(False)
        if self.page is not None and page!=self.page:self.discard(False)
        self.context=context;self.page=page
        valid=identity or (lambda row:bool(row.get('name')))
        signatures={hovered:tuple((identity(row) if identity else (row.get('name'),row.get('tier')),row.get('shop_page'),tuple(row['shop_slot']) if row.get('shop_slot') is not None else None) for row in current if valid(row))
                    for hovered,current in incoming.items()}
        # A newly seen item can replace a disappearing item across contexts too;
        # an already-present shop must not cancel an inventory card's grace.
        for hovered in (True,False):
            if set(signatures[hovered])-set(self.actual[hovered]) and not incoming[not hovered]:self.discard(not hovered)
        self.actual=signatures
        for hovered,current in incoming.items():
            previous=self.groups[hovered]
            if current and hovered:self.discard(hovered)
            verified_slots=bool(current and not hovered and all(row.get('shop_slot') is not None for row in (*previous,*current))
                                and len({row.get('shop_page') for row in (*previous,*current)})==1)
            if current and not hovered and not verified_slots:self.discard(hovered);previous=()
            if verified_slots and retain:
                saved={self.slot(row,index):row for index,row in enumerate(previous)}
                usable=[]
                for index,row in enumerate(current):
                    slot=self.slot(row,index);old=saved.get(slot);key=(hovered,slot)
                    if old and valid(old) and not valid(row):
                        deadline=self.deadlines.setdefault(key,now+self.grace)
                        if now<deadline:continue
                    usable.append(row)
                current=tuple(usable)
            keyed={(hovered,True if hovered else self.slot(row,index)) for index,row in enumerate(current)}
            result=list(deepcopy(current))
            for key in keyed:self.deadlines.pop(key,None)
            if retain:
                for index,row in enumerate(previous):
                    key=(hovered,True if hovered else self.slot(row,index))
                    if key in keyed or hovered and current:continue
                    deadline=self.deadlines.setdefault(key,now+self.grace)
                    if now<deadline:result.append(row)
                    else:self.deadlines.pop(key,None)
            else:self.discard(hovered)
            self.groups[hovered]=tuple(sorted(result,key=lambda row:(row.get('area') or {}).get('y',0)) if verified_slots else result)
        due=min(self.deadlines.values(),default=None)
        if due!=self.due or due is not None and not self.timer.isActive():
            self.timer.stop();self.due=due
            if due is not None:self.timer.start(max(1,math.ceil((due-now)*1000)))
        return [(row,hovered) for hovered in (True,False) for row in self.groups[hovered]]


class RecentRows(QListWidget):
    """Paint only nearby rows, at their interpolated positions while moving."""
    row_height=59

    def __init__(self,parent=None):
        super().__init__(parent);self.motion={};self.progress=1.0;self.hovered=None;self.pressed=None

    @staticmethod
    def identity(item):
        row=item.data(Qt.ItemDataRole.UserRole) if item else None
        return row['item'].game_id if row else None

    def target_rect(self,item):return super().visualItemRect(item)

    def visualItemRect(self,item):
        rect=self.target_rect(item);motion=self.motion.get(self.identity(item))
        if motion:rect.translate(0,round(motion[0]*(1-self.progress)))
        return rect

    def opacity(self,item):
        motion=self.motion.get(self.identity(item))
        return 1.0 if not motion else motion[1]+(1-motion[1])*self.progress

    def nearby(self):
        start=max(0,self.verticalScrollBar().value()//self.row_height-1)
        stop=min(self.count(),start+self.viewport().height()//self.row_height+4)
        items={self.identity(self.item(i)):self.item(i) for i in range(start,stop)}
        if self.motion:
            for identity in self.motion:
                item=self.owner.rows_by_id.get(identity)
                if item is not None:items[identity]=item
        return items.values()

    def itemAt(self,point,y=None):
        if y is not None:point=QPoint(point,y)
        return next((item for item in reversed(list(self.nearby())) if self.visualItemRect(item).contains(point) and self.opacity(item)>.1),None)

    def paintEvent(self,event):
        painter=QPainter(self.viewport());painter.setClipRegion(event.region())
        for item in self.nearby():
            rect=self.visualItemRect(item)
            if not rect.intersects(event.rect()):continue
            option=QStyleOptionViewItem();self.initViewItemOption(option);option.rect=rect;option.state&=~QStyle.StateFlag.State_MouseOver
            if self.identity(item)==self.hovered:option.state|=QStyle.StateFlag.State_MouseOver
            painter.save();painter.setOpacity(self.opacity(item));self.itemDelegate().paint(painter,option,self.indexFromItem(item));painter.restore()

    def mouseMoveEvent(self,event):
        identity=self.identity(self.itemAt(event.position().toPoint()))
        if identity!=self.hovered:
            previous=self.hovered;self.hovered=identity
            self.owner.update_rows({previous,identity})
        super().mouseMoveEvent(event)

    def leaveEvent(self,event):
        previous=self.hovered;self.hovered=None;self.owner.update_rows({previous});super().leaveEvent(event)

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.pressed=self.identity(self.itemAt(event.position().toPoint()))

    def mouseReleaseEvent(self,event):
        item=self.itemAt(event.position().toPoint())
        if event.button()==Qt.MouseButton.LeftButton and item and self.identity(item)==self.pressed:self.itemClicked.emit(item)
        self.pressed=None


class RecentDelegate(QStyledItemDelegate):
    def paint(self,painter,option,index):
        row=index.data(Qt.ItemDataRole.UserRole);host=self.parent();rect=option.rect.adjusted(1,2,-1,-2)
        painter.save();painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor('#29374a' if option.state&QStyle.StateFlag.State_MouseOver else '#202a38'));painter.drawRoundedRect(rect,7,7)
        icon=index.data(Qt.ItemDataRole.DecorationRole)
        if isinstance(icon,QIcon):painter.drawPixmap(rect.left()+9,rect.top()+11,icon.pixmap(30,30))
        font=QFont(option.font);font.setPixelSize(12);painter.setFont(font);painter.setPen(QColor('#dce4ef'))
        left=rect.left()+49;right=rect.right()-128
        painter.drawText(QRectF(left,rect.top()+7,max(20,right-left),19),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,
            painter.fontMetrics().elidedText(row['item'].name,Qt.TextElideMode.ElideRight,max(20,right-left)))
        font.setPixelSize(10);painter.setFont(font);painter.setPen(QColor('#9caec6'))
        caption='Seen '+age_text(max(0,time.time()-row['seen']))+' ago'
        painter.drawText(QRectF(left,rect.top()+30,max(20,right-left),16),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,caption)
        price=row.get('price') or {};listed=compare(row['item'],price.get('quantity'),price.get('mesos'),None).unit_price
        if listed is not None:
            caption=f'Last seen price {listed:,.0f}';width=painter.fontMetrics().horizontalAdvance(caption)+2
            painter.drawText(QRectF(rect.right()-9-width,rect.top()+30,width,16),Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter,caption)
        font.setPixelSize(17);painter.setFont(font);painter.setPen(QColor('#e7c68f' if index.data(Qt.ItemDataRole.UserRole+2) else '#98a3b1'))
        value=index.data(Qt.ItemDataRole.UserRole+1);box=QRectF(rect.right()-128,rect.top()+5,106,24)
        roll=host.rolls.get(row['item'].game_id)
        if roll:roll.paint(painter,box,Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
        if value is not None:paint_icon(painter,QRectF(rect.right()-20,rect.top()+10,14,14))
        painter.restore()


class RecentItems(QWidget):
    chosen=Signal(object)
    changed=Signal()

    def __init__(self,parent=None,limit=100):
        super().__init__(parent);self.limit=limit;self.entries=OrderedDict();self.active=set();self.fingerprint=None;self.rows_by_id={};self.rolls={}
        self.content=QWidget(self)
        layout=QVBoxLayout(self.content);layout.setContentsMargins(0,10,0,0);layout.setSpacing(7)
        header=QHBoxLayout();self.caption=MotionLabel('Recent items');self.caption.setStyleSheet('font-size:11px;color:#aebdd0')
        header.addWidget(self.caption,1);self.clear_button=QPushButton('Clear');self.clear_button.setObjectName('quiet');self.clear_button.clicked.connect(self.clear);header.addWidget(self.clear_button);layout.addLayout(header)
        self.rows=RecentRows(self);self.rows.owner=self;self.rows.rolls=self.rolls;self.rows.setItemDelegate(RecentDelegate(self.rows));self.rows.setMouseTracking(True)
        self.rows.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);self.rows.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.rows.setStyleSheet('QListWidget{border:0;background:transparent;}');layout.addWidget(self.rows)
        self.rows.itemClicked.connect(lambda item:self.chosen.emit(item.data(Qt.ItemDataRole.UserRole)['item']))
        self.rows.verticalScrollBar().valueChanged.connect(lambda _:self.changed.emit())
        self.animating=set()
        self.animation=QVariantAnimation(self);self.animation.setDuration(160);self.animation.valueChanged.connect(self.advance)
        self.animation.finished.connect(self.finish_animation)
        self.geometry_animation=QVariantAnimation(self);self.geometry_animation.setDuration(180)
        self.geometry_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.geometry_animation.valueChanged.connect(self.advance_geometry);self.geometry_animation.finished.connect(self.finish_geometry)
        self.rows_height=2;self.rows.setFixedHeight(2);self.full_height=0;self.setFixedHeight(0);self.visible_ids=()
        self.hide()

    def update_rows(self,identities):
        dirty=QRegion();area=self.rows.viewport().rect()
        for identity in identities:
            item=self.rows_by_id.get(identity)
            if item is not None:
                rect=self.rows.visualItemRect(item).intersected(area)
                if not rect.isEmpty():dirty|=QRegion(rect)
        if not dirty.isEmpty():self.rows.viewport().update(dirty)

    def advance(self,value):
        for identity in self.animating:
            if identity in self.rolls:self.rolls[identity].progress=float(value)
        self.update_rows(self.animating)

    def finish_animation(self):
        for identity in self.animating:
            if identity in self.rolls:self.rolls[identity].finish()
        self.animating.clear()

    def advance_geometry(self,value):
        if not enabled(self):self.finish_geometry();return
        before={self.rows.identity(item):self.rows.visualItemRect(item) for item in self.rows.nearby()}
        self.rows.progress=float(value)
        self.setFixedHeight(round(self.height_from+(self.full_height-self.height_from)*float(value)))
        dirty=QRegion();area=self.rows.viewport().rect()
        for item in self.rows.nearby():
            identity=self.rows.identity(item)
            if identity in self.rows.motion:
                dirty|=QRegion(self.rows.visualItemRect(item).united(before.get(identity,QRect())).intersected(area))
        if not dirty.isEmpty():self.rows.viewport().update(dirty)
        parent=self.parentWidget()
        if parent and parent.layout():parent.layout().activate()
        visible_ids=tuple(item.game_id for item in self.visible_items())
        if visible_ids!=self.visible_ids:self.visible_ids=visible_ids;self.changed.emit()

    def finish_geometry(self):
        self.geometry_animation.stop();affected=set(self.rows.motion);self.rows.motion={};self.rows.progress=1.0
        self.setFixedHeight(self.full_height);self.update_rows(affected)

    def observe(self,observations,catalog,now,*,active=None):
        if not catalog:return
        current=set()
        for row in observations:
            item=catalog.resolve(row.get('name'),row.get('tier'))
            if item is None:continue
            identity=item.game_id;current.add(identity);previous=self.entries.get(identity)
            price=row.get('price') or {}
            # A partial OCR read or an occluded listing must never erase the
            # last complete asking price. This is history, not a live verdict.
            complete=compare(item,price.get('quantity'),price.get('mesos'),None).unit_price is not None
            entry=dict(item=item,seen=now,price=dict(price) if complete else previous.get('price') if previous else None)
            self.entries[identity]=entry
            if previous is None or identity not in self.active:self.entries.move_to_end(identity,last=False)
        self.active=current if active is None else set(active)
        while len(self.entries)>self.limit:
            identity,_=self.entries.popitem();self.rolls.pop(identity,None)

    def refresh(self,market,ttl,now):
        # Once a sighting enters history, seeing it again updates that same row.
        # OCR misses must not repeatedly remove and recreate history entries.
        visible=[row for identity,row in self.entries.items() if identity not in self.active or identity in self.rows_by_id]
        quotes={row['item'].game_id:market.cached(row['item']) for row in visible}
        fingerprint=(int(now//5),ttl,tuple((row['item'].game_id,int(row['seen']//10),repr(row['price']),quotes[row['item'].game_id]) for row in visible))
        if fingerprint==self.fingerprint:return
        age_changed=self.fingerprint is None or self.fingerprint[0]!=fingerprint[0]
        self.fingerprint=fingerprint;position=self.rows.verticalScrollBar().value()
        before={identity:self.rows.visualItemRect(item) for identity,item in self.rows_by_id.items()}
        old_order=tuple(self.rows.identity(self.rows.item(i)) for i in range(self.rows.count()))
        new_order=tuple(row['item'].game_id for row in visible)
        target_height=min(5,len(visible))*59+2
        layout_changed=old_order!=new_order or self.rows_height!=target_height
        if layout_changed:self.geometry_animation.stop()
        height_from=self.height()
        anchor=self.rows.itemAt(QPoint(8,2));anchor_id=anchor.data(Qt.ItemDataRole.UserRole)['item'].game_id if anchor else None
        anchor_y=self.rows.visualItemRect(anchor).top() if anchor else 0
        previous=self.rows_by_id;current={};changed_prices=set()
        if layout_changed:self.rows.setUpdatesEnabled(False)
        identities={row['item'].game_id for row in visible}
        for identity,item in previous.items():
            if identity not in identities:self.rows.takeItem(self.rows.row(item))
        for index,row in enumerate(visible):
            identity=row['item'].game_id;item=previous.get(identity)
            if item is None:item=QListWidgetItem();item.setSizeHint(QSize(0,59));self.rows.insertItem(index,item)
            elif self.rows.row(item)!=index:self.rows.takeItem(self.rows.row(item));self.rows.insertItem(index,item)
            previous_row=item.data(Qt.ItemDataRole.UserRole)
            if (not previous_row or previous_row['item']!=row['item'] or previous_row['price']!=row['price']
                    or int(previous_row['seen']//10)!=int(row['seen']//10)):
                item.setData(Qt.ItemDataRole.UserRole,row)
            quote=quotes[identity];price=quote.price if quote else None
            if item.data(Qt.ItemDataRole.UserRole+1)!=price:item.setData(Qt.ItemDataRole.UserRole+1,price)
            if item.toolTip()!=row['item'].name:item.setToolTip(row['item'].name)
            fresh=bool(quote and quote.fresh(now,ttl))
            if item.data(Qt.ItemDataRole.UserRole+2)!=fresh:item.setData(Qt.ItemDataRole.UserRole+2,fresh)
            roll=self.rolls.setdefault(identity,NumberRoll())
            if roll.set_text(f'{price:,.0f}' if price is not None else '—',enabled(self)):changed_prices.add(identity)
            current[identity]=item
        self.rows_by_id=current;self.rows_height=target_height;self.rows.setFixedHeight(target_height)
        self.caption.setText(f'Recent items · {len(visible)}')
        self.full_height=self.content.sizeHint().height() if visible else 0
        self.content.resize(self.width(),self.full_height)
        self.content.layout().activate()
        if layout_changed:self.rows.doItemsLayout();self.rows.verticalScrollBar().setValue(position)
        if layout_changed and position and anchor_id in current:
            self.rows.scrollToItem(current[anchor_id],QListWidget.ScrollHint.PositionAtTop)
            self.rows.verticalScrollBar().setValue(self.rows.verticalScrollBar().value()-anchor_y)
        self.setVisible(bool(visible))
        if layout_changed and enabled(self):
            area=self.rows.viewport().rect();motions={}
            for identity,item in current.items():
                target=self.rows.target_rect(item);old=before.get(identity)
                if old is not None and old.intersects(area):
                    offset=old.top()-target.top()
                    if offset:motions[identity]=(offset,1.0)
                elif target.intersects(area):motions[identity]=(-16,0.0)
            self.rows.motion=motions;self.rows.progress=0.0;self.height_from=height_from
            self.geometry_animation.setStartValue(0.0);self.geometry_animation.setEndValue(1.0);self.geometry_animation.start()
        elif layout_changed or not enabled(self):self.finish_geometry()
        if layout_changed:self.rows.setUpdatesEnabled(True)
        if age_changed:self.update_rows(current)
        if changed_prices and enabled(self):
            self.animation.stop()
            for identity in self.animating-changed_prices:
                if identity in self.rolls:self.rolls[identity].finish()
            self.animating=changed_prices
            self.animation.setStartValue(0.0);self.animation.setEndValue(1.0);self.animation.start()
        elif not enabled(self):
            self.animation.stop();self.animating.clear()
            for roll in self.rolls.values():roll.finish()

    def visible_items(self):
        if not self.isVisible():return []
        area=self.rows.viewport().visibleRegion().boundingRect()
        return [item.data(Qt.ItemDataRole.UserRole)['item'] for item in self.rows.nearby() if self.rows.visualItemRect(item).intersects(area)]

    def set_image(self,identity,image):
        item=self.rows_by_id.get(identity)
        if item and not image.isNull() and item.data(Qt.ItemDataRole.UserRole+3)!=image.cacheKey():
            item.setIcon(QIcon(QPixmap.fromImage(image)));item.setData(Qt.ItemDataRole.UserRole+3,image.cacheKey())

    def clear(self):
        self.geometry_animation.stop();self.rows.motion={};self.rows.progress=1.0;self.rows_height=2;self.rows.setFixedHeight(2);self.full_height=0;self.setFixedHeight(0)
        self.animation.stop();self.animating.clear();self.entries.clear();self.active.clear();self.rows.clear();self.rows_by_id.clear();self.rolls.clear();self.fingerprint=None
        self.hide();self.changed.emit()

    def hideEvent(self,event):
        self.finish_geometry()
        self.animation.stop()
        self.animating.clear()
        for roll in self.rolls.values():roll.finish()
        super().hideEvent(event)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if self.content.width()!=self.width():self.content.resize(self.width(),self.full_height)
