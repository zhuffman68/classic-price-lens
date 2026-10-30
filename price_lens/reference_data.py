"""Versioned Classic World references and observed drops; no capture/game access."""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
import hashlib
import html
import json
import math
from pathlib import Path
import re
import sqlite3
import time
from urllib.parse import urlencode,quote,urlsplit

API='https://osmsdataexplorer.com/data/api/v1/'
WIKI='https://mapleclassic.wiki/'
FILES=('items.json','cash_shop.json','monsters.json','skills.json','maps.json','npcs.json','quests.json')
RELEASED_KINDS=('items','monsters','maps','quests')
RELEASE_RULES={
    'quests':"COALESCE(json_extract(e.body,'$.region'),'')!='Forgotten Hollow'",
    'maps':"COALESCE(json_extract(e.body,'$.region'),'')!='Dev' AND NOT EXISTS(SELECT 1 FROM json_each(e.body,'$.mobs') p WHERE json_extract(p.value,'$.mob_id') BETWEEN 54 AND 63 OR json_extract(p.value,'$.mob_id')=700003)"}
DAY=86400


def excluded(kind,identity,name):
    """Content explicitly outside ordinary released play, checked 2026-10-28.

    Forgotten Hollow is scheduled for November 18. A scheduled date alone does
    not unlock these records: this rule needs a verified release update.
    """
    if name.startswith(('GM ','Test(')):return True
    return kind=='monsters' and (identity in range(54,64) or identity==700003)


GROUP_FIELDS={'category':'e.category','sub_category':"json_extract(e.body,'$.sub_category')",'weapon.type':"json_extract(e.body,'$.weapon.type')",
    'job_id':"json_extract(e.body,'$.job_id')",'family':"CAST(json_extract(e.body,'$.job_id')/100 AS INTEGER)",'region':"json_extract(e.body,'$.region')",
    'quest.section':"CASE WHEN json_extract(e.body,'$.region') IN ('Warrior','Magician','Bowman','Thief') THEN 'Job advancement' WHEN json_extract(e.body,'$.region') IN ('Citizenship','Crafting','Event') THEN 'Systems & events' ELSE 'Towns' END"}
CLASS_LABEL="CASE WHEN e.kind='items' THEN COALESCE((SELECT GROUP_CONCAT(j.value, ', ') FROM json_each(e.body,'$.req_classes') j),'All classes') ELSE e.job END"
CLASS_ORDER="COALESCE((SELECT MIN(CASE j.value WHEN 'Warrior' THEN 1 WHEN 'Magician' THEN 2 WHEN 'Bowman' THEN 3 WHEN 'Thief' THEN 4 ELSE 5 END) FROM json_each(e.body,'$.req_classes') j),0)"
SORTS={'name':'e.name COLLATE NOCASE,e.id','level':'e.level IS NULL,e.level,e.name COLLATE NOCASE,e.id',
    'level-desc':'e.level IS NULL,e.level DESC,e.name COLLATE NOCASE,e.id','class':CLASS_ORDER+',e.level,e.name COLLATE NOCASE,e.id',
    'type':"e.category,COALESCE(json_extract(e.body,'$.sub_category'),''),e.name COLLATE NOCASE,e.id",
    'value':"json_extract(e.body,'$.price') IS NULL,json_extract(e.body,'$.price') DESC,e.name COLLATE NOCASE,e.id",
    'rate':"json_extract(e.body,'$.scroll.success_rate') IS NULL,json_extract(e.body,'$.scroll.success_rate'),e.name COLLATE NOCASE,e.id",'book':'e.id'}


def scoped(where,params,scope):
    for field,value in scope:
        expression=GROUP_FIELDS.get(field)
        if expression is None:raise ValueError('Unsupported browse category')
        where.append(expression+'=?');params.append(value)


def image_url(url):
    if not isinstance(url,str) or len(url)>600:return ''
    try:parsed=urlsplit(url)
    except ValueError:return ''
    return url if (parsed.scheme=='https' and parsed.netloc=='osmsdataexplorer.com'
                   and parsed.path.startswith('/data/') and not parsed.query and not parsed.fragment
                   and parsed.path.endswith(('.png','.webp'))) else ''


