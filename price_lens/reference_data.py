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
FILES=('items.json','cash_shop.json','monsters.json','skills.json','maps.json')
DAY=86400


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
        for key in ('spawns','levels','required_skills'):
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
            ''')

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=3)
        try:
            with db:yield db
        finally:db.close()

    def metadata(self):
        with self.connect() as db:return {k:json.loads(v) for k,v in db.execute('SELECT key,value FROM metadata')}

    @staticmethod
    def put_meta(db,key,value):db.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',(key,json.dumps(value)))

    def payload(self,name,digest):
        with self.connect() as db:
            row=db.execute('SELECT payload FROM files WHERE name=? AND hash=?',(name,digest)).fetchone()
            return bytes(row[0]) if row else None

    def checked(self,meta,at):
        with self.connect() as db:
            self.put_meta(db,'checked_at',at);self.put_meta(db,'manifest',meta)

    def replace(self,meta,payloads,at=None,guard=lambda:None):
        validate_meta(meta);at=time.time() if at is None else at
        documents={name:_rows(meta,name,payloads[name]) for name in FILES}
        records={}
        for name,rows in documents.items():
            kind={'items.json':'items','cash_shop.json':'items','monsters.json':'monsters','skills.json':'skills','maps.json':'maps'}[name]
            for source in rows:
                if not source['name'].strip():continue # Unnamed client placeholders are not searchable entities.
                row=dict(source);identity=row.get('id',row.get('item_id'));row['id']=identity
                if name=='cash_shop.json':
                    if (kind,identity) in records:continue
                    row['cash']=True;row['category']='Cash';row['nx_price']=row.pop('price',None)
                category=row.get('category') or row.get('job_tier') or ('Boss' if row.get('is_boss') else 'Monster' if kind=='monsters' else 'Map')
                level=row.get('level') if kind=='monsters' else (row.get('stats') or {}).get('reqLevel') if kind=='items' else None
                level=level if type(level) is int else None
                entry=Entry(kind,identity,row['name'],category,level,row.get('class_name','Crafting' if category=='Crafting' else ''),image_url(row.get('icon_url')))
                records[entry.key]=(entry,row)
        guard()
        with self.connect() as db:
            db.execute('DELETE FROM entities');db.execute('DELETE FROM lookup')
            db.executemany('INSERT INTO entities VALUES(?,?,?,?,?,?,?,?)',[(e.kind,e.id,e.name,e.category,e.level,e.job,e.icon,json.dumps(row,separators=(',',':'))) for e,row in records.values()])
            db.executemany('INSERT INTO lookup VALUES(?,?,?)',[(e.kind,e.id,e.name) for e,row in records.values()])
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

    def search(self,kind,query='',category='',limit=80):
        if kind not in ('items','monsters','skills'):return [],0
        terms=re.findall(r'[^\W_]+',str(query)[:120],re.UNICODE)[:12]
        params=[kind];where=['e.kind=?']
        if terms:
            if len(terms)==1 and terms[0].isdigit():where.append('e.id=?');params.append(int(terms[0]))
            else:
                expression=' AND '.join('"'+term+'"*' for term in terms)
                where.append('e.id IN (SELECT id FROM lookup WHERE lookup MATCH ? AND kind=?)');params.extend((expression,kind))
        if category:
            where.append('e.job=?' if kind=='skills' else 'e.category=?');params.append(category)
        condition=' AND '.join(where)
        with self.connect() as db:
            count=db.execute('SELECT COUNT(*) FROM entities e WHERE '+condition,params).fetchone()[0]
            rows=db.execute('SELECT kind,id,name,category,level,job,icon FROM entities e WHERE '+condition+' ORDER BY e.name COLLATE NOCASE,e.id LIMIT ?',(*params,max(1,min(10000,limit)))).fetchall()
        return [Entry(*row) for row in rows],count

    def categories(self,kind):
        field='job' if kind=='skills' else 'category'
        with self.connect() as db:return [r[0] for r in db.execute(f'SELECT DISTINCT {field} FROM entities WHERE kind=? AND {field}!="" ORDER BY {field}',(kind,))]

    def entry(self,kind,identity):
        with self.connect() as db:
            row=db.execute('SELECT kind,id,name,category,level,job,icon,body FROM entities WHERE kind=? AND id=?',(kind,identity)).fetchone()
        return (Entry(*row[:7]),json.loads(row[7])) if row else None

    def locations(self,identity):
        found=self.entry('monsters',identity)
        if not found:return []
        locations=[]
        for spawn in found[1].get('spawns',[]):
            if not isinstance(spawn,dict) or type(spawn.get('map_id')) is not int:continue
            target=self.entry('maps',spawn['map_id'])
            if target:locations.append({**target[1],'count':spawn.get('count')})
        return sorted(locations,key=lambda r:(-(r.get('count') or 0),r['name']))

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
        return list(combined.values())

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
