"""The local Database tab. Navigation never creates market-price demand."""
from datetime import datetime
from pathlib import Path
import time
from PySide6.QtCore import QEasingCurve,QPoint,QRect,QSize,Qt,QTimer,QVariantAnimation,Signal
from PySide6.QtGui import QColor,QIcon,QImage,QKeySequence,QPainter,QPixmap,QShortcut
from PySide6.QtWidgets import (QButtonGroup,QComboBox,QFrame,QHBoxLayout,QLabel,QLineEdit,QListWidget,QListWidgetItem,
    QPushButton,QScrollArea,QStackedWidget,QVBoxLayout,QWidget)
from .motion import ContentArea,MotionLabel,enabled
from .reference_data import image_url
from .reference_media import ReferenceMedia,ReferenceSprite
from .reference_details import text,describe_item,describe_monster,describe_skill
from .domain import key as name_key
from .watchlist_ui import WatchButton


class DatabasePanel(QWidget):
    source_requested=Signal(str)
    price_requested=Signal(int)

    def __init__(self,service,media_folder,parent=None,*,media=None):
        super().__init__(parent);self.service=service;self.store=service.store
        self.media=media or ReferenceMedia(media_folder,self)
        self.kind='items';self.selected=None;self.history=[];self.entries={};self.catalog={};self.market=None;self.ttl=900
        self.active=False;self.closed=False;self.related=[];self.rank_slider=None;self.results_current=True;self.limit=80;self.match_count=0
        self.setStyleSheet('QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;} QScrollBar::up-arrow:vertical,QScrollBar::down-arrow:vertical{width:0;height:0;}')
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(8)
        kinds=QHBoxLayout();kinds.setSpacing(6);self.kind_group=QButtonGroup(self);self.kind_buttons={}
        for kind,title in (('items','Items'),('monsters','Monsters'),('skills','Skills')):
            button=QPushButton(title);button.setCheckable(True);button.setChecked(kind==self.kind)
            button.setStyleSheet('QPushButton:checked{background:#3f3528;border-color:#b59664;color:#f0ce94;}')
            self.kind_group.addButton(button);self.kind_buttons[kind]=button;kinds.addWidget(button,1)
            button.clicked.connect(lambda checked=False,kind=kind:self.choose_kind(kind))
        layout.addLayout(kinds)
        tools=QHBoxLayout();tools.setSpacing(6)
        self.query=QLineEdit();self.query.setPlaceholderText('Search items…');self.query.setClearButtonEnabled(True);self.query.setAccessibleName('Search database')
        self.query.setMinimumHeight(34);self.query.setStyleSheet('QLineEdit{background:#1b2330;border:1px solid #3b485c;border-radius:6px;padding:6px 9px;} QLineEdit:focus{border-color:#c3a16a;}')
        tools.addWidget(self.query,1);self.refresh=QPushButton('↻');self.refresh.setFixedWidth(34);self.refresh.setToolTip('Update the local database')
        self.refresh.setAccessibleName('Refresh database');self.refresh.clicked.connect(self.refresh_all);tools.addWidget(self.refresh);layout.addLayout(tools)
        self.filters=QComboBox();self.filters.setAccessibleName('Filter database');layout.addWidget(self.filters)
        self.summary=MotionLabel();self.summary.setStyleSheet('color:#a8b6c8;font-size:11px');layout.addWidget(self.summary)
        self.content=ContentArea();content=QVBoxLayout(self.content);content.setContentsMargins(0,0,0,0)
        self.pages=QStackedWidget();content.addWidget(self.pages);layout.addWidget(self.content,1)
        self.list_page=QWidget();listing=QVBoxLayout(self.list_page);listing.setContentsMargins(0,0,0,0);listing.setSpacing(6)
        self.results=QListWidget();self.results.setIconSize(QSize(32,32));self.results.setSpacing(3)
        self.results.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.results.setStyleSheet('QListWidget{background:transparent;border:0;} QListWidget::item{padding:7px;border:1px solid transparent;border-radius:7px;} QListWidget::item:hover{background:#253244;} QListWidget::item:selected{background:#3e3529;border-color:#a88b5c;color:#f0d4a8;}')
        listing.addWidget(self.results,1);self.more=QPushButton('Show more');listing.addWidget(self.more);self.more.hide()
        self.more.clicked.connect(self.show_more);self.pages.addWidget(self.list_page)
        self.detail_page=QWidget();detail_page=QVBoxLayout(self.detail_page);detail_page.setContentsMargins(0,0,0,0);detail_page.setSpacing(8)
        nav=QHBoxLayout();self.back=QPushButton('‹ Back');self.back.clicked.connect(self.go_back);nav.addWidget(self.back);nav.addStretch()
        self.section_links=QHBoxLayout();self.section_links.setSpacing(10);nav.addLayout(self.section_links);detail_page.addLayout(nav)
        self.detail_scroll=QScrollArea();self.detail_scroll.setWidgetResizable(True);self.detail_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.detail=QWidget();self.detail_layout=QVBoxLayout(self.detail);self.detail_layout.setContentsMargins(0,0,5,0);self.detail_layout.setSpacing(12)
        self.detail_scroll.setWidget(self.detail);detail_page.addWidget(self.detail_scroll,1);self.pages.addWidget(self.detail_page)
        self.status=MotionLabel();self.status.setWordWrap(True);self.status.setStyleSheet('font-size:10px;color:#96a6bb');layout.addWidget(self.status)
        self.status.setToolTip('Reference data: OSMS Data Explorer / @ohmi, CC BY 4.0\nDrop reports: MapleClassic Wiki, CC BY-NC-SA 4.0; NiaMeowDB community reports\nGame text and images © Nexon')
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(100);self.timer.timeout.connect(self.search)
        self.scrolling=QVariantAnimation(self);self.scrolling.setDuration(210);self.scrolling.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.scrolling.valueChanged.connect(lambda value:self.detail_scroll.verticalScrollBar().setValue(round(value)))
        self.query.textChanged.connect(self.schedule);self.query.returnPressed.connect(self.open_first)
        self.filters.currentIndexChanged.connect(lambda *_:self.search())
        self.results.itemClicked.connect(self.choose_result);self.results.itemActivated.connect(self.choose_result)
        self.results.verticalScrollBar().valueChanged.connect(self.observe_media)
        self.detail_scroll.verticalScrollBar().valueChanged.connect(self.observe_media)
        self.media.ready.connect(self.image_ready);self.service.updated.connect(self.reloaded);self.service.changed.connect(self.update_status)
        self.service.extra.updated.connect(self.extra_updated);self.service.extra.changed.connect(self.update_status)
        self.focus_shortcut=QShortcut(QKeySequence('Ctrl+F'),self);self.focus_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.focus_shortcut.activated.connect(lambda:(self.query.setFocus(),self.query.selectAll()))
        self.back_shortcut=QShortcut(QKeySequence('Alt+Left'),self);self.back_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.back_shortcut.activated.connect(self.go_back)
        self.fill_filters();self.search(False);self.update_status()

    def set_catalog(self,catalog):
        self.catalog={item.game_id:item for item in catalog.items} if catalog else {}
        if self.selected and self.selected.kind=='items' and hasattr(self,'watch_button'):
            self.watch_button.set_item(self.catalog_item(self.selected));self.update_market()

    def catalog_item(self,entry):
        item=self.catalog.get(entry.id)
        return item if item and name_key(item.name)==name_key(entry.name) else None

    def set_market(self,market,ttl):self.market=market;self.ttl=ttl;self.update_market()

    def set_watchlist(self,watchlist):self.watchlist=watchlist

    def refresh_all(self):
        self.service.start(True)
        if self.active:self.service.extra.select(self.selected,True)

    def extra_updated(self,key):
        if not self.closed and self.active and self.selected and self.selected.key==key:
            position=self.detail_scroll.verticalScrollBar().value();self.reloaded();self.detail_scroll.verticalScrollBar().setValue(position)

    def fill_filters(self,value=''):
        self.filters.blockSignals(True);self.filters.clear();self.filters.addItem('All jobs' if self.kind=='skills' else 'All categories','')
        for category in self.store.categories(self.kind):self.filters.addItem(category,category)
        self.filters.setCurrentIndex(max(0,self.filters.findData(value)));self.filters.blockSignals(False)

    def choose_kind(self,kind):
        if kind not in self.kind_buttons:return
        self.content.begin();self.kind=kind;self.selected=None;self.history=[];self.timer.stop();self.limit=80
        self.kind_buttons[kind].setChecked(True);self.query.blockSignals(True);self.query.clear();self.query.blockSignals(False)
        self.query.setPlaceholderText('Search '+kind+'…');self.fill_filters();self.search(False);self.content.complete()

    def schedule(self):
        self.results_current=False;self.limit=80;self.timer.start()

    def search(self,animate=True):
        entries,count=self.store.search(self.kind,self.query.text(),self.filters.currentData() or '',self.limit)
        structure=tuple(entry.key for entry in entries)
        previous=tuple(self.results.item(i).data(Qt.ItemDataRole.UserRole).key for i in range(self.results.count()))
        change=previous!=structure or self.selected is not None
        if animate and change:self.content.begin()
        self.selected=None;self.history=[];self.pages.setCurrentWidget(self.list_page);self.pause_sprite()
        self.service.extra.select(None)
        rows={self.results.item(i).data(Qt.ItemDataRole.UserRole).key:self.results.item(i) for i in range(self.results.count())}
        self.results.blockSignals(True)
        for identity,row in list(rows.items()):
            if identity not in structure:self.results.takeItem(self.results.row(row));rows.pop(identity)
        self.entries={entry.key:entry for entry in entries}
        for index,entry in enumerate(entries):
            row=rows.get(entry.key)
            if row is None:row=QListWidgetItem();self.results.insertItem(index,row)
            elif self.results.row(row)!=index:self.results.takeItem(self.results.row(row));self.results.insertItem(index,row)
            label=entry.category
            if entry.kind=='skills':label=entry.job+' · '+entry.category
            elif entry.level is not None:label+=f' · Lv. {entry.level}'
            old=row.data(Qt.ItemDataRole.UserRole);caption=entry.name+'\n'+label
            if row.text()!=caption:row.setText(caption)
            if old!=entry:row.setData(Qt.ItemDataRole.UserRole,entry)
            row.setSizeHint(QSize(0,59))
            if old is None or old.icon!=entry.icon:row.setIcon(self.icon(entry.icon))
            row.setToolTip(entry.name)
        self.results.blockSignals(False);self.results_current=True;self.match_count=count
        self.summary.setText(f'{count:,} '+('matches' if self.query.text().strip() else self.kind))
        self.more.setVisible(count>len(entries));self.results.setVisible(bool(entries))
        if not entries:
            self.summary.setText('No matches' if self.store.metadata().get('counts') else 'Getting the Classic World database…' if self.service.busy else 'Database not downloaded yet')
        if animate and change:self.content.complete()
        self.observe_media();QTimer.singleShot(0,self.observe_media)

    def show_more(self):self.limit+=80;self.search()

    def choose_result(self,row):
        if self.results_current and row:self.open(row.data(Qt.ItemDataRole.UserRole).key)

    def open_first(self):
        self.timer.stop();self.search();self.choose_result(self.results.item(0))

    def state(self):
        return (self.selected.key if self.selected else None,self.kind,self.query.text(),self.filters.currentData(),
                self.detail_scroll.verticalScrollBar().value() if self.selected else self.results.verticalScrollBar().value())

    def open(self,key,remember=True):
        if self.selected and self.selected.key==key:return
        record=self.store.entry(*key)
        if record is None:return
        if remember:self.history.append(self.state());self.history=self.history[-32:]
        self.timer.stop();self.scrolling.stop();self.content.begin();self.pause_sprite()
        self.selected,row=record;entry=self.selected;self.kind=entry.kind;self.kind_buttons[self.kind].setChecked(True)
        self.query.blockSignals(True);self.query.clear();self.query.blockSignals(False);self.query.setPlaceholderText('Search '+self.kind+'…');self.fill_filters()
        while self.detail_layout.count():
            item=self.detail_layout.takeAt(0)
            if item.widget():item.widget().hide();item.widget().deleteLater()
        self.related=[];self.rank_slider=None;self.market_label=None;self.section_targets={}
        header=QWidget();head=QHBoxLayout(header);head.setContentsMargins(0,0,0,0);head.setSpacing(12)
        self.sprite=ReferenceSprite(self.media,header);head.addWidget(self.sprite,0,Qt.AlignmentFlag.AlignTop)
        names=QVBoxLayout();names.setSpacing(5);self.item_name=text(entry.name,17,'#edcf9f',True);self.item_name.setProperty('currencyIcon',False)
        names.addWidget(self.item_name);names.addWidget(text(entry.job+' · '+entry.category if entry.kind=='skills' else entry.category,11,'#9cacc1'));names.addStretch();head.addLayout(names,1)
        self.watch_button=WatchButton(header)
        if hasattr(self,'watchlist'):self.watch_button.bind(self.watchlist)
        self.watch_button.set_item(self.catalog_item(entry) if entry.kind=='items' else None);head.addWidget(self.watch_button,0,Qt.AlignmentFlag.AlignTop)
        self.detail_layout.addWidget(header)
        self.animation_url='';animations=row.get('animation_urls') or {}
        if entry.kind=='monsters' and animations:
            self.animation_choice=QComboBox();self.animation_choice.setAccessibleName('Monster animation')
            labels={'move':'Move','stand':'Idle','attack1':'Attack','hit1':'Hit','die1':'Defeated','jump':'Jump'}
            for action in ('move','stand',*[k for k in animations if k not in ('move','stand')]):
                url=image_url(animations.get(action))
                if url:self.animation_choice.addItem(labels.get(action,action.replace('1','').capitalize()),url)
            self.animation_url=self.animation_choice.currentData() or '';self.detail_layout.addWidget(self.animation_choice)
            self.animation_choice.currentIndexChanged.connect(self.change_animation)
        self.sprite.set_source(entry.icon,self.animation_url)
        {'items':describe_item,'monsters':describe_monster,'skills':describe_skill}[entry.kind](self,entry,row)
        while self.section_links.count():
            button=self.section_links.takeAt(0).widget();button.hide();button.deleteLater()
        for title in ('Top',*self.section_targets):
            link=QPushButton(title);link.setObjectName('quiet');link.clicked.connect(lambda checked=False,title=title:self.scroll_to(title));self.section_links.addWidget(link)
        source=QPushButton('OSMS Data Explorer ↗');source.setObjectName('quiet')
        source.clicked.connect(lambda:self.source_requested.emit('https://osmsdataexplorer.com/'));self.detail_layout.addWidget(source,0,Qt.AlignmentFlag.AlignLeft)
        self.detail_layout.addStretch()
        self.summary.setText('');self.pages.setCurrentWidget(self.detail_page);self.detail_scroll.verticalScrollBar().setValue(0)
        self.sprite.active=self.active;self.sprite.sync();self.content.complete()
        self.service.extra.select(entry if self.active else None)
        QTimer.singleShot(0,self.observe_media)

    def scroll_to(self,section):
        self.scrolling.stop();bar=self.detail_scroll.verticalScrollBar();target=self.section_targets.get(section)
        end=min(bar.maximum(),max(0,target.mapTo(self.detail,QPoint()).y()-4)) if target else 0
        if not enabled(self):bar.setValue(end);return
        self.scrolling.setStartValue(bar.value());self.scrolling.setEndValue(end);self.scrolling.start()

    def go_back(self):
        if not self.selected:return
        state=self.history.pop() if self.history else (None,self.kind,'','',0);remaining=list(self.history)
        key,self.kind,query,category,position=state;self.kind_buttons[self.kind].setChecked(True)
        self.query.blockSignals(True);self.query.setText(query);self.query.blockSignals(False);self.fill_filters(category)
        if key:
            self.selected=None;self.open(key,False);self.detail_scroll.verticalScrollBar().setValue(position)
        else:self.search();self.results.verticalScrollBar().setValue(position)
        self.history=remaining

    def change_animation(self):
        if not self.selected:return
        self.animation_url=self.animation_choice.currentData() or '';self.sprite.set_source(self.selected.icon,self.animation_url)
        self.observe_media()

    def add_relation(self,entry,name,subtitle,icon,trailing=''):
        widget=QPushButton() if entry else QFrame()
        widget.setObjectName('referenceRelation');widget.setMinimumHeight(57)
        widget.setStyleSheet('#referenceRelation{background:#202a38;border:1px solid #2e3b4e;border-radius:8px;} #referenceRelation:hover{background:#2a394d;border-color:#626c77;}')
        row=QHBoxLayout(widget);row.setContentsMargins(9,7,9,7);row.setSpacing(8)
        image=QLabel();image.setFixedSize(32,32);image.setPixmap(self.icon(icon).pixmap(32,32));row.addWidget(image)
        words=QVBoxLayout();words.setContentsMargins(0,0,0,0);words.setSpacing(3);name_label=text(name,12,'#d9e2ef')
        if entry:name_label.setProperty('currencyIcon',False)
        words.addWidget(name_label)
        if subtitle:words.addWidget(text(subtitle,10,'#9eafc5'))
        row.addLayout(words,1)
        if trailing:
            value=text(trailing,10,'#e2bf86');value.setMaximumWidth(105);value.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter);row.addWidget(value)
        for label in widget.findChildren(QLabel):label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        if entry:widget.clicked.connect(lambda checked=False,key=entry.key:self.open(key))
        self.detail_layout.addWidget(widget);self.related.append((widget,image,icon));return widget

    def build_market(self,entry):
        self.market_label=text('',13,'#e9c88d',True);self.detail_layout.addWidget(self.market_label)
        self.section_targets['Price']=self.market_label
        self.market_button=QPushButton('View market price');self.market_button.clicked.connect(lambda:self.price_requested.emit(entry.id))
        self.detail_layout.addWidget(self.market_button,0,Qt.AlignmentFlag.AlignLeft);self.update_market()

    def update_market(self):
        if not self.selected or self.selected.kind!='items' or not getattr(self,'market_label',None):return
        item=self.catalog_item(self.selected);quote=self.market.cached(item) if self.market and item else None
        if quote and quote.price is not None:
            freshness='' if quote.fresh(time.time(),self.ttl) else ' · older reference'
            self.market_label.setText(f'Market · {quote.price:,.0f} mesos'+(' per set' if item.per_set else '')+freshness)
        else:self.market_label.setText('No market reference in the saved snapshot')
        self.market_button.setVisible(item is not None)

    def icon(self,url):
        image=QImage(str(Path(__file__).parent/'resources/meso.svg')) if url==':meso' else self.media.image(url)
        tile=QPixmap(32,32);tile.fill(Qt.GlobalColor.transparent);painter=QPainter(tile)
        if image.isNull():
            painter.setPen(QColor('#5d718d'));painter.drawRoundedRect(8,7,16,18,3,3)
        else:
            image=image.scaled(QSize(16,16) if url==':meso' else QSize(32,32),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.FastTransformation)
            painter.drawImage((32-image.width())//2,(32-image.height())//2,image)
        painter.end();icon=QIcon(tile);icon.addPixmap(tile,QIcon.Mode.Disabled);return icon

    def image_ready(self,url):
        for index in range(self.results.count()):
            row=self.results.item(index);entry=row.data(Qt.ItemDataRole.UserRole)
            if entry.icon==url:row.setIcon(self.icon(url))
        for widget,label,icon in self.related:
            if icon==url:label.setPixmap(self.icon(icon).pixmap(32,32))

    def observe_media(self,*_):
        if self.closed:return
        urls=[]
        if self.active and self.isVisible() and not self.window().isMinimized():
            if self.selected:
                viewport=self.detail_scroll.viewport()
                sprite_visible=QRect(self.sprite.mapTo(viewport,QPoint()),self.sprite.size()).intersects(viewport.rect())
                self.sprite.active=sprite_visible;self.sprite.sync()
                urls=[self.selected.icon,self.animation_url] if sprite_visible else []
                for widget,label,icon in self.related:
                    if QRect(widget.mapTo(viewport,QPoint()),widget.size()).intersects(viewport.rect()):urls.append(icon)
            else:
                viewport=self.results.viewport().rect()
                for index in range(self.results.count()):
                    row=self.results.item(index)
                    if self.results.visualItemRect(row).intersects(viewport):urls.append(row.data(Qt.ItemDataRole.UserRole).icon)
        self.media.observe(urls)

    def pause_sprite(self):
        if hasattr(self,'sprite'):self.sprite.active=False;self.sprite.sync()

    def set_active(self,active):
        self.active=active
        self.service.extra.select(self.selected if active else None)
        if hasattr(self,'sprite'):self.sprite.active=bool(active and self.selected);self.sprite.sync()
        QTimer.singleShot(0,self.observe_media)
        self.update_status()

    def sync_motion(self):
        if hasattr(self,'sprite'):self.sprite.sync()

    def reloaded(self):
        key=self.selected.key if self.selected else None;history=list(self.history);category=self.filters.currentData()
        self.fill_filters(category or '')
        if key and self.store.entry(*key):
            self.selected=None;self.open(key,False);self.history=history
        else:self.search()
        self.update_status()

    def update_status(self):
        state=self.store.metadata();stamp=state.get('generation','')
        try:stamp=datetime.fromisoformat(stamp.replace('Z','+00:00')).strftime('%b %d')
        except (ValueError,TypeError):stamp=''
        parts=['Updating database…' if self.service.busy else 'Reference data · '+stamp if stamp else 'Reference data not downloaded']
        if self.service.error:parts.append('Offline · saved data retained' if state.get('counts') else self.service.error)
        if self.service.drop_error:parts.append(self.service.drop_error)
        elif state.get('drops_checked_at'):parts.append(f"{self.store.report_count()} drop reports")
        if self.active and self.selected and self.service.extra.pending:parts.append('Checking extra drops…')
        elif self.active and self.selected:
            check=self.store.community_check(self.selected.kind,self.selected.id)
            if check and check[1].get('error'):parts.append('Extra drop reports offline')
        self.status.setText(' · '.join(parts));self.refresh.setEnabled(not self.service.busy)

    def hideEvent(self,event):self.scrolling.stop();self.pause_sprite();self.media.observe([]);super().hideEvent(event)

    def showEvent(self,event):super().showEvent(event);self.set_active(self.active)

    def close(self):
        self.closed=True;self.timer.stop();self.scrolling.stop();self.pause_sprite();self.media.close();super().close()