def wiki_url(page):
    return WIKI+'wiki/'+quote(str(page).replace(' ','_'),safe='')


def drop_url(offset=0):
    fields=('m.id=monster_id,m.name_en=monster_name,i.id=item_id,i.name_en=item_name,'
            'd.drop_rate=rate,d.min_quantity=minimum,d.max_quantity=maximum,'
            'd.sample_kills=kills,d.sample_drops=observed,d.game_version=version,'
            'd.observed_on=date,d.quest_flag=quest,d.rate_low=low,d.rate_high=high,'
            'd.monster_id=page,d.item_id=item_page,d.category=category')
    return WIKI+'api.php?'+urlencode(dict(action='cargoquery',tables='monster_drops=d,monsters=m,items=i',
        fields=fields,join_on='d.monster_id=m._pageName,d.item_id=i._pageName',
        where='m.variant IS NULL OR m.variant=""',order_by='d._ID,m.id,i.id',limit=500,offset=offset,format='json'))


def validate_meta(meta):
    if not isinstance(meta,dict) or type(meta.get('schema_version')) is not int or meta['schema_version']!=1 or meta.get('game')!='MapleStory Classic World':
        raise ValueError('Unsupported Classic World database')
    stamp=meta.get('data_updated_at')
    if not isinstance(stamp,str) or not datetime.fromisoformat(stamp.replace('Z','+00:00')).tzinfo:raise ValueError('Missing database date')
    if not re.fullmatch(r'[a-f0-9]{20,64}',str(meta.get('client_build',''))):raise ValueError('Missing database build')
    for name in FILES:
        row=meta.get('files',{}).get(name,{})
        if not re.fullmatch(r'[a-f0-9]{64}',str(row.get('sha256',''))):raise ValueError('Missing database hash')
        if type(row.get('bytes')) is not int or not 1<=row['bytes']<=8*1024*1024:raise ValueError('Database file too large')
        if type(row.get('records')) is not int or not 1<=row['records']<=20000:raise ValueError('Invalid database count')
    return meta


def _rows(meta,name,raw):
    info=meta['files'][name]
    if len(raw)!=info['bytes'] or hashlib.sha256(raw).hexdigest()!=info['sha256']:
        raise ValueError('Database download failed verification: '+name)
    rows=json.loads(raw)
    if not isinstance(rows,list) or len(rows)!=info['records']:raise ValueError('Database record count changed')
    used=set();identity_key='item_id' if name=='cash_shop.json' else 'id'
    for row in rows:
        if not isinstance(row,dict):raise ValueError('Invalid database record')
        identity=row.get(identity_key)
        if type(identity) is not int or not 0<=identity<=2147483647 or identity in used:raise ValueError('Invalid or duplicate database ID')
        if not isinstance(row.get('name'),str) or len(row['name'])>300:raise ValueError('Missing database name')
        for key in ('stats','spec','scroll','animation_urls'):
            if key in row and not isinstance(row[key],dict):raise ValueError('Invalid reference fields')
        if 'description' in row and (not isinstance(row['description'],str) or len(row['description'])>16000):raise ValueError('Invalid reference description')
        if 'req_classes' in row and (not isinstance(row['req_classes'],list) or any(not isinstance(v,str) for v in row['req_classes'])):raise ValueError('Invalid class requirements')
        for key in ('spawns','levels','required_skills','requirements','rewards','reward_choices','reward_random','mobs','portals','npcs'):
            if key in row and (not isinstance(row[key],list) or len(row[key])>2000 or any(not isinstance(v,dict) for v in row[key])):raise ValueError('Invalid reference relationships')
        for spawn in row.get('spawns',[]):
            if type(spawn.get('map_id')) is not int or 'count' in spawn and (type(spawn['count']) is not int or not 0<=spawn['count']<=10000):raise ValueError('Invalid monster location')
        for level in row.get('levels',[]):
            if type(level.get('level')) is not int or not 1<=level['level']<=200:raise ValueError('Invalid skill rank')
        if 'level_descriptions' in row and (not isinstance(row['level_descriptions'],list) or any(not isinstance(v,str) for v in row['level_descriptions'])):raise ValueError('Invalid rank descriptions')
        used.add(identity)
    return rows


