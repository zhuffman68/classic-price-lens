"""Owned, compact entry views. Background reports update only their own rows."""
import json
import re
import time
from PySide6.QtCore import Qt,Signal,QTimer
from shiboken6 import isValid
from PySide6.QtWidgets import QFrame,QGridLayout,QHBoxLayout,QPushButton,QScrollArea,QSlider,QVBoxLayout,QWidget,QComboBox
from .motion import MotionLabel,RollingLabel,AnimatedTabs
from .reference_data import image_url,wiki_url
from .reference_media import ReferenceSprite
from .reference_skills import skill_ranks
from .reference_widgets import ReferenceList
from .reference_relations import quest_rewards,item_quest_sources,relationship
from .reference_maps import MapPreview
from .watchlist_ui import WatchButton
from .domain import key as name_key,Item
from .price_widgets import PriceCard

ITEM_STATS={'reqLevel':'Level required','reqSTR':'STR required','reqDEX':'DEX required','reqINT':'INT required','reqLUK':'LUK required','reqPOP':'Fame required',
    'incPAD':'Weapon attack','incMAD':'Magic attack','incPDD':'Weapon defense','incMDD':'Magic defense','incACC':'Accuracy',
    'incEVA':'Avoidability','incSTR':'STR','incDEX':'DEX','incINT':'INT','incLUK':'LUK','incMHP':'HP','incMMP':'MP',
    'incSpeed':'Speed','incJump':'Jump','incCRT':'Critical rate','incCRD':'Critical damage','tuc':'Upgrade slots','slotMax':'Stack limit',
    'incWAT':'Weapon attack','incMAT':'Magic attack','incWDEF':'Weapon defense','incMDEF':'Magic defense'}
MONSTER_STATS={'PADamage':'Weapon attack','MADamage':'Magic attack','PDDamage':'Weapon defense','MDDamage':'Magic defense',
    'acc':'Accuracy','eva':'Avoidability','speed':'Speed','pushed':'Knockback damage'}
SKILL_STATS={'mpCon':('MP cost',''),'hpCon':('HP cost',''),'damage':('Damage','%'),'mad':('Magic attack',''),
    'mobCount':('Targets',''),'attackCount':('Hits per target',''),'time':('Duration',' s'),'cooltime':('Cooldown',' s'),
    'prop':('Chance','%'),'fixdamage':('Fixed damage','')}


def text(value='',size=12,color='#dce1e8',bold=False):
    label=MotionLabel(value);label.setWordWrap(True)
    label.setStyleSheet(f'font-size:{size}px;color:{color};font-weight:{600 if bold else 400};background:transparent')
    return label


def formatted(value):
    if type(value) in (int,float):return f'{value:,.2f}'.rstrip('0').rstrip('.') if isinstance(value,float) else f'{value:,}'
    return str(value)


def heading(layout,title):layout.addWidget(text(title,12,'#e5c28b',True))


def stats(layout,values,*,columns=2,compact=False):
    if not values:return {}
    frame=QFrame();frame.setStyleSheet('QFrame{background:#222b39;border-radius:8px;}')
    grid=QGridLayout(frame);grid.setContentsMargins(12,10,12,10);grid.setHorizontalSpacing(16);grid.setVerticalSpacing(9)
    fields={}
    for index,(key,caption,value) in enumerate(values):
        cell=QWidget();cell.setStyleSheet('background:transparent');column=(QHBoxLayout if compact else QVBoxLayout)(cell);column.setContentsMargins(0,0,0,0);column.setSpacing(5 if compact else 2)
        column.addWidget(text(caption,10,'#a2afc0'));label=RollingLabel(formatted(value))
        label.setStyleSheet('font-size:15px;font-weight:600;color:#e5eaf2;background:transparent')
        if compact:column.addStretch();label.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
        column.addWidget(label);grid.addWidget(cell,index//columns,index%columns);fields[key]=label
    for index in range(columns):grid.setColumnStretch(index,1)
    layout.addWidget(frame);return fields


def page():
    widget=QWidget();layout=QVBoxLayout(widget);layout.setContentsMargins(0,8,5,0);layout.setSpacing(9)
    scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);scroll.setWidget(widget)
    return scroll,widget,layout


