"""Compact reference cards and links; source numbers keep their own units."""
import re
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame,QGridLayout,QHBoxLayout,QPushButton,QSlider,QVBoxLayout,QWidget
from .motion import MotionLabel,RollingLabel
from .reference_data import wiki_url
from .reference_skills import skill_ranks

ITEM_STATS={'reqLevel':'Level required','reqSTR':'STR required','reqDEX':'DEX required','reqINT':'INT required','reqLUK':'LUK required',
    'incPAD':'Weapon attack','incMAD':'Magic attack','incPDD':'Weapon defense','incMDD':'Magic defense','incACC':'Accuracy',
    'incEVA':'Avoidability','incSTR':'STR','incDEX':'DEX','incINT':'INT','incLUK':'LUK','incMHP':'HP','incMMP':'MP',
    'incSpeed':'Speed','incJump':'Jump','incCRT':'Critical rate','incCRD':'Critical damage','tuc':'Upgrade slots','slotMax':'Stack limit',
    'incWAT':'Weapon attack','incMAT':'Magic attack','incWDEF':'Weapon defense','incMDEF':'Magic defense'}
MONSTER_STATS={'PADamage':'Weapon attack','MADamage':'Magic attack','PDDamage':'Weapon defense','MDDamage':'Magic defense',
    'acc':'Accuracy','eva':'Avoidability','speed':'Speed','pushed':'Knockback damage'}
SKILL_STATS={'mpCon':('MP cost',''),'hpCon':('HP cost',''),'damage':('Damage','%'),'mad':('Magic attack',''),
    'mobCount':('Targets',''),'attackCount':('Hits per target',''),'time':('Duration','s'),'cooltime':('Cooldown','s'),
    'prop':('Chance','%'),'fixdamage':('Fixed damage','')}


def text(value='',size=12,color='#dce1e8',bold=False):
    label=MotionLabel(value);label.setWordWrap(True)
    label.setStyleSheet(f'font-size:{size}px;color:{color};font-weight:{650 if bold else 400};background:transparent')
    return label


def heading(layout,title,subtitle=''):
    label=text(title,13,'#e5c28b',True);layout.addWidget(label)
    if subtitle:layout.addWidget(text(subtitle,10,'#9facc0'))
    return label


def formatted(value):
    if type(value) in (int,float):return f'{value:,.2f}'.rstrip('0').rstrip('.') if isinstance(value,float) else f'{value:,}'
    return str(value)