@dataclass(frozen=True)
class Entry:
    kind:str
    id:int
    name:str
    category:str
    level:int|None=None
    job:str=''
    icon:str=''

    @property
    def key(self):return self.kind,self.id


class ReferenceStore:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT);
                CREATE TABLE IF NOT EXISTS files(name TEXT PRIMARY KEY,hash TEXT,payload BLOB);
                CREATE TABLE IF NOT EXISTS entities(kind TEXT,id INTEGER,name TEXT,category TEXT,level INTEGER,job TEXT,icon TEXT,body TEXT,PRIMARY KEY(kind,id));
                CREATE VIRTUAL TABLE IF NOT EXISTS lookup USING fts5(kind UNINDEXED,id UNINDEXED,name);
                CREATE TABLE IF NOT EXISTS drops(monster_id INTEGER,item_id INTEGER,category TEXT,body TEXT);
                CREATE INDEX IF NOT EXISTS drop_monster ON drops(monster_id);
                CREATE INDEX IF NOT EXISTS drop_item ON drops(item_id);
                CREATE TABLE IF NOT EXISTS community_reports(monster_id INTEGER,item_id INTEGER,body TEXT,PRIMARY KEY(monster_id,item_id));
                CREATE TABLE IF NOT EXISTS community_checks(kind TEXT,id INTEGER,saved REAL,detail TEXT,PRIMARY KEY(kind,id));
                CREATE TABLE IF NOT EXISTS availability(kind TEXT,id INTEGER,name TEXT,source TEXT,first_seen REAL,last_seen REAL,detail TEXT,PRIMARY KEY(kind,id,source));
                CREATE INDEX IF NOT EXISTS available_entity ON availability(kind,id,name);
                CREATE TABLE IF NOT EXISTS item_sources(kind TEXT,item_id INTEGER,source_id INTEGER,body TEXT,PRIMARY KEY(kind,item_id,source_id));
                CREATE TABLE IF NOT EXISTS source_checks(item_id INTEGER PRIMARY KEY,saved REAL,error INTEGER);
            ''')

    def save_sources(self,kind,rows,*,item_id=None,guard=lambda:None):
        with self.connect() as db:
            guard()
            if kind=='npc':db.execute('DELETE FROM item_sources WHERE kind=?',(kind,))
            else:db.execute('DELETE FROM item_sources WHERE kind=? AND item_id=?',(kind,item_id))
            db.executemany('INSERT OR REPLACE INTO item_sources VALUES(?,?,?,?)',[(kind,row['item_id'],row['id'],json.dumps(row)) for row in rows])
            if kind=='npc':self.put_meta(db,'npc_shops_checked',time.time())
            else:db.execute('INSERT OR REPLACE INTO source_checks VALUES(?,?,0)',(item_id,time.time()))
            guard()

    def source_check(self,item_id):
        with self.connect() as db:return db.execute('SELECT saved,error FROM source_checks WHERE item_id=?',(item_id,)).fetchone()

    def source_failed(self,item_id,guard=lambda:None):
        with self.connect() as db:
            guard();db.execute('INSERT OR REPLACE INTO source_checks VALUES(?,?,1)',(item_id,time.time()));guard()

    def sources_for(self,item_id):
        with self.connect() as db:rows=db.execute("SELECT body FROM item_sources WHERE item_id=? ORDER BY CASE kind WHEN 'npc' THEN 0 ELSE 1 END,source_id",(item_id,)).fetchall()
        result=[]
        for body, in rows:
            row=json.loads(body);item=self.entry('items',item_id);source=self.entry('npcs' if row['kind']=='npc' else 'items',row['id'])
            if item and source and item[0].name==row['item_name'] and source[0].name==row['name']:result.append(row)
        return result

    def shop_inventory(self,npc_id):
        with self.connect() as db:rows=db.execute("SELECT body FROM item_sources WHERE kind='npc' AND source_id=? ORDER BY item_id",(npc_id,)).fetchall()
        return [json.loads(body) for body, in rows]

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=3)
        try:
            with db:yield db
        finally:db.close()

    def metadata(self):
        with self.connect() as db:return {k:json.loads(v) for k,v in db.execute('SELECT key,value FROM metadata')}

    def value(self,key,default=None):
        with self.connect() as db:row=db.execute('SELECT value FROM metadata WHERE key=?',(key,)).fetchone()
        return json.loads(row[0]) if row else default

    @staticmethod
    def put_meta(db,key,value):db.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',(key,json.dumps(value)))

    def payload(self,name,digest):
        with self.connect() as db:
            row=db.execute('SELECT payload FROM files WHERE name=? AND hash=?',(name,digest)).fetchone()
            return bytes(row[0]) if row else None

    def has_payloads(self,meta):
        with self.connect() as db:saved=dict(db.execute('SELECT name,hash FROM files'))
        return all(saved.get(name)==meta['files'][name]['sha256'] for name in FILES)

    def checked(self,meta,at):
        with self.connect() as db:
            self.put_meta(db,'checked_at',at);self.put_meta(db,'manifest',meta)

    def replace(self,meta,payloads,at=None,guard=lambda:None):
        validate_meta(meta);at=time.time() if at is None else at
        documents={name:_rows(meta,name,payloads[name]) for name in FILES}
        records={}
        for name,rows in documents.items():
            kind={'items.json':'items','cash_shop.json':'items','monsters.json':'monsters','skills.json':'skills','maps.json':'maps','npcs.json':'npcs','quests.json':'quests'}[name]
            for source in rows:
                if not source['name'].strip():continue # Unnamed client placeholders are not searchable entities.
                row=dict(source);identity=row.get('id',row.get('item_id'));row['id']=identity
                if kind=='items':
                    from .reference_items import normalize
                    row=normalize(row)
                if name=='cash_shop.json':
                    if (kind,identity) in records:continue
                    row['cash']=True;row['category']='Cash';row['nx_price']=row.pop('price',None)
                category=row.get('category') or row.get('job_tier') or ('Boss' if row.get('is_boss') else 'Monster' if kind=='monsters' else 'Quest' if kind=='quests' else 'Town' if kind=='maps' and row.get('is_town') else 'Map' if kind=='maps' else 'NPC')
                level=row.get('level') if kind=='monsters' else row.get('level_min') if kind=='quests' else (row.get('stats') or {}).get('reqLevel') if kind=='items' else None
                level=level if type(level) is int else None
                icon=row.get('map_mark_url') if kind=='maps' else row.get('icon_url')
                entry=Entry(kind,identity,row['name'],category,level,row.get('class_name','Crafting' if category=='Crafting' else ''),image_url(icon))
                records[entry.key]=(entry,row)
        for key,(entry,row) in list(records.items()):
            if entry.kind=='quests':
                npc=records.get(('npcs',row.get('npc_id')))
                if npc:records[key]=(Entry(entry.kind,entry.id,entry.name,entry.category,entry.level,entry.job,npc[0].icon),row)
        guard()
        with self.connect() as db:
            db.execute('DELETE FROM entities');db.execute('DELETE FROM lookup')
            db.executemany('INSERT INTO entities VALUES(?,?,?,?,?,?,?,?)',[(e.kind,e.id,e.name,e.category,e.level,e.job,e.icon,json.dumps(row,separators=(',',':'))) for e,row in records.values()])
            db.executemany('INSERT INTO lookup VALUES(?,?,?)',[(e.kind,e.id,e.name+(' '+str(row.get('region',''))+' '+str(row.get('street_name','')) if e.kind in ('maps','quests') else '')) for e,row in records.values()])
            for name,raw in payloads.items():db.execute('INSERT OR REPLACE INTO files VALUES(?,?,?)',(name,meta['files'][name]['sha256'],raw))
            self.put_meta(db,'manifest',meta);self.put_meta(db,'checked_at',at)
            self.put_meta(db,'generation',meta.get('data_updated_at',''))
            self.put_meta(db,'counts',{kind:sum(e.kind==kind for e,row in records.values()) for kind in ('items','monsters','skills')})
            saved=db.execute("SELECT value FROM metadata WHERE key='drop_rows'").fetchone()
            if saved:self.put_meta(db,'drop_count',self._write_drops(db,json.loads(saved[0])))
            names={(e.kind,e.id):e.name for e,row in records.values()}
            for mid,iid,body in db.execute('SELECT monster_id,item_id,body FROM community_reports').fetchall():
                report=json.loads(body)
                if names.get(('monsters',mid))!=report.get('monster_name') or names.get(('items',iid))!=report.get('item_name'):
                    db.execute('DELETE FROM community_reports WHERE monster_id=? AND item_id=?',(mid,iid))
            guard()

    def search(self,kind,query='',category='',limit=80,*,released=True,scope=(),sort='name'):
        if kind not in (*RELEASED_KINDS,'skills'):return [],0
        terms=re.findall(r'[^\W_]+',str(query)[:120],re.UNICODE)[:12]
        params=[kind];where=['e.kind=?']
        if released and kind in RELEASED_KINDS:
            where.append('EXISTS(SELECT 1 FROM availability a WHERE a.kind=e.kind AND a.id=e.id AND a.name=e.name)')
            if kind in RELEASE_RULES:where.append(RELEASE_RULES[kind])
        if released and kind=='skills':where.append("e.category!='Crafting'")
        if terms:
            if len(terms)==1 and terms[0].isdigit():where.append('e.id=?');params.append(int(terms[0]))
            else:
                expression=' AND '.join('"'+term+'"*' for term in terms)
                where.append('e.id IN (SELECT id FROM lookup WHERE lookup MATCH ? AND kind=?)');params.extend((expression,kind))
        if category:
            where.append('e.job=?' if kind=='skills' else 'e.category=?');params.append(category)
        scoped(where,params,scope)
        condition=' AND '.join(where)
        with self.connect() as db:
            count=db.execute('SELECT COUNT(*) FROM entities e WHERE '+condition,params).fetchone()[0]
            order=SORTS.get(sort)
            if order is None:raise ValueError('Unsupported database sort')
            rows=db.execute('SELECT e.kind,e.id,e.name,e.category,e.level,'+CLASS_LABEL+',e.icon FROM entities e WHERE '+condition+' ORDER BY '+order+' LIMIT ?',(*params,max(1,min(10000,limit)))).fetchall()
        return [Entry(*row) for row in rows],count

    def groups(self,kind,field,scope=()):
        expression=GROUP_FIELDS.get(field)
        if expression is None:raise ValueError('Unsupported browse group')
        where=['e.kind=?'];params=[kind]
        if kind in RELEASED_KINDS:where.append('EXISTS(SELECT 1 FROM availability a WHERE a.kind=e.kind AND a.id=e.id AND a.name=e.name)')
        if kind in RELEASE_RULES:where.append(RELEASE_RULES[kind])
        if kind=='skills':where.append("e.category!='Crafting'")
        scoped(where,params,scope)
        where.append(expression+' IS NOT NULL');where.append(expression+"!=''")
        with self.connect() as db:
            rows=db.execute('SELECT '+expression+",COUNT(*),COALESCE(MIN(CASE WHEN COALESCE(e.icon,'')!='' THEN e.id END),MIN(e.id)) FROM entities e WHERE "+' AND '.join(where)+' GROUP BY '+expression,params).fetchall()
        return [{'value':value,'count':count,'entry':self.entry(kind,identity)[0]} for value,count,identity in rows]

    def entry(self,kind,identity):
        with self.connect() as db:
            row=db.execute('SELECT e.kind,e.id,e.name,e.category,e.level,'+CLASS_LABEL+',e.icon,e.body FROM entities e WHERE e.kind=? AND e.id=?',(kind,identity)).fetchone()
        if not row:return None
        body=json.loads(row[7])
        if kind=='items':
            from .reference_items import normalize
            body=normalize(body)
        return Entry(*row[:7]),body

    def available(self,kind,identity):
        if kind=='npcs':
            record=self.entry(kind,identity)
            return bool(record and any(row['name']==record[0].name for row in self.shop_inventory(identity)))
        if kind=='skills':
            record=self.entry(kind,identity);return bool(record and record[0].category!='Crafting')
        with self.connect() as db:
            condition=' AND '+RELEASE_RULES[kind] if kind in RELEASE_RULES else ''
            return db.execute('SELECT 1 FROM entities e JOIN availability a ON a.kind=e.kind AND a.id=e.id AND a.name=e.name WHERE e.kind=? AND e.id=?'+condition+' LIMIT 1',(kind,identity)).fetchone() is not None

    def confirm(self,rows,source,at=None,guard=lambda:None):
        """Retain positive, exact-ID/name evidence even after a sale/event ends."""
        if not isinstance(rows,list) or len(rows)>20000 or source not in ('nia-release','market','screen'):raise ValueError('Invalid availability evidence')
        at=time.time() if at is None else at;clean=[];guard()
        with self.connect() as db:
            names={(k,i):n for k,i,n in db.execute('SELECT kind,id,name FROM entities')}
            before=db.execute('SELECT COUNT(*) FROM availability').fetchone()[0]
            for row in rows:
                kind,identity,name=row.get('kind'),row.get('id'),row.get('name')
                if kind not in RELEASED_KINDS or type(identity) is not int or not isinstance(name,str) or names.get((kind,identity))!=name or excluded(kind,identity,name):continue
                detail=row.get('detail') or {}
                if not isinstance(detail,dict):continue
                clean.append((kind,identity,name,source,at,at,json.dumps(detail)))
            if rows and not clean:raise ValueError('Availability records do not match the Classic World catalog')
            db.executemany('''INSERT INTO availability VALUES(?,?,?,?,?,?,?) ON CONFLICT(kind,id,source) DO UPDATE SET
                name=excluded.name,last_seen=excluded.last_seen,detail=excluded.detail''',clean)
            guard();after=db.execute('SELECT COUNT(*) FROM availability').fetchone()[0]
        return after-before

    def evidence(self,kind,identity):
        with self.connect() as db:
            rows=db.execute('SELECT a.source,a.detail FROM availability a JOIN entities e ON a.kind=e.kind AND a.id=e.id AND a.name=e.name WHERE a.kind=? AND a.id=? ORDER BY a.first_seen',(kind,identity)).fetchall()
        return [{'source':source,**json.loads(detail)} for source,detail in rows]

    def released_counts(self):
        with self.connect() as db:
            return {kind:db.execute('SELECT COUNT(*) FROM entities e WHERE e.kind=? AND EXISTS(SELECT 1 FROM availability a WHERE a.kind=e.kind AND a.id=e.id AND a.name=e.name)',(kind,)).fetchone()[0] for kind in ('items','monsters')}

    def catalog(self,original=None):
        from .domain import Catalog,Item,key as name_key
        known={item.game_id:item for item in original.items} if original else {}
        with self.connect() as db:
            rows=db.execute("SELECT e.id,e.name,e.body FROM entities e WHERE e.kind='items' AND EXISTS(SELECT 1 FROM availability a WHERE a.kind=e.kind AND a.id=e.id AND a.name=e.name)").fetchall()
        items=[]
        for identity,name,body in rows:
            item=known.get(identity)
            if item and name_key(item.name)==name_key(name):items.append(item);continue
            row=json.loads(body);items.append(Item(identity,name,row.get('category')=='Equipment' or 1000000<=identity<2000000,
                identity//10000 in (207,233), (row.get('scroll') or {}).get('tier'),cash=bool(row.get('cash')),gender=row.get('gender')))
        return Catalog.from_items(items)

    def locations(self,identity):
        found=self.entry('monsters',identity)
        if not found:return []
        locations=[]
        for spawn in found[1].get('spawns',[]):
            if not isinstance(spawn,dict) or type(spawn.get('map_id')) is not int:continue
            target=self.entry('maps',spawn['map_id'])
            if target and self.available('maps',spawn['map_id']):locations.append({**target[1],'count':spawn.get('count')})
        return sorted(locations,key=lambda r:(-(r.get('count') or 0),r['name']))

    def map_monsters(self,identity):
        record=self.entry('maps',identity)
        if not record:return []
        counts={}
        for point in record[1].get('mobs',[]):
            mid=point.get('mob_id')
            if type(mid) is int:counts[mid]=counts.get(mid,0)+1
        result=[]
        for mid,count in counts.items():
            target=self.entry('monsters',mid)
            if target and self.available('monsters',mid):result.append((target[0],count))
        return sorted(result,key=lambda pair:(pair[0].level or 0,pair[0].name))

    def quests_for(self,item_id):
        with self.connect() as db:
            rows=db.execute("""SELECT e.id FROM entities e WHERE e.kind='quests'
                AND EXISTS(SELECT 1 FROM availability a WHERE a.kind=e.kind AND a.id=e.id AND a.name=e.name)
                AND EXISTS(SELECT 1 FROM json_each(e.body,'$.rewards') r
                    WHERE json_extract(r.value,'$.type')='item' AND json_extract(r.value,'$.id')=?)
                AND COALESCE(json_extract(e.body,'$.region'),'')!='Forgotten Hollow'
                ORDER BY e.level,e.name COLLATE NOCASE""",(item_id,)).fetchall()
        return [self.entry('quests',identity) for identity, in rows]

    def save_drops(self,rows,at=None,guard=lambda:None):
        if not isinstance(rows,list) or len(rows)>10000:raise ValueError('Too many drop records')
        guard()
        with self.connect() as db:
            count=self._write_drops(db,rows)
            if rows and not count:raise ValueError('Drop records do not match the Classic World database')
            self.put_meta(db,'drop_rows',rows);self.put_meta(db,'drops_checked_at',time.time() if at is None else at)
            self.put_meta(db,'drop_count',count);guard()
        return count

    def _write_drops(self,db,rows):
        names={(kind,identity):name for kind,identity,name in db.execute('SELECT kind,id,name FROM entities')}
        clean={}
        text=lambda s:' '.join(html.unescape(str(s or '')).casefold().replace('’',"'").split())
        def integer(value):
            if type(value) is not int and not(isinstance(value,str) and re.fullmatch(r'\d{1,10}',value)):raise ValueError('Invalid report ID/count')
            value=int(value)
            if not 0<=value<=2147483647:raise ValueError('Invalid report ID/count')
            return value
        for row in rows:
            if not isinstance(row,dict):continue
            try:
                mid=integer(row['monster_id']);item_id=integer(row['item_id']) if row.get('item_id') is not None else None
                category=str(row.get('category') or '')
                if category not in ('meso','nothing') and item_id is None:continue
                if text(names.get(('monsters',mid)))!=text(row.get('monster_name')) or ('monsters',mid) not in names:continue
                if item_id is not None and (('items',item_id) not in names or text(names[('items',item_id)])!=text(row.get('item_name'))):continue
                version=str(row.get('version') or '')
                if version and not re.fullmatch(r'\d+\.\d+(?:\.\d+)?',version):continue
                result={k:html.unescape(str(row[k])) if row.get(k) is not None else None for k in ('page','date','version','item_page')}
                result.update(monster_id=mid,item_id=item_id,category=category,quest=row.get('quest') in ('1',1,True) or category=='quest')
                for key in ('rate','low','high'):
                    value=float(row[key]) if row.get(key) not in (None,'') else None
                    if value is not None and (not math.isfinite(value) or not 0<=value<=100):raise ValueError()
                    result[key]=value
                for key in ('minimum','maximum','kills','observed'):
                    value=integer(row[key]) if row.get(key) not in (None,'') else None
                    result[key]=value
                if result['kills'] is not None and result['observed'] is not None and result['observed']>result['kills']:continue
                if result['minimum'] is not None and result['maximum'] is not None and result['minimum']>result['maximum']:continue
                key=(mid,item_id,category);old=clean.get(key)
                if old is None or (result['date'] or '')>(old['date'] or ''):clean[key]=result
            except (ValueError,TypeError,KeyError,OverflowError):continue
        db.execute('DELETE FROM drops')
        db.executemany('INSERT INTO drops VALUES(?,?,?,?)',[(r['monster_id'],r['item_id'],r['category'],json.dumps(r)) for r in clean.values()])
        return len(clean)

    def drops_for(self,kind,identity):
        field='monster_id' if kind=='monsters' else 'item_id'
        with self.connect() as db:
            rows=[{**json.loads(r[0]),'source':'wiki'} for r in db.execute(f'SELECT body FROM drops WHERE {field}=? ORDER BY category,item_id,monster_id',(identity,))]
            names={(kind,identity):name for kind,identity,name in db.execute('SELECT kind,id,name FROM entities')}
            combined={(r['monster_id'],r['item_id'],r['category'] if r['item_id'] is None else ''):r for r in rows}
            for record, in db.execute(f'SELECT body FROM community_reports WHERE {field}=?',(identity,)):
                r=json.loads(record)
                if names.get(('monsters',r['monster_id']))!=r['monster_name'] or names.get(('items',r['item_id']))!=r['item_name']:continue
                key=(r['monster_id'],r['item_id'],'')
                if key in combined:combined[key]['also_reported']=True
                else:combined[key]=r
        return [r for r in combined.values() if self.available('monsters',r['monster_id']) and (r['item_id'] is None or self.available('items',r['item_id']))]

    def community_check(self,kind,identity):
        with self.connect() as db:
            row=db.execute('SELECT saved,detail FROM community_checks WHERE kind=? AND id=?',(kind,identity)).fetchone()
        return (row[0],json.loads(row[1])) if row else None

    def save_community(self,kind,identity,rows,detail,guard=lambda:None):
        if kind not in ('items','monsters') or len(rows)>1000:raise ValueError('Invalid report collection')
        field='monster_id' if kind=='monsters' else 'item_id';guard()
        with self.connect() as db:
            names={(kind,identity):name for kind,identity,name in db.execute('SELECT kind,id,name FROM entities')}
            for row in rows:
                if row.get('source')!='meow' or row.get('rate') is not None:raise ValueError('Community votes are not sampled drop rates')
                if row.get(field)!=identity or type(row.get('monster_id')) is not int or type(row.get('item_id')) is not int:raise ValueError('Wrong report identity')
                if names.get(('monsters',row['monster_id']))!=row.get('monster_name') or names.get(('items',row['item_id']))!=row.get('item_name'):raise ValueError('Unverified report identity')
            if not detail.get('error'):
                db.execute(f'DELETE FROM community_reports WHERE {field}=?',(identity,))
                db.executemany('INSERT OR REPLACE INTO community_reports VALUES(?,?,?)',[(r['monster_id'],r['item_id'],json.dumps(r)) for r in rows])
            db.execute('INSERT OR REPLACE INTO community_checks VALUES(?,?,?,?)',(kind,identity,time.time(),json.dumps(detail)))
            db.execute('DELETE FROM community_checks WHERE rowid IN (SELECT rowid FROM community_checks ORDER BY saved DESC LIMIT -1 OFFSET 1024)')
            db.execute('DELETE FROM community_reports WHERE rowid IN (SELECT rowid FROM community_reports ORDER BY rowid DESC LIMIT -1 OFFSET 10000)')
            guard()

    def report_count(self):
        with self.connect() as db:
            return db.execute('''SELECT COUNT(*) FROM (
                SELECT monster_id,item_id,CASE WHEN item_id IS NULL THEN category ELSE '' END FROM drops
                UNION SELECT monster_id,item_id,'' FROM community_reports)''').fetchone()[0]
