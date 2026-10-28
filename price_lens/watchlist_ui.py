"""Inline watched items, exact selection, cached references and clipped expansion."""
from PySide6.QtCore import QRect,QRectF,QSize,Qt,Signal,QVariantAnimation,QEasingCurve
from PySide6.QtGui import QColor,QFont,QIcon,QPainter,QPixmap,QPalette,QBrush
from PySide6.QtWidgets import (QFrame,QHBoxLayout,QLabel,QListWidget,QListWidgetItem,
    QStyledItemDelegate,QStyleOptionViewItem,QStyle,QToolButton,QPushButton,QVBoxLayout,QWidget)
from .motion import RollingLabel,enabled
from .gui_currency import paint_icon
from .domain import age_text


class WatchButton(QPushButton):
    """One exact-item watch control shared by search, shop and inventory cards."""
    def __init__(self,parent=None):
        super().__init__('☆',parent);self.watches=None;self.item=None
        self.setCheckable(True);self.setFixedSize(32,32)
        self.setStyleSheet('QPushButton {background:transparent;border:1px solid transparent;font-size:20px;color:#b5c1d2;border-radius:6px;} QPushButton:hover {background:#303c4e;border-color:#53647b;} QPushButton:checked {background:#403525;border-color:#c8a363;color:#f5d798;}')
        self.clicked.connect(self.toggle_item);self.hide()

    def bind(self,watches):
        if self.watches is watches:return
        if self.watches:self.watches.changed.disconnect(self.refresh)
        self.watches=watches
        if watches:watches.changed.connect(self.refresh)
        self.refresh()

    def set_item(self,item):
        self.item=item;self.refresh()

    def toggle_item(self):
        if self.watches and self.item:self.watches.toggle(self.item)

    def refresh(self):
        watched=bool(self.item and self.watches and self.item.game_id in self.watches.ids)
        self.setChecked(watched);self.setText('★' if watched else '☆')
        self.setToolTip('Stop watching this item' if watched else 'Watch this item')
        self.setAccessibleName('Stop watching item' if watched else 'Watch item')
        self.setEnabled(bool(self.item and self.watches and (watched or len(self.watches.ids)<512)))
        self.setVisible(bool(self.item and self.watches is not None))


class ClippedSection(QWidget):
    """Keep list contents at full height while only their viewport slides."""
    def __init__(self,parent=None):
        super().__init__(parent);self.content=QWidget(self);self.expanded=False
        self.animation=QVariantAnimation(self);self.animation.setDuration(200)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.animation.valueChanged.connect(self.advance)
        self.animation.finished.connect(self.finish)
        self.full_height=0;self.setFixedHeight(0)

    def advance(self,value):
        self.setFixedHeight(round(value))
        # Qt otherwise paints a frame with the old ancestor height, squeezing
        # the header/body apart before the queued layout request catches up.
        chain=[];parent=self.parentWidget()
        while parent is not None:
            chain.append(parent);parent.updateGeometry()
            if parent.layout():parent.layout().invalidate()
            parent=parent.parentWidget()
        for parent in reversed(chain):
            if parent.layout() and parent.layout().isEnabled():parent.layout().activate()
        self.update()

    def finish(self):
        self.content.setVisible(self.expanded);self.update()

    def set_expanded(self,shown):
        self.expanded=shown;self.content.layout().activate()
        full=self.content.sizeHint().height();self.full_height=full
        if self.content.size()!=QSize(self.width(),full):self.content.resize(self.width(),full)
        target=full if shown else 0
        if self.animation.state()==self.animation.State.Running and self.animation.endValue()==target:return
        self.animation.stop()
        if self.height()==target:self.finish();return
        if not enabled(self.parentWidget() or self):self.setFixedHeight(target);self.finish();return
        self.content.show()
        self.animation.setStartValue(self.height());self.animation.setEndValue(target);self.animation.start()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        # Height changes clip a fixed canvas. Relaying them to the children
        # made wrapped text/list geometry recalculate during every frame.
        if self.content.layout() and self.content.width()!=self.width():
            self.content.resize(self.width(),self.full_height or self.content.sizeHint().height())


