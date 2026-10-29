"""Positive release/circulation evidence, never inferred from client presence."""
from datetime import datetime,timezone
import json
import time
from urllib.parse import urlencode
from .domain import key as name_key,WORLD
from .reference_community import BASE,MonsterIndex
from .reference_data import DAY,excluded
from .reference_indexes import ReleaseIndex,release_name


class AvailabilityLoader:
    def __init__(self,store,fetch_json,fetch_bytes):
        self.store=store;self.fetch_json=fetch_json;self.fetch_bytes=fetch_bytes

    def refresh(self,token,force=False):
        state=self.store.metadata()
        if not force and state.get('availability_schema')==2 and 0<=time.time()-state.get('availability_checked_at',0)<DAY:return
        raw=self.fetch_bytes(BASE+'monsters');token.check()
        if len(raw)>3*1024*1024:raise ValueError('Monster index too large')
        index=MonsterIndex();index.feed(raw.decode('utf-8'))
        if len(index.rows)<10:raise ValueError('Released monster index unavailable')
        proofs=[]
        for text,row in index.rows.items():
            identity=int(text);record=self.store.entry('monsters',identity)
            if not record:continue
            entry,body=record
            if (entry.name==row['name'] and body.get('level')==row['level'] and body.get('hp')==row['hp']
                    and not excluded('monsters',identity,entry.name)):
                proofs.append(dict(kind='monsters',id=identity,name=entry.name,detail={'label':'Released Classic World monster','url':BASE+'monsters/'+text}))
        if not proofs:raise ValueError('Released monsters did not match the catalog')
        self.store.confirm(proofs,'nia-release',guard=token.check)
        # `avail=launch` is Nia's sourced release filter, not its raw catalog.
        # Cosmetics also use its curated never-sold exclusion; explicit old-beta
        # and future-date flags are rejected below. Expired releases are retained.
        for kind in ('Equip','Use','Etc','Setup','Cash','Cash Equip'):
            proofs=[]
            for page in range(1,61):
                params={'type':kind,'limit':100,'page':page,'ossyria':0,'cot1':0,'locale':'en'}
                if kind=='Cash Equip':params['unsold']='hide'
                else:params['avail']='launch'
                doc=self.fetch_json(BASE+'api/items?'+urlencode(params));token.check()
                rows=doc.get('items') if isinstance(doc,dict) else None
                if not isinstance(rows,list) or len(rows)>100 or doc.get('page')!=page or type(doc.get('hasMore')) is not bool:raise ValueError('Availability index format changed')
                for row in rows:
                    proof=self.item(row,kind)
                    if proof:proofs.append(proof)
                if not doc['hasMore']:break
            else:raise ValueError('Availability page limit reached')
            if rows and not proofs:raise ValueError('Released items did not match the catalog')
            self.store.confirm(proofs,'nia-release',guard=token.check)
        self.release_places(token)
        with self.store.connect() as db:
            self.store.put_meta(db,'availability_checked_at',time.time());self.store.put_meta(db,'availability_schema',2);token.check()

    def release_places(self,token):
        for kind,path in (('maps','maps/all'),('quests','quest-tracker/all')):
            raw=self.fetch_bytes(BASE+path);token.check()
            if len(raw)>4*1024*1024:raise ValueError('Release index too large')
            parser=ReleaseIndex(kind);parser.feed(raw.decode('utf-8'))
            if not parser.rows:raise ValueError('Release index unavailable')
            proofs=[]
            for identity,label in parser.rows.items():
                record=self.store.entry(kind,identity)
                if not record:continue
                entry,row=record
                if not release_name(kind,row,label) or excluded(kind,identity,entry.name):continue
                if row.get('region') in ('Dev','Forgotten Hollow') or any(point.get('mob_id') in (*range(54,64),700003) for point in row.get('mobs',[])):continue
                proofs.append(dict(kind=kind,id=identity,name=entry.name,detail={'label':'Released Classic World '+('map' if kind=='maps' else 'quest'),
                    'url':BASE+('maps/' if kind=='maps' else 'quest-tracker/')+str(identity)}))
            if proofs:self.store.confirm(proofs,'nia-release',guard=token.check)

    def item(self,row,kind):
        if not isinstance(row,dict) or row.get('type')!=kind:return None
        identity=row.get('iconKey')
        if not isinstance(identity,str) or not identity.isdecimal() or len(identity)>10:return None
        identity=int(identity);record=self.store.entry('items',identity)
        if not record or record[0].name!=row.get('name') or excluded('items',identity,record[0].name):return None
        try:stats=json.loads(row.get('stats') or '{}') if isinstance(row.get('stats'),str) else row.get('stats') or {}
        except (ValueError,TypeError):return None
        if not isinstance(stats,dict) or stats.get('cashShopLastSeenIn'):return None
        date=stats.get('availableDate')
        if date:
            try:
                start=datetime.fromisoformat(str(date).replace('Z','+00:00'))
                if start.tzinfo is None:start=start.replace(tzinfo=timezone.utc)
                if start.timestamp()>time.time():return None
            except ValueError:return None
        sources=row.get('sources') or []
        if not isinstance(sources,list):return None
        allowed={'npc':'NPC shop','mob':'Monster drop','craft':'Crafting','brk':'Breakable','quest':'Quest','box':'Reward box'}
        labels=[allowed[value] for value in sources if value in allowed]
        label=' / '.join(labels) or ('Released cosmetic' if kind=='Cash Equip' else 'Released Cash Shop item' if kind=='Cash' else 'Released item')
        provider_id=row.get('id')
        if type(provider_id) is not int or provider_id<=0:return None
        return dict(kind='items',id=identity,name=record[0].name,detail={'label':label,'url':BASE+'item-db/'+str(provider_id)})


def market_proofs(store,catalog,snapshot):
    """A catalog row alone proves nothing; a dated observed sale does."""
    if not snapshot or not getattr(snapshot,'meta',None) or not catalog:return []
    result=[];items={item.game_id:item for item in catalog.items}
    for identity,row in snapshot.rows.items():
        item=items.get(identity);quote=row.get('quote') or {};record=store.entry('items',identity)
        if not item or not record or record[0].name!=row.get('name') or name_key(item.name)!=name_key(record[0].name):continue
        sold=quote.get('observed_at');reports=quote.get('sample_count')
        if quote.get('game_id')!=identity or quote.get('world')!=WORLD or quote.get('basis')!='observed shop sales':continue
        founders=datetime(2026,10,6,18,tzinfo=timezone.utc).timestamp()
        if type(reports) is not int or reports<=0 or type(sold) not in (int,float) or not founders<=sold<=time.time()+300:continue
        result.append(dict(kind='items',id=identity,name=record[0].name,detail={'label':'Observed in the Classic World market','url':'https://meso.watch/','observed_at':sold}))
    return result
