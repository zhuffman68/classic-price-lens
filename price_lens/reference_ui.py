"""Released Classic World browsing, with stable entry ownership and local search."""
from datetime import datetime
from PySide6.QtCore import Qt,QTimer,Signal
from PySide6.QtGui import QKeySequence,QShortcut
from PySide6.QtWidgets import QComboBox,QHBoxLayout,QPushButton,QSizePolicy,QStackedWidget,QTabBar,QVBoxLayout,QWidget
from .motion import MotionLabel
from .reference_media import ReferenceMedia
from .reference_widgets import ReferenceList,BrowserContent,thumbnail
from .reference_details import EntryDetails
from .domain import key as name_key
from .search_field import SearchField

FAMILIES={0:'Beginner',1:'Warrior',2:'Magician',3:'Bowman',4:'Thief'}
JOBS={0:'Beginner',100:'Warrior',110:'Fighter',120:'Page',130:'Spearman',200:'Magician',210:'Fire / Poison',220:'Ice / Lightning',230:'Cleric',
      300:'Bowman',310:'Hunter',320:'Crossbowman',400:'Thief',410:'Assassin',420:'Bandit'}
CATEGORIES={'Equipment':'Equipment','Consumable':'Use','Etc':'Etc','Setup':'Setup','Cash':'Cash'}
ORDER={'Equipment':0,'Consumable':1,'Setup':2,'Etc':3,'Cash':4,'Weapon':0,'Hat':1,'Overall':2,'Top':3,'Bottom':4,'Glove':5,'Shoes':6,'Cape':7,'Shield':8,'Earring':9}
PLURALS={'Weapon':'Weapons','Hat':'Hats','Top':'Tops','Bottom':'Bottoms','Overall':'Overalls','Glove':'Gloves','Cape':'Capes','Shield':'Shields','Earring':'Earrings','Scroll':'Scrolls','Consume':'Potions & use items'}
KINDS=('items','monsters','skills','maps','quests')