def facts(layout,values):
    grid=QGridLayout();grid.setContentsMargins(0,0,0,0);grid.setHorizontalSpacing(8);grid.setVerticalSpacing(5)
    for index,(caption,value) in enumerate(values):
        grid.addWidget(text(caption,10,'#a6b4c7'),index,0)
        label=text(formatted(value),12,'#e9dbc2',True);label.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(label,index,1)
    grid.setColumnStretch(0,1);layout.addLayout(grid)


class EntryDetails(QFrame):
    media_changed=Signal()

    def __init__(self,panel,entry,row):
        super().__init__();self.panel=panel;self.store=panel.store;self.media=panel.media;self.entry=entry;self.row=row
        self.lists=[];self.rank_slider=None;self.animation_url='';self.market_label=None;self.drop_list=None;self.source_list=None;self.drop_key=None
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(7)
        self.summary_card=None;self.sprite=None;self.map_preview=None
        if entry.kind=='items':
            self.summary_card=PriceCard(item=self.item_identity(),row={'name':entry.name},quote=None,now=time.time(),ttl=panel.ttl,hovered=True,selected=True,
                watchlist=getattr(panel,'watchlist',None),context_name=row.get('sub_category') or 'Item')
            layout.addWidget(self.summary_card)
            self.item_name=self.summary_card.fields['name'];self.watch_button=self.summary_card.watch_button
            self.market_label=self.summary_card.fields['market'];self.thumbnail=self.summary_card.thumbnail;self.header=self.summary_card.header;self.fields=self.summary_card.fields
            self.thumbnail.show();self.thumbnail.set_image(self.media.image(entry.icon))
        else:
            header=QWidget();head=QHBoxLayout(header);head.setContentsMargins(0,0,0,0);head.setSpacing(10)
            self.sprite=ReferenceSprite(self.media,header);head.addWidget(self.sprite,0,Qt.AlignmentFlag.AlignTop)
            names=QVBoxLayout();names.setContentsMargins(0,1,0,0);names.setSpacing(4)
            self.item_name=text(entry.name,16,'#edcf9f',True);self.item_name.setProperty('currencyIcon',False);names.addWidget(self.item_name)
            sub=row.get('sub_category') or entry.category
            names.addWidget(text(entry.job+' · '+entry.category if entry.kind=='skills' else row.get('region') or sub,10,'#9cacc1'))
            self.animations=QComboBox();self.animations.setMaximumWidth(118);self.animations.setAccessibleName('Monster animation')
            animations=row.get('animation_urls') or {};labels={'move':'Move','stand':'Idle','attack1':'Attack','hit1':'Hit','die1':'Defeated','jump':'Jump'}
            if entry.kind=='monsters':
                for action in ('move','stand',*[k for k in animations if k not in ('move','stand')]):
                    url=image_url(animations.get(action))
                    if url:self.animations.addItem(labels.get(action,action.replace('1','').capitalize()),url)
            self.animations.setVisible(self.animations.count()>1)
            if self.animations.count()>1:names.addWidget(self.animations,0,Qt.AlignmentFlag.AlignLeft)
            names.addStretch();head.addLayout(names,1)
            self.watch_button=WatchButton(header)
            if hasattr(panel,'watchlist'):self.watch_button.bind(panel.watchlist)
            self.watch_button.set_item(panel.catalog_item(entry) if entry.kind=='items' else None);head.addWidget(self.watch_button,0,Qt.AlignmentFlag.AlignTop)
            layout.addWidget(header);self.animation_url=self.animations.currentData() or '';self.sprite.set_source(entry.icon,self.animation_url)
            self.animations.currentIndexChanged.connect(self.change_animation)
        if entry.kind=='maps':
            self.map_preview=MapPreview(self.media,row);self.map_preview.chosen.connect(lambda mid:self.panel.open(('monsters',mid)))
            layout.addWidget(self.map_preview)
        self.tabs=AnimatedTabs()
        self.tabs.animation.setDuration(240)
        if self.summary_card:self.summary_card.set_panel(self.tabs);layout.addStretch()
        else:layout.addWidget(self.tabs,1)
        self.tabs.tabBar().setDrawBase(False)
        self.tabs.setStyleSheet('QTabWidget::pane{border:0;background:transparent;} QTabWidget::tab-bar{alignment:center;} QTabBar::tab{padding:6px 9px;margin:0 3px 2px 0;} QScrollArea,QScrollArea>QWidget>QWidget{background:transparent;}')
        if self.summary_card:
            self.tabs.setStyleSheet('QTabWidget{background:#222b39;border-radius:8px;} QTabWidget::pane{border:0;padding:0;} QTabWidget QWidget{background:transparent;} QTabWidget::tab-bar{alignment:center;} QTabBar::tab{padding:6px 9px;margin:0 2px 0 0;border-radius:5px;} QTabBar::tab:selected{background:#3a495f;color:#f1dfbf;} QScrollArea{border:0;}')
        overview,self.overview,body=page();self.tabs.addTab(overview,'Overview')
        if entry.kind=='items':body.setContentsMargins(7,3,7,0);body.setSpacing(7)
        if entry.kind=='items':self.item(body)
        elif entry.kind=='monsters':self.monster(body)
        elif entry.kind=='skills':self.skill(body)
        elif entry.kind=='quests':self.quest(body)
        elif entry.kind=='maps':self.map(body)
        elif entry.kind=='npcs':self.npc(body)
        body.addStretch()
        self.tabs.tabBar().setVisible(self.tabs.count()>1)
        self.tabs.currentChanged.connect(lambda *_:self.media_changed.emit())
        self.refresh_drops();self.update_market()

    def add_list(self,layout,*,drop_tiles=False):
        listing=ReferenceList(self.media,drop_tiles=drop_tiles);listing.chosen.connect(self.navigate);listing.viewport_changed.connect(self.media_changed.emit)
        layout.addWidget(listing,1);self.lists.append(listing);return listing

    def navigate(self,key):
        if isinstance(key,(tuple,list)) and len(key)==2:self.panel.open(tuple(key))

    def item(self,layout):
        row=self.row;cash=bool(row.get('cash'))
        if not row.get('scroll') and row.get('description') and name_key(row['description'])!=name_key(self.entry.name):layout.addWidget(text(row['description'],11,'#bac5d5'))
        if not cash:
            values=[(caption,str(row['stats'][key])+'%' if key in ('incCRT','incCRD') else row['stats'][key]) for key,caption in ITEM_STATS.items() if key in (row.get('stats') or {}) and not key.startswith('req')]
            if row.get('gender'):values.insert(0,('Gender',row['gender'].capitalize()))
            speed=(row.get('stats') or {}).get('attackSpeed')
            if speed is not None:values.append(('Attack speed',{2:'Faster',3:'Faster',4:'Fast',5:'Fast',6:'Normal',7:'Slow',8:'Slow',9:'Slower'}.get(speed,str(speed))))
            if values:heading(layout,'Base stats');facts(layout,values)
            required=[(caption.removesuffix(' required'),row['stats'][key]) for key,caption in ITEM_STATS.items() if key.startswith('req') and key in (row.get('stats') or {})]
            if row.get('req_classes'):required.append(('Class',', '.join(row['req_classes'])))
            if required:heading(layout,'Requirements');facts(layout,required)
            effects=row.get('spec') or {};values=[]
            for key,caption,unit in (('hp','HP restored',''),('mp','MP restored',''),('hpR','HP restored','%'),('mpR','MP restored','%'),
                ('pad','Weapon attack',''),('mad','Magic attack',''),('pdd','Weapon defense',''),('acc','Accuracy',''),('eva','Avoidability',''),('speed','Speed',''),('jump','Jump','')):
                if effects.get(key):values.append((key,caption,formatted(effects[key])+unit))
            if values:
                if effects.get('time'):values.append(('buffTime','Duration',formatted(effects['time']/60000)+' min'))
                heading(layout,'Effect');facts(layout,[(caption,value) for key,caption,value in values])
            scroll=row.get('scroll') or {}
            if scroll:
                values=[('success','Success rate',formatted(scroll['success_rate'])+'%')] if 'success_rate' in scroll else []
                values.extend((k,ITEM_STATS[k],v) for k,v in (scroll.get('stats') or {}).items() if k in ITEM_STATS)
                if scroll.get('slot'):values.append(('slot','Applies to',scroll['slot']))
                heading(layout,'Scroll effect');facts(layout,[(caption,value) for key,caption,value in values])
            if row.get('price') is not None and not (row.get('stats') or {}).get('notSale'):layout.addWidget(text(f"NPC sell-back · {formatted(row['price'])} mesos",11,'#9facc0'))
        evidence=self.store.evidence('items',self.entry.id)
        if cash:
            self.sources=self.overview;source_body=layout;self.tabs.setTabText(0,'Sources');heading(source_body,'Sources')
        else:
            source_scroll,self.sources,source_body=page();self.tabs.addTab(source_scroll,'Sources')
        labels=[]
        for record in evidence[:3]:
            if record.get('source')=='market':continue
            labels.extend(part.strip() for part in record.get('label','').split('/') if part.strip() not in ('Quest','Monster drop'))
        if labels:source_body.addWidget(text(' · '.join(dict.fromkeys(labels)),10,'#aab8ca'))
        self.source_list=self.add_list(source_body)
        if not cash:self.drop_list=self.source_list
        self.drop_note=text('',11,'#a1afc2');source_body.addWidget(self.drop_note)
        self.report_button=self.report_link(source_body)

    def npc(self,layout):
        rows=self.store.shop_inventory(self.entry.id);locations=[];items=[]
        for row in rows:
            location=relationship(self.store,'maps',row.get('map_id'),'Shop location')
            if location and location not in locations:locations.append(location)
            item=relationship(self.store,'items',row['item_id'],f"Shop · {row['price']:,} mesos")
            if item:items.append(item)
        if locations:heading(layout,'Location');self.add_list(layout).populate(locations)
        heading(layout,'Shop inventory');self.add_list(layout).populate(items)

    def monster(self,layout):
        row=self.row
        stats(layout,[(key,caption,row[key]) for key,caption in (('level','Level'),('hp','HP'),('exp','EXP')) if key in row],columns=3)
        traits=[]
        if row.get('is_boss'):traits.append('Boss')
        if row.get('undead'):traits.append('Undead')
        traits.extend(f'{element}: {status.lower()}' for element,status in (row.get('elements') or {}).items())
        if traits:layout.addWidget(text(' · '.join(traits),11,'#b5c4d5'))
        values=[(key,caption,row['stats'][key]) for key,caption in MONSTER_STATS.items() if key in (row.get('stats') or {})]
        if 'mp' in row:values.insert(0,('mp','MP',row['mp']))
        if values:heading(layout,'Combat');stats(layout,values,compact=True)
        locations_scroll,self.locations,places=page();self.tabs.addTab(locations_scroll,'Locations')
        listing=self.add_list(places);rows=[]
        for place in self.store.locations(self.entry.id):
            detail=place.get('street_name') or place.get('region','')
            if place.get('count') is not None:detail+=f" · {place['count']} spawn points"
            rows.append(dict(key=('map',place['id']),name=place['name'],subtitle=detail,icon=image_url(place.get('map_mark_url'))))
        listing.populate(rows)
        if not rows:places.addWidget(text('No verified location recorded.',11,'#a1afc2'))
        drop_scroll,self.drops,drops=page();self.tabs.addTab(drop_scroll,'Drops')
        self.drop_list=self.add_list(drops,drop_tiles=True);self.drop_note=text('',11,'#a1afc2');drops.addWidget(self.drop_note);self.report_button=self.report_link(drops)

    def quest(self,layout):
        row=self.row;npc=self.store.entry('npcs',row.get('npc_id'))
        values=[('Level',f"{row.get('level_min',0)}+")]
        if npc:values.append(('Quest giver',npc[0].name))
        if row.get('repeat'):values.append(('Repeat',row['repeat'].capitalize()))
        facts(layout,values)
        description=(row.get('description') or '').split('\n')[0]
        if description:layout.addWidget(text(description,12,'#bac5d5'))
        maps=[]
        if npc:
            for identity in npc[1].get('maps',[]):
                record=relationship(self.store,'maps',identity,'Quest giver location')
                if record and record['target']:maps.append(record)
        if maps:heading(layout,'Location');self.add_list(layout).populate(maps)
        next_id=row.get('next_quest_id')
        if next_id:
            record=relationship(self.store,'quests',next_id,'Next quest')
            if record and record['target']:self.add_list(layout).populate([record])
        requirements,_,body=page();self.tabs.addTab(requirements,'Requirements');records=[];other=[]
        for index,requirement in enumerate(row.get('requirements',[])):
            kind={'mob':'monsters','item':'items','quest':'quests','skill':'skills'}.get(requirement.get('type'))
            if kind:
                quantity=requirement.get('count');caption=f"×{quantity:,}" if type(quantity) is int else 'Completed' if kind=='quests' else 'Rank '+str(requirement.get('level','—'))
                record=relationship(self.store,kind,requirement.get('id'),caption,key=('requirement',index))
                if record:records.append(record)
            elif requirement.get('type')=='citizenship':other.append((requirement.get('town','Citizenship'),'Grade '+str(requirement.get('grade','—'))))
        if records:self.add_list(body).populate(records)
        if other:facts(body,other)
        if not records and not other:body.addWidget(text('No additional requirements.',11,'#a6b4c7'))
        rewards,_,body=page();self.tabs.addTab(rewards,'Rewards');records=[];numbers=[]
        for reward in quest_rewards(row):
            kind=reward.get('type')
            if kind in ('money','exp'):
                value=reward.get('value')
                if type(value) in (int,float):numbers.append(('EXP' if kind=='exp' else 'mesos',f'{value:,.0f}'))
            elif kind=='item':
                quantity=reward.get('count',1);caption=f"×{quantity:,} · "+reward['caption'] if type(quantity) is int else reward['caption']
                record=relationship(self.store,'items',reward.get('id'),caption,key=reward['key'])
                if record:records.append(record)
        if numbers:
            totals=QHBoxLayout();totals.setContentsMargins(0,0,0,0);totals.setSpacing(18)
            for caption,value in numbers:totals.addWidget(text(value+' '+caption,13,'#e9dbc2',True))
            totals.addStretch();body.addLayout(totals)
        if records:self.add_list(body).populate(records)
        source=QPushButton('Quest source ↗');source.setObjectName('quiet');source.clicked.connect(lambda:self.panel.source_requested.emit('https://meowdb.com/msclassic/quest-tracker/'+str(self.entry.id)))
        layout.addWidget(source,0,Qt.AlignmentFlag.AlignLeft)

    def map(self,layout):
        self.tabs.setTabText(0,'Monsters');records=[]
        for entry,count in self.store.map_monsters(self.entry.id):
            records.append(dict(key=entry.key,target=entry.key,name=entry.name,subtitle=f'Lv. {entry.level} · {count} spawn '+('point' if count==1 else 'points'),icon=entry.icon))
        if records:self.add_list(layout).populate(records)
        else:layout.addWidget(text('No released monster spawns recorded.',11,'#a6b4c7'))
        links,_,body=page();self.tabs.addTab(links,'Connections');records=[]
        for identity in dict.fromkeys(self.row.get('exits',[])):
            if identity==self.entry.id:continue
            record=relationship(self.store,'maps',identity,'Connected map')
            if record and record['target']:records.append(record)
        if records:self.add_list(body).populate(records)
        else:body.addWidget(text('No verified connections recorded.',11,'#a6b4c7'))
        self.map_note=text('',10,'#96a6bb');body.addWidget(self.map_note)

    def skill(self,layout):
        row=self.row;description=re.sub(r'^\[Master Level:\s*\d+\]\s*','',row.get('description') or '')
        if description:layout.addWidget(text(description,12,'#bac5d5'))
        if row.get('passive'):layout.addWidget(text('Passive',11,'#a7b5c7'))
        levels,descriptions,notes=skill_ranks(row)
        if levels:
            ranks={level['level']:level for level in levels};maximum=max(ranks)
            controls=QWidget();bar=QHBoxLayout(controls);bar.setContentsMargins(0,0,0,0)
            rank=text(f'Rank {maximum} / {maximum}',12,'#edc68a',True);rank.setMinimumWidth(94)
            self.rank_slider=QSlider(Qt.Orientation.Horizontal);self.rank_slider.setRange(min(ranks),maximum);self.rank_slider.setValue(maximum)
            self.rank_slider.setAccessibleName('Skill rank');self.rank_slider.setObjectName('referenceRank')
            self.rank_slider.setStyleSheet('QSlider::groove:horizontal{height:5px;background:#354257;border-radius:2px;} QSlider::sub-page:horizontal{background:#c9ab78;border-radius:2px;} QSlider::handle:horizontal{width:13px;height:13px;margin:-5px 0;background:#edc68a;border:1px solid #b79761;border-radius:6px;}')
            bar.addWidget(rank);bar.addWidget(self.rank_slider,1);layout.addWidget(controls)
            initial=ranks[maximum];per_level=text(descriptions[maximum-1] if len(descriptions)>=maximum else '',12,'#c8d3e2');layout.addWidget(per_level)
            fields=stats(layout,[(key,caption,formatted(initial[key])+unit if key in initial else '—') for key,(caption,unit) in SKILL_STATS.items() if any(key in level for level in levels)])
            def update(value):
                level=ranks.get(value,{})
                rank.setText(f'Rank {value} / {maximum}');per_level.setText(descriptions[value-1] if len(descriptions)>=value else '')
                per_level.setToolTip(notes.get(value,''))
                for key,label in fields.items():
                    label.setText(formatted(level[key])+SKILL_STATS[key][1] if key in level else '—');label.setToolTip(notes.get(value,''))
            self.rank_slider.valueChanged.connect(update)
            per_level.setToolTip(notes.get(maximum,''))
            for label in fields.values():label.setToolTip(notes.get(maximum,''))
        required=[]
        for item in row.get('required_skills') or []:
            target=self.store.entry('skills',item.get('skill_id'))
            if target:required.append(dict(key=target[0].key,target=target[0].key,name=target[0].name,subtitle=f"Rank {item.get('level','—')}",icon=target[0].icon))
        if required:
            heading(layout,'Prerequisites');listing=self.add_list(layout);listing.setMaximumHeight(min(170,len(required)*62));listing.populate(required)

    def report_link(self,layout):
        button=QPushButton('Source reports ↗');button.setObjectName('quiet');button.hide()
        layout.addWidget(button,0,Qt.AlignmentFlag.AlignLeft);button.clicked.connect(self.open_reports);return button

    def open_reports(self):
        rows=self.store.drops_for(self.entry.kind,self.entry.id)
        if not rows:return
        row=rows[0]
        if row.get('source')=='meow':url=row.get('source_url')
        else:url=wiki_url(row.get('page') if self.entry.kind=='monsters' else row.get('item_page') or self.entry.name)
        if url:self.panel.source_requested.emit(url)

    def refresh_drops(self):
        listing=self.source_list if self.entry.kind=='items' else self.drop_list
        if listing is None:return
        rows=[] if self.row.get('cash') else self.store.drops_for(self.entry.kind,self.entry.id)
        quests=item_quest_sources(self.store,self.entry.id) if self.entry.kind=='items' else []
        sources=self.store.sources_for(self.entry.id) if self.entry.kind=='items' else []
        fingerprint=json.dumps([rows,quests,sources],sort_keys=True)
        if fingerprint==self.drop_key:return
        self.drop_key=fingerprint;records=[]
        for row in sources:
            kind='npcs' if row['kind']=='npc' else 'items';source=self.store.entry(kind,row['id'])
            if source is None:continue
            detail=f"Shop · {row['price']:,} mesos" if row['kind']=='npc' else 'Reward box · player reported'
            records.append(dict(key=('source',row['kind'],row['id']),target=source[0].key if self.store.available(*source[0].key) else None,
                name=source[0].name,subtitle=detail,icon=source[0].icon,
                tip=' · '.join(filter(None,(row.get('map_name'),row.get('basis'),row.get('source_url'))))))
        for row in rows:
            kind,identity=('monsters',row['monster_id']) if self.entry.kind=='items' else ('items',row['item_id'])
            target=self.store.entry(kind,identity) if identity is not None else None
            name=target[0].name if target else 'Currency' if row['category']=='meso' else 'No item or currency'
            details=[]
            if row.get('minimum') is not None:
                low,high=row['minimum'],row.get('maximum');details.append(str(low) if high in (None,low) else f'{low}–{high}')
            rate=f"{row['rate']:.2f}% observed" if row.get('rate') is not None else 'Disputed report' if row.get('disputed') else 'Reported'
            details.append(rate)
            if row.get('observed') is not None and row.get('kills'):details.append(f"{row['observed']:,} / {row['kills']:,} kills")
            tip=['NiaMeowDB report' if row.get('source')=='meow' else 'MapleClassic Wiki observation']
            if row.get('version'):tip.append('Game version '+row['version'])
            if row.get('date'):tip.append('Observed '+row['date'])
            if row.get('low') is not None and row.get('high') is not None:tip.append(f"Reported interval: {row['low']:g}–{row['high']:g}%")
            if row.get('source')=='meow':tip.append(f"Votes: {row.get('upvotes',0):g} for / {row.get('downvotes',0):g} against; not a rate")
            if row.get('also_reported'):tip.append('Also reported on NiaMeowDB')
            if row.get('quest'):details.append('Quest drop')
            tip.extend(details)
            records.append(dict(key=(row['monster_id'],row['item_id'],row['category']),target=target[0].key if target else None,
                name=name,subtitle=' · '.join(details),rate=rate,icon=target[0].icon if target else ':meso' if row['category']=='meso' else '',tip='\n'.join(tip)))
        records+=quests
        listing.populate(records);self.report_button.setVisible(bool(rows))
        self.drop_note.setText('' if rows or self.row.get('cash') else 'No confirmed monster-drop reports recorded.' if self.entry.kind=='items' else 'No confirmed drop reports recorded.')
        self.drop_note.setVisible(not records);self.media_changed.emit()

    def item_identity(self):
        item=self.panel.catalog_item(self.entry)
        return item or Item(self.entry.id,self.entry.name,self.row.get('category')=='Equipment' or 1000000<=self.entry.id<2000000,
            self.entry.id//10000 in (207,233),cash=bool(self.row.get('cash')),gender=self.row.get('gender'))

    def update_data(self,**data):
        # PriceSearch owns selection changes; quote updates reuse this summary.
        if self.summary_card:
            data['selected']=True;data['context_name']=self.row.get('sub_category') or ('Cash item' if self.row.get('cash') else self.entry.category)
            self.summary_card.update_data(**data)

    def update_market(self):
        if self.summary_card is None:return
        item=self.item_identity();market=self.panel.market
        quote=market.cached(item) if market else None
        if quote is None and market and hasattr(market,'reference'):quote=market.reference(item)
        state=market.state_for(item.game_id) if market and hasattr(market,'state_for') else ''
        self.update_data(item=item,row={'name':item.name},quote=quote,now=time.time(),ttl=self.panel.ttl,hovered=True,lookup_state=state,open_source=self.panel.source_requested.emit)

    def change_animation(self):
        self.animation_url=self.animations.currentData() or '';self.sprite.set_source(self.entry.icon,self.animation_url);self.media_changed.emit()

    def visible_urls(self):
        urls=[self.entry.icon,self.animation_url]
        if self.map_preview:urls.append(self.row.get('minimap_url',''))
        for listing in self.lists:
            if listing.isVisible():urls+=listing.nearby_urls()
        return urls

    def image_ready(self,url):
        if self.summary_card and url==self.entry.icon:self.thumbnail.set_image(self.media.image(url))
        if self.map_preview:self.map_preview.update()
        for listing in self.lists:listing.image_ready(url)

    def set_active(self,active):
        if self.sprite:self.sprite.active=active;self.sprite.sync()

    def sync_motion(self):
        if self.sprite:self.sprite.sync()

    def pause(self):self.set_active(False)

    def state(self):
        return {'tab':self.tabs.currentIndex(),'scrolls':[self.tabs.widget(i).verticalScrollBar().value() for i in range(self.tabs.count())],
                'lists':[listing.verticalScrollBar().value() for listing in self.lists], 'rank':self.rank_slider.value() if self.rank_slider else None}

    def restore(self,state):
        self.tabs.setCurrentIndex(min(state.get('tab',0),self.tabs.count()-1))
        if self.rank_slider and state.get('rank'):self.rank_slider.setValue(state['rank'])
        for index,value in enumerate(state.get('scrolls',[])[:self.tabs.count()]):self.tabs.widget(index).verticalScrollBar().setValue(value)
        def restore_lists():
            for listing,value in zip(self.lists,state.get('lists',[])):
                if isValid(listing):listing.verticalScrollBar().setValue(value)
        QTimer.singleShot(0,restore_lists)