def stats(layout,values):
    frame=QFrame();frame.setStyleSheet('QFrame{background:#222b39;border-radius:9px;}')
    grid=QGridLayout(frame);grid.setContentsMargins(12,10,12,10);grid.setHorizontalSpacing(18);grid.setVerticalSpacing(10)
    fields={}
    for index,(key,caption,value) in enumerate(values):
        cell=QWidget();cell.setStyleSheet('background:transparent');column=QVBoxLayout(cell);column.setContentsMargins(0,0,0,0);column.setSpacing(3)
        column.addWidget(text(caption,10,'#a2afc0'))
        label=RollingLabel(formatted(value));label.setStyleSheet('font-size:16px;font-weight:600;color:#e5eaf2;background:transparent')
        column.addWidget(label);grid.addWidget(cell,index//2,index%2);fields[key]=label
    grid.setColumnStretch(0,1);grid.setColumnStretch(1,1)
    layout.addWidget(frame);return fields


def describe_item(panel,entry,row):
    layout=panel.detail_layout
    if row.get('description'):layout.addWidget(text(row['description'],12,'#bac5d5'))
    if row.get('req_classes'):layout.addWidget(text('For '+', '.join(row['req_classes']),11,'#aab8c9'))
    values=[(key,caption,row['stats'][key]) for key,caption in ITEM_STATS.items() if key in (row.get('stats') or {})]
    if row.get('gender'):values.insert(0,('gender','Gender',row['gender'].capitalize()))
    speed=(row.get('stats') or {}).get('attackSpeed')
    if speed is not None:values.append(('speed','Attack speed',{2:'Faster',3:'Faster',4:'Fast',5:'Fast',6:'Normal',7:'Slow',8:'Slow',9:'Slower'}.get(speed,str(speed))))
    if values:heading(layout,'Base stats');stats(layout,values)
    effects=row.get('spec') or {}
    effect_values=[(key,caption,formatted(effects[key])+unit) for key,caption,unit in
                   (('hp','HP restored',''),('mp','MP restored',''),('hpR','HP restored','%'),('mpR','MP restored','%')) if key in effects]
    if effect_values:stats(layout,effect_values)
    scroll=row.get('scroll')
    if scroll:
        values=[('success','Success rate',formatted(scroll['success_rate'])+'%')] if 'success_rate' in scroll else []
        values.extend((k,ITEM_STATS[k],v) for k,v in (scroll.get('stats') or {}).items() if k in ITEM_STATS)
        if values:stats(layout,values)
    if row.get('cash'):
        if row.get('nx_price') is not None:layout.addWidget(text(f"Cash Shop · {row['nx_price']:,} NX",11,'#9facc0'))
    elif row.get('price') is not None:layout.addWidget(text(f"NPC sell-back · {formatted(row['price'])} mesos",11,'#9facc0'))
    panel.build_market(entry)
    build_drops(panel,entry)


def describe_monster(panel,entry,row):
    layout=panel.detail_layout
    values=[(key,caption,row[key]) for key,caption in (('level','Level'),('hp','HP'),('mp','MP'),('exp','EXP')) if key in row]
    values.extend((key,caption,row['stats'][key]) for key,caption in MONSTER_STATS.items() if key in (row.get('stats') or {}))
    stats(layout,values)
    traits=[]
    if row.get('is_boss'):traits.append('Boss')
    if row.get('undead'):traits.append('Undead')
    for element,status in (row.get('elements') or {}).items():traits.append(f'{element}: {status.lower()}')
    if traits:layout.addWidget(text(' · '.join(traits),11,'#b5c4d5'))
    locations=panel.store.locations(entry.id)
    panel.section_targets['Locations']=heading(layout,'Locations',f"{len(locations)} map{'s' if len(locations)!=1 else ''}")
    if not locations:layout.addWidget(text('No locations listed in this dataset.',11,'#9facc0'))
    for place in locations:
        detail=place.get('street_name') or place.get('region','')
        if place.get('count') is not None:detail+=f" · {place['count']} spawn points"
        panel.add_relation(None,place['name'],detail,'')
    build_drops(panel,entry)


def describe_skill(panel,entry,row):
    layout=panel.detail_layout
    description=re.sub(r'^\[Master Level:\s*\d+\]\s*','',row.get('description') or '')
    if description:layout.addWidget(text(description,12,'#bac5d5'))
    if row.get('mechanics'):layout.addWidget(text(str(row['mechanics']).capitalize()+(' · Passive' if row.get('passive') and row['mechanics']!='passive' else ''),11,'#a7b5c7'))
    levels,descriptions,rank_notes=skill_ranks(row)
    if levels:
        bar=QHBoxLayout();rank=text('',12,'#edc68a',True);rank.setMinimumWidth(92)
        slider=QSlider(Qt.Orientation.Horizontal);slider.setRange(1,max(level['level'] for level in levels));slider.setValue(slider.maximum())
        slider.setAccessibleName('Skill rank');slider.setObjectName('referenceRank');bar.addWidget(rank);bar.addWidget(slider,1);layout.addLayout(bar)
        slider.setStyleSheet('QSlider::groove:horizontal{height:5px;background:#354257;border-radius:2px;} QSlider::sub-page:horizontal{background:#d9ad66;border-radius:2px;} QSlider::handle:horizontal{width:13px;height:13px;margin:-5px 0;background:#edc68a;border:1px solid #b79761;border-radius:6px;}')
        panel.section_targets['Rank']=slider
        per_level=text('',12,'#c8d3e2');layout.addWidget(per_level)
        # Client rank text explains skill-specific x/y fields without guessing.
        fields=stats(layout,[(key,caption,'—') for key,(caption,unit) in SKILL_STATS.items() if any(key in level for level in levels)])
        def update(value):
            level=next((level for level in levels if level['level']==value),{})
            rank.setText(f'Rank {value} / {slider.maximum()}')
            per_level.setText(str(descriptions[value-1]) if len(descriptions)>=value else '')
            per_level.setToolTip(rank_notes.get(value,''))
            for key,label in fields.items():label.setText(formatted(level[key])+SKILL_STATS[key][1] if key in level else '—')
            for label in fields.values():label.setToolTip(rank_notes.get(value,''))
        slider.valueChanged.connect(update);update(slider.value());panel.rank_slider=slider
    elif row.get('max_level') and row.get('job_tier')!='Crafting':layout.addWidget(text(f"Maximum rank · {row['max_level']}",12,'#b8c6d8'))
    required=row.get('required_skills') or []
    if required:heading(layout,'Prerequisites')
    for required_skill in required:
        target=panel.store.entry('skills',required_skill.get('skill_id'))
        if target:panel.add_relation(target[0],target[0].name,f"Rank {required_skill.get('level','—')}",target[0].icon)


def build_drops(panel,entry):
    rows=panel.store.drops_for(entry.kind,entry.id);layout=panel.detail_layout
    panel.section_targets['Drops']=heading(layout,'Dropped by' if entry.kind=='items' else 'Drops','Community reports · sampled rates where available')
    if not rows:layout.addWidget(text('No reported drops in the saved dataset.',11,'#9facc0'))
    for row in rows:
        kind,identity=('monsters',row['monster_id']) if entry.kind=='items' else ('items',row['item_id'])
        target=panel.store.entry(kind,identity) if identity is not None else None
        if target:
            name=target[0].name;icon=target[0].icon
        else:name='Currency' if row['category']=='meso' else 'No item or currency';icon=':meso' if row['category']=='meso' else ''
        details=[]
        if row.get('minimum') is not None:
            low,high=row['minimum'],row.get('maximum');details.append(str(low) if high in (None,low) else f'{low}–{high}')
        if row.get('quest'):details.append('Quest drop')
        if row.get('observed') is not None and row.get('kills'):details.append(f"{row['observed']:,} / {row['kills']:,} kills")
        if row.get('version'):details.append('v'+row['version'])
        rate=f"{row['rate']:.2f}% observed" if row.get('rate') is not None else 'Disputed report' if row.get('disputed') else 'Reported' if row.get('source')=='meow' else 'Rate unknown'
        widget=panel.add_relation(target[0] if target else None,name,' · '.join(details),icon,trailing=rate)
        provenance=[]
        provenance.append('NiaMeowDB community report' if row.get('source')=='meow' else 'MapleClassic Wiki observation')
        if row.get('source')=='meow':provenance.append(f"Votes: {row.get('upvotes',0):g} for / {row.get('downvotes',0):g} against (not a drop rate)")
        if row.get('also_reported'):provenance.append('Also reported on NiaMeowDB')
        if row.get('date'):provenance.append('Observed '+row['date'])
        if row.get('low') is not None and row.get('high') is not None:provenance.append(f"Reported interval: {row['low']:g}–{row['high']:g}%")
        widget.setToolTip('\n'.join(provenance))
    source=next((r.get('page') if entry.kind=='monsters' else r.get('item_page') for r in rows),entry.name)
    button=QPushButton('View drop reports ↗');button.setObjectName('quiet')
    button.clicked.connect(lambda:panel.source_requested.emit(wiki_url(source or entry.name)));layout.addWidget(button,0,Qt.AlignmentFlag.AlignLeft)
    check=panel.store.community_check(entry.kind,entry.id)
    extra_url=check[1].get('source_url') if check else None
    if extra_url and extra_url.startswith('https://meowdb.com/msclassic/'):
        extra=QPushButton('NiaMeowDB reports ↗');extra.setObjectName('quiet')
        extra.clicked.connect(lambda:panel.source_requested.emit(extra_url));layout.addWidget(extra,0,Qt.AlignmentFlag.AlignLeft)