class WatchDelegate(QStyledItemDelegate):
    def paint(self,painter,option,index):
        selected=bool(option.state & QStyle.StateFlag.State_Selected)
        hovered=bool(option.state & QStyle.StateFlag.State_MouseOver)
        painter.save()
        if selected or hovered:
            painter.setPen(QColor('#64718a') if selected else Qt.PenStyle.NoPen)
            painter.setBrush(QColor('#35455b') if selected else QColor('#293649'))
            painter.drawRoundedRect(option.rect.adjusted(2,2,-2,-2),6,6)
        text_option=QStyleOptionViewItem(option);text_option.rect=option.rect.adjusted(2,1,-140,-1)
        text_option.state &= ~(QStyle.StateFlag.State_Selected|QStyle.StateFlag.State_MouseOver|QStyle.StateFlag.State_HasFocus)
        text_option.backgroundBrush=QBrush(Qt.BrushStyle.NoBrush)
        if selected:text_option.palette.setColor(QPalette.ColorRole.Text,QColor('#f0e4cc'))
        super().paint(painter,text_option,index)
        price=index.data(Qt.ItemDataRole.UserRole+1)
        font=QFont(option.font);font.setPixelSize(11);painter.setFont(font)
        price_box=option.rect.adjusted(option.rect.width()-138,0,-34,0)
        painter.setPen(QColor('#e9c989') if price and price[1] else QColor('#9aa7ba'))
        if price and price[0] is not None:
            painter.drawText(price_box.adjusted(0,0,-18,0),Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter,f'{price[0]:,.0f}')
            paint_icon(painter,QRectF(price_box.right()-15,price_box.center().y()-7,16,14))
        else:painter.drawText(price_box,Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter,'—')
        painter.setPen(QColor('#dfb56e'));font.setPixelSize(17);painter.setFont(font)
        painter.drawText(QRect(option.rect.right()-29,option.rect.top(),28,option.rect.height()),Qt.AlignmentFlag.AlignCenter,'★')
        painter.restore()


class WatchRows(QListWidget):
    remove_requested=Signal(int)
    chosen=Signal(object)
    empty_clicked=Signal()

    def __init__(self,parent=None):
        super().__init__(parent);self.removing=None;self.previous=None;self.active_identity=None
        self.setItemDelegate(WatchDelegate(self));self.setIconSize(QSize(28,28))
        self.setMouseTracking(True);self.viewport().setMouseTracking(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTextElideMode(Qt.TextElideMode.ElideRight);self.setAccessibleName('Watched items')

    def remove_target(self,event):
        row=self.itemAt(event.position().toPoint())
        return row if row and event.position().x()>=self.visualItemRect(row).right()-30 else None

    def clear_choice(self):
        self.active_identity=None
        self.clearSelection();self.setCurrentItem(None);self.chosen.emit(None)

    def mousePressEvent(self,event):
        self.previous=self.active_identity
        row=self.remove_target(event)
        if row and event.button()==Qt.MouseButton.LeftButton:
            self.removing=row.data(Qt.ItemDataRole.UserRole);event.accept();return
        self.removing=None;super().mousePressEvent(event)

    def mouseReleaseEvent(self,event):
        if self.removing is not None:
            identity=self.removing;self.removing=None;row=self.remove_target(event)
            if row and row.data(Qt.ItemDataRole.UserRole)==identity:self.remove_requested.emit(identity)
            event.accept();return
        row=self.itemAt(event.position().toPoint());super().mouseReleaseEvent(event)
        if event.button()!=Qt.MouseButton.LeftButton:return
        identity=row.data(Qt.ItemDataRole.UserRole) if row else None
        if identity is None:
            self.clear_choice();self.empty_clicked.emit()
        elif identity==self.previous:self.clear_choice()
        else:self.active_identity=identity;self.chosen.emit(identity)

    def keyPressEvent(self,event):
        row=self.currentItem()
        if row and event.key()==Qt.Key.Key_Delete:
            self.remove_requested.emit(row.data(Qt.ItemDataRole.UserRole));event.accept();return
        if event.key()==Qt.Key.Key_Escape:self.clear_choice();event.accept();return
        if row and event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter,Qt.Key.Key_Space):
            self.active_identity=row.data(Qt.ItemDataRole.UserRole);self.chosen.emit(self.active_identity);event.accept();return
        super().keyPressEvent(event)