class DatabasePanel(QWidget):
    source_requested=Signal(str)
    return_requested=Signal()

    def __init__(self,service,media_folder,parent=None,*,media=None):
        super().__init__(parent);self.service=service;self.store=service.store;self.media=media or ReferenceMedia(media_folder,self)
        self.kind='items';self.scope=();self.selected=None;self.history=[];self.catalog={};self.market=None;self.ttl=900;self.external_demand=None
        self.active=False;self.closed=False;self._entry=None;self.entries={};self.results_current=True;self.limit=80;self.match_count=0;self.sort_mode=None
        self.external_return=None
        self.setStyleSheet('QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;} QScrollBar::up-arrow:vertical,QScrollBar::down-arrow:vertical{width:0;height:0;}')
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(8)
        self.kind_bar=QTabBar();self.kind_bar.setExpanding(False);self.kind_bar.setDrawBase(False)
        for kind in KINDS:self.kind_bar.addTab(kind.capitalize())
        self.kind_bar.setAccessibleName('Database category');layout.addWidget(self.kind_bar,0,Qt.AlignmentFlag.AlignHCenter)
        self.kind_bar.currentChanged.connect(lambda index:self.choose_kind(KINDS[index]))
        tools=QHBoxLayout();tools.setSpacing(6)
        self.query=SearchField('Search items…');self.query.setAccessibleName('Search database')
        tools.addWidget(self.query,1);layout.addLayout(tools)
        navigation=QHBoxLayout();navigation.setSpacing(7)
        self.back=QPushButton('‹');self.back.setFixedSize(30,28);self.back.setAccessibleName('Back');self.back.setToolTip('Back · Alt+Left');self.back.clicked.connect(self.go_back)
        navigation.addWidget(self.back);self.breadcrumb=MotionLabel('Items');self.breadcrumb.setStyleSheet('font-size:11px;color:#b6c2d2')
        self.breadcrumb.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed);self.breadcrumb.setMinimumWidth(0);navigation.addWidget(self.breadcrumb,1)
        self.summary=MotionLabel();self.summary.setStyleSheet('font-size:10px;color:#9dacc0');self.summary.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
        navigation.addWidget(self.summary);layout.addLayout(navigation)
        self.content=BrowserContent();content=QVBoxLayout(self.content);content.setContentsMargins(0,0,0,0)
        self.pages=QStackedWidget();content.addWidget(self.pages);layout.addWidget(self.content,1)
        self.list_page=QWidget();listing=QVBoxLayout(self.list_page);listing.setContentsMargins(0,0,0,0);listing.setSpacing(6)
        self.sort_row=QWidget();sorts=QHBoxLayout(self.sort_row);sorts.setContentsMargins(0,0,0,0);sorts.addStretch()
        self.sort_choice=QComboBox();self.sort_choice.setAccessibleName('Sort database results');self.sort_choice.setMinimumWidth(165)
        sorts.addWidget(self.sort_choice);listing.addWidget(self.sort_row);self.sort_choice.currentIndexChanged.connect(self.sort_changed)
        self.results=ReferenceList(self.media);self.results.chosen.connect(self.choose_result);self.results.viewport_changed.connect(self.observe_media)
        listing.addWidget(self.results,1);self.more=QPushButton('Show more');listing.addWidget(self.more);self.more.hide();self.more.clicked.connect(self.show_more);self.pages.addWidget(self.list_page)
        self.tiles=ReferenceList(self.media,tiles=True);self.tiles.chosen.connect(self.enter_group);self.tiles.viewport_changed.connect(self.observe_media);self.pages.addWidget(self.tiles)
        self.status=MotionLabel();self.status.setWordWrap(True);self.status.setMinimumHeight(27);self.status.setStyleSheet('font-size:10px;color:#96a6bb');layout.addWidget(self.status)
        self.status.setToolTip('Released-content evidence: NiaMeowDB source/release indexes and dated exact-ID market sales.\nReference values and images: OSMS Data Explorer / @ohmi, CC BY 4.0.\nDrop observations: MapleClassic Wiki; extra reports: NiaMeowDB. Game artwork © Nexon.')
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(100);self.timer.timeout.connect(self.search)
        self.query.textChanged.connect(self.schedule);self.query.returnPressed.connect(self.open_first)
        self.media.ready.connect(self.image_ready);self.service.updated.connect(self.reloaded);self.service.changed.connect(self.update_status)
        self.service.extra.updated.connect(self.extra_updated);self.service.extra.changed.connect(self.update_status)
        self.service.sources.updated.connect(self.extra_updated)
        self.service.geometry.updated.connect(self.geometry_updated)
        self.focus_shortcut=QShortcut(QKeySequence('Ctrl+F'),self);self.focus_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.focus_shortcut.activated.connect(lambda:(self.query.setFocus(),self.query.selectAll()))
        self.back_shortcut=QShortcut(QKeySequence('Alt+Left'),self);self.back_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut);self.back_shortcut.activated.connect(self.go_back)
        self.search(False);self.update_status()

    @property
    def detail(self):return self._entry
    @property
    def detail_page(self):return self._entry
    @property
    def detail_scroll(self):return self._entry.tabs.currentWidget() if self._entry else None
    @property
    def item_name(self):return self._entry.item_name if self._entry else None
    @property
    def sprite(self):return self._entry.sprite if self._entry else None
    @property
    def rank_slider(self):return self._entry.rank_slider if self._entry else None
    @property
    def watch_button(self):return self._entry.watch_button if self._entry else None
    @property
    def market_label(self):return self._entry.market_label if self._entry else None
    def set_catalog(self,catalog):
        self.catalog={item.game_id:item for item in catalog.items} if catalog else {};self.update_market()

    def catalog_item(self,entry):
        item=self.catalog.get(entry.id)
        return item if item and name_key(item.name)==name_key(entry.name) else None

    def set_market(self,market,ttl):self.market=market;self.ttl=ttl;self.update_market()
    def set_watchlist(self,watchlist):self.watchlist=watchlist

    def extra_updated(self,key):
        if not self.closed and self._entry and self.selected and self.selected.key==tuple(key):
            self._entry.refresh_drops();self.update_status();self.observe_media()

    def sync_kind(self):
        self.kind_bar.blockSignals(True);self.kind_bar.setCurrentIndex(KINDS.index(self.kind));self.kind_bar.blockSignals(False)
        self.query.setPlaceholderText('Search '+self.kind+'…')

    def choose_kind(self,kind):
        if kind not in KINDS:return
        self.external_return=None
        old=KINDS.index(self.kind);new=KINDS.index(kind)
        self.content.begin();self.kind=kind;self.scope=();self.selected=None;self.history=[];self.timer.stop();self.limit=80;self.sort_mode=None
        self.query.blockSignals(True);self.query.clear();self.query.blockSignals(False);self.sync_kind();self.search(False)
        self.content.complete(1 if new>old else -1 if new<old else 0)

    def schedule(self):self.results_current=False;self.limit=80;self.timer.start()
    def scope_filters(self):return tuple((field,value) for field,value,label in self.scope)

    def sort_changed(self,*_):
        self.sort_mode=self.sort_choice.currentData();self.limit=80;self.search()

    def sorting(self):
        if self.kind=='skills':self.sort_row.hide();return 'book'
        options=[('name','Name · A–Z')]
        if self.kind in ('monsters','quests'):options=[('level','Level · low to high'),('level-desc','Level · high to low'),('name','Name · A–Z')]
        elif self.kind=='maps':options=[('name','Name · A–Z')]
        elif self.scope:
            category=self.scope[0][1]
            if category=='Equipment':options += [('level','Level · low to high'),('level-desc','Level · high to low'),('class','Class')]
            else:
                options += [('type','Type')]
                if category!='Cash':options += [('value','NPC sell value')]
                if any(value=='Scroll' for field,value,label in self.scope):options += [('rate','Scroll success rate')]
        else:options += [('type','Type')]
        if self.sort_mode not in [value for value,label in options]:self.sort_mode=options[0][0]
        self.sort_choice.blockSignals(True);self.sort_choice.clear()
        for value,label in options:self.sort_choice.addItem(label,value)
        self.sort_choice.setCurrentIndex(self.sort_choice.findData(self.sort_mode));self.sort_choice.blockSignals(False);self.sort_row.show()
        return self.sort_mode

    def group_field(self):
        if self.query.text().strip():return None
        if self.kind=='items':
            if not self.scope:return 'category'
            if len(self.scope)==1:return 'sub_category'
            if self.scope[-1][:2]==('sub_category','Weapon'):return 'weapon.type'
        if self.kind=='skills':
            if not self.scope:return 'family'
            if len(self.scope)==1 and self.scope[0][1]!=0:return 'job_id'
        if self.kind in ('maps','quests') and not self.scope:return 'region'
        return None

    def groups(self):
        field=self.group_field()
        if not field:return []
        rows=self.store.groups(self.kind,field,self.scope_filters())
        if len(rows)==1 and field=='sub_category' and rows[0]['value'] in ('Etc','Install'):return []
        if field=='category':rows.sort(key=lambda row:ORDER.get(row['value'],99))
        elif field=='sub_category':rows.sort(key=lambda row:(ORDER.get(row['value'],99),str(row['value'])))
        elif field=='family':rows.sort(key=lambda row:row['value'])
        else:rows.sort(key=lambda row:row['value'])
        result=[]
        for row in rows:
            value=row['value'];label=CATEGORIES.get(value,value) if field=='category' else PLURALS.get(value,value) if field=='sub_category' else FAMILIES.get(value,str(value)) if field=='family' else JOBS.get(value,str(value)) if field=='job_id' else value
            result.append(dict(key=(field,value),target=(field,value,label),name=str(label),subtitle=f"{row['count']:,} {self.kind}",icon=row['entry'].icon))
        return result

    def search(self,animate=True):
        if self.closed:return
        groups=self.groups();order=self.sorting();entries,count=self.store.search(self.kind,self.query.text(),scope=self.scope_filters(),limit=self.limit,sort=order)
        structure=tuple(row['key'] for row in groups) if groups else tuple(entry.key for entry in entries)
        previous=getattr(self,'search_structure',None);change=self.selected is not None or previous!=structure or bool(groups)!=(self.pages.currentWidget()==self.tiles)
        if animate and change:self.content.begin()
        self.selected=None;self.pause_sprite()
        if self.active:self.service.extra.select(None)
        self.entries={entry.key:entry for entry in entries}
        if groups:
            self.tiles.populate(groups);self.pages.setCurrentWidget(self.tiles);self.summary.setText(f'{len(groups)} groups')
        else:
            records=[]
            for entry in entries:
                subtitle=entry.job+' · '+entry.category if entry.kind=='skills' else entry.category
                if entry.kind=='items' and entry.category=='Equipment':subtitle=entry.job
                if entry.kind in ('maps','quests'):
                    record=self.store.entry(*entry.key);subtitle=record[1].get('region') or entry.category
                if entry.level is not None:subtitle+=f' · Lv. {entry.level}'
                records.append(dict(key=entry.key,target=entry.key,name=entry.name,subtitle=subtitle,icon=entry.icon))
            self.results.populate(records);self.pages.setCurrentWidget(self.list_page);self.more.setVisible(count>len(entries));self.summary.setText(f'{count:,} results')
        self.results_current=True;self.match_count=count;self.search_structure=structure
        self.update_navigation()
        if animate and change:self.content.complete()
        self.observe_media();QTimer.singleShot(0,self.observe_media)

    def enter_group(self,group):
        if not self.results_current:return
        self.history.append(self.state());self.history=self.history[-32:];self.content.begin()
        self.scope=(*self.scope,tuple(group));self.selected=None;self.query.blockSignals(True);self.query.clear();self.query.blockSignals(False);self.limit=80
        self.search(False);self.content.complete(1)

    def show_more(self):self.limit+=80;self.search()

    def choose_result(self,row):
        if not self.results_current:return
        if hasattr(row,'data'):row=row.data(Qt.ItemDataRole.UserRole)
        if row:self.open(tuple(row))

    def open_first(self):
        self.timer.stop();self.search()
        if self.pages.currentWidget()==self.list_page and self.results.count():self.choose_result(self.results.item(0))

    def state(self):
        return dict(selected=self.selected.key if self.selected else None,kind=self.kind,query=self.query.text(),scope=self.scope,
            limit=self.limit,sort=self.sort_mode,scroll=self.results.verticalScrollBar().value(),tile_scroll=self.tiles.verticalScrollBar().value(),
            details=self._entry.state() if self.selected and self._entry else {})

    def open(self,key,remember=True,direction=1):
        if self.selected and self.selected.key==key:return
        record=self.store.entry(*key)
        if not record or not self.store.available(*key):return
        if remember:self.history.append(self.state());self.history=self.history[-32:]
        self.timer.stop();self.content.begin()
        if key[0]!=self.kind and key[0] in KINDS:
            self.kind=key[0];self.scope=();self.query.blockSignals(True);self.query.clear();self.query.blockSignals(False)
        self.sync_kind();self.selected,row=record
        self.dispose_entry();self._entry=EntryDetails(self,self.selected,row);self._entry.media_changed.connect(self.observe_media)
        self.pages.addWidget(self._entry);self.pages.setCurrentWidget(self._entry)
        self._entry.set_active(self.active);self.summary.setText('');self.update_navigation();self.content.complete(direction)
        self.service.extra.select(self.selected if self.active else None);QTimer.singleShot(0,self.observe_media)
        self.service.sources.select(self.selected if self.active else None)

    def open_external(self,key):
        self.external_return=(self.state(),list(self.history));self.history=[]
        if self.selected and self.selected.key==key:self.selected=None
        self.open(key,False)

    def dispose_entry(self):
        if self._entry:
            old=self._entry;self._entry=None;old.pause();self.pages.removeWidget(old);old.hide();old.deleteLater()

    def go_back(self):
        if not self.history and self.external_return:
            state,history=self.external_return;self.external_return=None;self.history=[state]
            self.go_back();self.history=history;self.update_navigation();self.return_requested.emit();return
        if not self.history:
            if self.selected:self.selected=None;self.search()
            return
        state=self.history.pop();remaining=list(self.history);self.content.begin();self.selected=None
        self.kind=state['kind'];self.scope=tuple(state['scope']);self.limit=state.get('limit',80);self.sort_mode=state.get('sort');self.sync_kind()
        self.query.blockSignals(True);self.query.setText(state['query']);self.query.blockSignals(False)
        if state['selected']:
            self.content.finish();self.open(tuple(state['selected']),False,-1)
            if self._entry:self._entry.restore(state.get('details',{}))
        else:
            self.search(False);self.results.verticalScrollBar().setValue(state.get('scroll',0));self.tiles.verticalScrollBar().setValue(state.get('tile_scroll',0));self.content.complete(-1)
        self.history=remaining;self.update_navigation()

    def update_navigation(self):
        title=' › '.join([self.kind.capitalize(),*[str(label) for field,value,label in self.scope]])
        self.breadcrumb.setText(title);self.breadcrumb.setToolTip(title);self.back.setEnabled(bool(self.history or self.selected))

    def update_market(self):
        if self._entry:self._entry.update_market()

    def icon(self,url):return thumbnail(self.media,url,32,self.devicePixelRatioF())

    def image_ready(self,url):
        self.results.image_ready(url);self.tiles.image_ready(url)
        if self._entry:self._entry.image_ready(url)

    def observe_media(self,*_):
        if self.closed:return
        urls=[]
        visible=self.active and self.isVisible() and not self.window().isMinimized()
        if self._entry:
            self._entry.set_active(bool(visible and self.selected))
        if visible:
            if self.selected and self._entry:urls=self._entry.visible_urls()
            elif self.pages.currentWidget()==self.tiles:urls=self.tiles.nearby_urls()
            else:urls=self.results.nearby_urls()
        if not visible and self.external_demand and self.window().isVisible() and not self.window().isMinimized():urls=self.external_demand()
        self.media.observe(urls)
        row=self._entry.row if visible and self.selected and self.selected.kind=='maps' and self._entry else None
        self.service.geometry.select(row)
        if row:self.geometry_updated(row['id'])

    def geometry_updated(self,identity):
        if not self._entry or not self.selected or self.selected.key!=('maps',identity):return
        proof=self.service.geometry.cached(self._entry.row)
        names={entry.id:entry.name for entry,count in self.store.map_monsters(identity)}
        self._entry.map_preview.set_geometry(proof,names)

    def pause_sprite(self):
        if self._entry:self._entry.pause()

    def set_active(self,active):
        self.active=active;self.service.extra.select(self.selected if active else None)
        if not active:self.pause_sprite()
        QTimer.singleShot(0,self.observe_media);self.update_status()

    def sync_motion(self):
        if self._entry:self._entry.sync_motion()

    def reloaded(self):
        if self.closed:return
        if self.selected and self._entry:
            record=self.store.entry(*self.selected.key)
            if not record or not self.store.available(*self.selected.key):self.selected=None;self.search()
            elif record[1]!=self._entry.row:
                state=self._entry.state();key=self.selected.key;self.selected=None;self.open(key,False,0);self._entry.restore(state)
            else:self._entry.refresh_drops();self._entry.update_market()
        else:self.search()
        self.update_status()
        if not self.active:QTimer.singleShot(0,self.warm_landing)

    def warm_landing(self):
        if self.closed or self.active or not self.window().isVisible() or self.window().isMinimized():return
        if self.external_demand and self.external_demand():return
        urls=[row['entry'].icon for row in self.store.groups('items','category')]
        urls += [row['entry'].icon for row in self.store.groups('skills','family')]
        self.media.observe(urls[:12])

    def update_status(self):
        if self.closed:return
        state=self.store.metadata();stamp=state.get('generation','')
        try:stamp=datetime.fromisoformat(stamp.replace('Z','+00:00')).strftime('%b %d')
        except (ValueError,TypeError):stamp=''
        counts=self.store.released_counts();parts=['Updating released content…' if self.service.busy else f"Released content · {counts['items']:,} items · {counts['monsters']} monsters"]
        if stamp:parts.append('Data '+stamp)
        if self.service.error:parts.append('Saved reference data')
        if self.service.availability_error:parts.append('Release list offline')
        if self.service.drop_error:parts.append('Drop reports offline')
        if self.active and self.selected and self.service.extra.pending:parts.append('Checking sources…')
        self.status.setText(' · '.join(parts))

    def hideEvent(self,event):self.pause_sprite();self.observe_media();super().hideEvent(event)
    def showEvent(self,event):super().showEvent(event);self.set_active(self.active)

    def close(self):
        self.closed=True;self.timer.stop();self.content.finish();self.pause_sprite();self.media.close();super().close()
