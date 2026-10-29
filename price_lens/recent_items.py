"""Bounded session-only sightings; no frames, disk history or market requests."""
from collections import OrderedDict
import time
from PySide6.QtCore import Qt,QSize,QRectF,QPoint,Signal,QVariantAnimation
from PySide6.QtGui import QColor,QFont,QIcon,QPixmap
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QListWidget,QListWidgetItem,QPushButton,QStyledItemDelegate,QStyle
from .motion import MotionLabel,reveal,enabled,fade_away
from .domain import age_text,compare
from .gui_currency import paint_icon
from .number_motion import NumberRoll


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
        if listed is not None:painter.drawText(QRectF(rect.right()-134,rect.top()+30,125,16),Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter,f'Last listed {listed:,.0f}')
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
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(7)
        header=QHBoxLayout();self.caption=MotionLabel('Recent items');self.caption.setStyleSheet('font-size:11px;color:#aebdd0')
        header.addWidget(self.caption,1);self.clear_button=QPushButton('Clear');self.clear_button.setObjectName('quiet');self.clear_button.clicked.connect(self.clear);header.addWidget(self.clear_button);layout.addLayout(header)
        self.rows=QListWidget();self.rows.rolls=self.rolls;self.rows.setItemDelegate(RecentDelegate(self.rows));self.rows.setMouseTracking(True)
        self.rows.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);self.rows.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.rows.setStyleSheet('QListWidget{border:0;background:transparent;}');layout.addWidget(self.rows)
        self.rows.itemClicked.connect(lambda item:self.chosen.emit(item.data(Qt.ItemDataRole.UserRole)['item']))
        self.rows.verticalScrollBar().valueChanged.connect(self.changed.emit)
        self.animating=set()
        self.animation=QVariantAnimation(self);self.animation.setDuration(160);self.animation.valueChanged.connect(self.advance)
        self.animation.finished.connect(self.finish_animation)
        self.hide()

    def advance(self,value):
        for identity in self.animating:
            if identity in self.rolls:self.rolls[identity].progress=float(value)
        self.rows.viewport().update()

    def finish_animation(self):
        for identity in self.animating:
            if identity in self.rolls:self.rolls[identity].finish()
        self.animating.clear()

    def observe(self,observations,catalog,now):
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
        self.active=current
        while len(self.entries)>self.limit:
            identity,_=self.entries.popitem();self.rolls.pop(identity,None)

    def refresh(self,market,ttl,now):
        # Once a sighting enters history, seeing it again updates that same row.
        # OCR misses must not repeatedly remove and recreate history entries.
        visible=[row for identity,row in self.entries.items() if identity not in self.active or identity in self.rows_by_id]
        quotes={row['item'].game_id:market.cached(row['item']) for row in visible}
        fingerprint=(int(now//5),ttl,tuple((row['item'].game_id,int(row['seen']//10),repr(row['price']),quotes[row['item'].game_id]) for row in visible))
        if fingerprint==self.fingerprint:return
        self.fingerprint=fingerprint;shown=not self.isHidden();position=self.rows.verticalScrollBar().value()
        anchor=self.rows.itemAt(QPoint(8,2));anchor_id=anchor.data(Qt.ItemDataRole.UserRole)['item'].game_id if anchor else None
        anchor_y=self.rows.visualItemRect(anchor).top() if anchor else 0
        previous=self.rows_by_id;current={};changed_prices=set()
        identities={row['item'].game_id for row in visible}
        for identity,item in previous.items():
            if identity not in identities:self.rows.takeItem(self.rows.row(item))
        for index,row in enumerate(visible):
            identity=row['item'].game_id;item=previous.get(identity)
            if item is None:item=QListWidgetItem();item.setSizeHint(QSize(0,59));self.rows.insertItem(index,item)
            elif self.rows.row(item)!=index:self.rows.takeItem(self.rows.row(item));self.rows.insertItem(index,item)
            if item.data(Qt.ItemDataRole.UserRole)!=row:item.setData(Qt.ItemDataRole.UserRole,row)
            quote=quotes[identity];price=quote.price if quote else None
            item.setData(Qt.ItemDataRole.UserRole+1,price);item.setToolTip(row['item'].name)
            item.setData(Qt.ItemDataRole.UserRole+2,bool(quote and quote.fresh(now,ttl)))
            roll=self.rolls.setdefault(identity,NumberRoll())
            if roll.set_text(f'{price:,.0f}' if price is not None else '—',enabled(self)):changed_prices.add(identity)
            current[identity]=item
        self.rows_by_id=current;self.rows.verticalScrollBar().setValue(position)
        if position and anchor_id in current:
            self.rows.scrollToItem(current[anchor_id],QListWidget.ScrollHint.PositionAtTop)
            self.rows.verticalScrollBar().setValue(self.rows.verticalScrollBar().value()-anchor_y)
        self.rows.setFixedHeight(min(5,len(visible))*59+2);self.caption.setText(f'Recent items · {len(visible)}');self.setVisible(bool(visible))
        if visible and not shown:reveal(self)
        if changed_prices:
            self.animation.stop()
            for identity in self.animating-changed_prices:
                if identity in self.rolls:self.rolls[identity].finish()
            self.animating=changed_prices
            self.animation.setStartValue(0.0);self.animation.setEndValue(1.0);self.animation.start()

    def visible_items(self):
        if not self.isVisible():return []
        area=self.rows.viewport().rect()
        return [item.data(Qt.ItemDataRole.UserRole)['item'] for item in self.rows_by_id.values() if self.rows.visualItemRect(item).intersects(area)]

    def set_image(self,identity,image):
        item=self.rows_by_id.get(identity)
        if item and not image.isNull() and item.data(Qt.ItemDataRole.UserRole+3)!=image.cacheKey():
            item.setIcon(QIcon(QPixmap.fromImage(image)));item.setData(Qt.ItemDataRole.UserRole+3,image.cacheKey())

    def clear(self):
        fade_away(self)
        self.animation.stop();self.animating.clear();self.entries.clear();self.active.clear();self.rows.clear();self.rows_by_id.clear();self.rolls.clear();self.fingerprint=None
        self.hide();self.changed.emit()

    def hideEvent(self,event):
        self.animation.stop()
        self.animating.clear()
        for roll in self.rolls.values():roll.finish()
        super().hideEvent(event)