class WatchedItems(QFrame):
    item_selected=Signal(object)
    visible_changed=Signal()
    expanded_changed=Signal(bool)

    def __init__(self,parent=None):
        super().__init__(parent);self.watches=None;self.expanded=False;self.icons={};self.image_keys={}
        self.setObjectName('watchedItems');self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet('QFrame#watchedItems {background:#1c2532;border:1px solid #344154;border-radius:8px;} QFrame#watchedItems QWidget {background:transparent;border:0;} QToolButton {background:transparent;border:0;color:#e4eaf2;padding:4px;font-weight:600;} QListWidget {background:transparent;border:0;outline:0;} QListWidget::item {padding:5px 6px;border:0;background:transparent;}')
        layout=QVBoxLayout(self);layout.setContentsMargins(10,5,10,5);layout.setSpacing(0)
        header=QHBoxLayout();header.setSpacing(5)
        self.toggle=QToolButton();self.toggle.setText('Watched items');self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(Qt.ArrowType.RightArrow);self.toggle.setCheckable(True);self.toggle.toggled.connect(self.set_expanded)
        header.addWidget(self.toggle)
        self.count=RollingLabel('0');self.count.setFixedWidth(28);self.count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.count.setStyleSheet('color:#b6c3d5;font-size:11px;background:#2a3647;border-radius:7px;padding:2px;');header.addWidget(self.count)
        header.addStretch();self.reference_label=QLabel('Reference');self.reference_label.setStyleSheet('color:#97a8bf;font-size:10px');header.addWidget(self.reference_label)
        layout.addLayout(header)
        self.body=ClippedSection(self);body=QVBoxLayout(self.body.content);body.setContentsMargins(0,5,0,3);body.setSpacing(0)
        self.empty=QLabel('Search for an item, then choose ☆ to watch it.');self.empty.setWordWrap(True)
        self.empty.setStyleSheet('color:#9eacbf;font-size:11px;padding:5px;');body.addWidget(self.empty)
        self.rows=WatchRows();self.rows.chosen.connect(self.item_selected.emit);self.rows.remove_requested.connect(self.remove)
        self.rows.empty_clicked.connect(lambda:self.set_expanded(not self.expanded))
        self.rows.verticalScrollBar().valueChanged.connect(lambda *_:self.visible_changed.emit())
        self.rows.viewport().setAutoFillBackground(False);self.rows.verticalScrollBar().setCursor(Qt.CursorShape.ArrowCursor)
        body.addWidget(self.rows);layout.addWidget(self.body)

    def set_watchlist(self,watches):
        self.watches=watches;watches.changed.connect(self.refresh);self.refresh();self.set_expanded(False)

    def set_expanded(self,expanded):
        was=self.expanded;self.expanded=bool(expanded)
        self.toggle.blockSignals(True);self.toggle.setChecked(self.expanded);self.toggle.blockSignals(False)
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if self.expanded else Qt.ArrowType.RightArrow)
        self.body.set_expanded(self.expanded);self.reference_label.setVisible(self.expanded and bool(self.rows.count()))
        if was and not self.expanded:self.rows.clear_choice()
        if was!=self.expanded:self.expanded_changed.emit(self.expanded)
        self.visible_changed.emit()

    def refresh(self):
        entries=self.watches.entries if self.watches else {};count=len(entries)
        previous=self.rows.count();position=self.rows.verticalScrollBar().value()
        identity=self.rows.active_identity
        quotes={self.rows.item(i).data(Qt.ItemDataRole.UserRole):self.rows.item(i).data(Qt.ItemDataRole.UserRole+1) for i in range(previous)}
        self.rows.clear();blank=QPixmap(28,28);blank.fill(Qt.GlobalColor.transparent);placeholder=QIcon(blank)
        for item_id,name in sorted(entries.items(),key=lambda row:(row[1].casefold(),row[0])):
            row=QListWidgetItem(name);row.setData(Qt.ItemDataRole.UserRole,item_id);row.setData(Qt.ItemDataRole.UserRole+1,quotes.get(item_id));row.setSizeHint(QSize(0,42))
            row.setIcon(self.icons.get(item_id,placeholder));row.setToolTip(name+'\nClick for its market reference; click ★ to stop watching.')
            self.rows.addItem(row)
            if item_id==identity:self.rows.setCurrentItem(row)
        self.icons={k:v for k,v in self.icons.items() if k in entries};self.image_keys={k:v for k,v in self.image_keys.items() if k in entries}
        self.rows.setFixedHeight(min(3,count)*42+4);self.rows.setVisible(bool(count));self.empty.setVisible(not count)
        self.rows.verticalScrollBar().setValue(position);self.count.setText(str(count))
        if count and not previous:self.set_expanded(True)
        else:self.body.set_expanded(self.expanded)
        if identity is not None and identity not in entries:self.rows.active_identity=None;self.item_selected.emit(None)
        self.reference_label.setVisible(self.expanded and bool(count));self.visible_changed.emit()

    def remove(self,identity):
        if self.watches:self.watches.remove(identity)

    def visible_ids(self):
        if not self.expanded or not self.isVisible():return []
        region=self.rows.viewport().rect().adjusted(0,-42,0,42)
        return [self.rows.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.rows.count()) if self.rows.visualItemRect(self.rows.item(i)).intersects(region)]

    def set_image(self,identity,image):
        if image.isNull() or self.image_keys.get(identity)==image.cacheKey():return
        self.image_keys[identity]=image.cacheKey();tile=QPixmap(28,28);tile.fill(Qt.GlobalColor.transparent)
        image=image.scaled(28,28,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.FastTransformation)
        painter=QPainter(tile);painter.drawImage((28-image.width())//2,(28-image.height())//2,image);painter.end()
        icon=QIcon(tile);icon.addPixmap(tile,QIcon.Mode.Disabled);self.icons[identity]=icon
        for i in range(self.rows.count()):
            row=self.rows.item(i)
            if row.data(Qt.ItemDataRole.UserRole)==identity:row.setIcon(icon)

    def set_quote(self,identity,quote,now,ttl):
        data=(quote.price,quote.fresh(now,ttl),quote.fetched_at) if quote else None
        for i in range(self.rows.count()):
            row=self.rows.item(i)
            stored=row.data(Qt.ItemDataRole.UserRole+1)
            if isinstance(stored,list):stored=tuple(stored)
            if row.data(Qt.ItemDataRole.UserRole)!=identity or stored==data:continue
            row.setData(Qt.ItemDataRole.UserRole+1,data)
            row.setToolTip(row.text()+'\n'+(f'Market reference: {quote.price:,.0f} mesos\nChecked {age_text(max(0,now-quote.fetched_at))} ago'+(' · expired' if not quote.cache_valid(now,ttl) else '') if quote and quote.price is not None else 'No price in the market snapshot.'))

    def showEvent(self,event):
        super().showEvent(event);self.body.set_expanded(self.expanded);self.visible_changed.emit()

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            self.set_expanded(not self.expanded);event.accept();return
        super().mouseReleaseEvent(event)
