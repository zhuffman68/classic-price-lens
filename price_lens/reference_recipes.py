"""Exact, reachable scroll-crafting outcomes; never unlock a whole scroll tier."""
from datetime import datetime
import hashlib
import json
import math
import time

from .reference_data import API,validate_meta

# OSMS documents the current client cap explicitly: skills still export max 10.
# A later date or a higher raw max_level must not automatically unlock 9/10.
CRAFTING_CAP=8
CAP_SOURCE=API+'README.md'
CATALYST_ID=4130003
CATALYST_NAME='Scroll Crafting Catalyst'
CATALYST_TEXT='When used while crafting scrolls, there is a chance to produce an Intermediate, Greater, or Chaos scroll of the same category.'
TIERS=('Lesser','Intermediate','Greater','Chaos')
RATES=(100,60,10,10)


def verified_recipes(meta,raw,*,now=None):
    """Check the optional public payload just as strictly as the core files."""
    validate_meta(meta);info=meta.get('files',{}).get('recipes.json')
    now=time.time() if now is None else now
    stamp=datetime.fromisoformat(meta['data_updated_at'].replace('Z','+00:00')).timestamp()
    if stamp>now+300:raise ValueError('Future recipe generation')
    if (not isinstance(info,dict) or type(info.get('bytes')) is not int or not 1<=info['bytes']<=8*1024*1024
            or type(info.get('records')) is not int or not 1<=info['records']<=20000
            or not isinstance(raw,bytes) or len(raw)!=info['bytes'] or hashlib.sha256(raw).hexdigest()!=info.get('sha256')):
        raise ValueError('Recipe download failed verification')
    rows=json.loads(raw)
    if not isinstance(rows,list) or len(rows)!=info['records']:raise ValueError('Recipe count changed')
    used=set()
    for row in rows:
        if not isinstance(row,dict):raise ValueError('Invalid recipe')
        identity=row.get('id')
        if type(identity) is not int or identity<=0 or identity in used:raise ValueError('Invalid recipe ID')
        used.add(identity)
        for field,minimum,maximum in (('output_item_id',1,2147483647),('discipline_skill_id',1,2147483647),
                ('output_count',1,1000000),('req_skill_level',1,200),('craft_exp',0,2147483647),('meso_cost',0,2147483647)):
            value=row.get(field)
            if type(value) is not int or not minimum<=value<=maximum:raise ValueError('Invalid recipe '+field)
        if not isinstance(row.get('discipline'),str) or not row['discipline']:raise ValueError('Missing crafting discipline')
        ingredients=row.get('ingredients')
        if not isinstance(ingredients,list) or not 1<=len(ingredients)<=200:raise ValueError('Invalid recipe ingredients')
        seen=set()
        for ingredient in ingredients:
            if not isinstance(ingredient,dict):raise ValueError('Invalid recipe ingredient')
            item=ingredient.get('item_id');count=ingredient.get('count')
            if (type(item) is not int or not 1<=item<=2147483647 or item in seen
                    or type(count) is not int or not 1<=count<=1000000):raise ValueError('Invalid recipe ingredient')
            seen.add(item)
    return rows


def scroll_family(row):
    """Validate canonical family/tier/ID agreement before deriving any outcome."""
    identity=row.get('id');scroll=row.get('scroll');name=row.get('name')
    if (type(identity) is not int or identity//10000!=204 or not isinstance(scroll,dict)
            or not isinstance(name,str) or ': ' not in name):return None
    family,tier=name.rsplit(': ',1)
    if tier not in TIERS or scroll.get('tier')!=tier:return None
    index=TIERS.index(tier)
    if identity%4!=index or type(scroll.get('success_rate')) is not int or scroll['success_rate']!=RATES[index]:return None
    if tier=='Chaos' and (type(scroll.get('destroy_rate')) is not int or scroll['destroy_rate']!=50):return None
    stats=scroll.get('stats')
    if not isinstance(stats,dict) or not stats:return None
    if any(type(n) not in (int,float) or not math.isfinite(n) or n<=0 for n in stats.values()):return None
    return family,index,scroll.get('slot'),scroll.get('stat'),frozenset(stats)


def recipe_proofs(store,meta,raw,*,now=None,guard=lambda:None):
    """Sources must already prove the base, every ingredient and the catalyst."""
    rows=verified_recipes(meta,raw,now=now);guard()
    if store.metadata().get('manifest')!=meta:raise ValueError('Stale recipe generation')
    catalyst=store.entry('items',CATALYST_ID)
    if (not catalyst or catalyst[0].name!=CATALYST_NAME or catalyst[1].get('description')!=CATALYST_TEXT
            or not store.available('items',CATALYST_ID)):return []
    skill=store.entry('skills',92050000)
    if not skill or skill[0].name!='Arcforge' or skill[1].get('job_tier')!='Crafting':return []
    proofs={}
    for recipe in rows:
        guard()
        if (recipe['discipline']!='Arcforge' or recipe['discipline_skill_id']!=92050000
                or recipe['req_skill_level']>CRAFTING_CAP):continue
        identity=recipe['output_item_id'];base=store.entry('items',identity)
        if not base or not store.available('items',identity):continue
        family=scroll_family(base[1])
        if not family or family[1]!=0:continue
        if not all(store.available('items',part['item_id']) for part in recipe['ingredients']):continue
        for offset,tier in enumerate(TIERS[1:],1):
            target=store.entry('items',identity+offset)
            if not target or store.available('items',identity+offset):continue
            expected=(family[0],offset,*family[2:])
            candidate=scroll_family(target[1])
            if not candidate or candidate[:4]!=expected[:4] or target[0].name!=family[0]+': '+tier:continue
            # Higher DEF tiers legitimately add the second defense as well:
            # e.g. Cape Weapon Def. Lesser has PDD only, Chaos has PDD and MDD.
            if candidate[4]!=expected[4] and not (expected[4]<candidate[4]<={'incPDD','incMDD'}):continue
            proofs[identity+offset]=dict(kind='items',id=identity+offset,name=target[0].name,detail={
                'label':'Scroll crafting with catalyst','url':API+'recipes.json','basis':'Verified recipe and catalyst mechanics',
                'recipe_id':recipe['id'],'base_item_id':identity,'catalyst_id':CATALYST_ID,
                'crafting_level':recipe['req_skill_level'],'crafting_cap':CRAFTING_CAP,'cap_source':CAP_SOURCE,
                'client_build':meta['client_build'],'recipe_sha256':meta['files']['recipes.json']['sha256']})
    guard();return list(proofs.values())


class RecipeAvailability:
    def __init__(self,store,fetch_bytes):self.store=store;self.fetch_bytes=fetch_bytes

    def refresh(self,token):
        token.check();meta=self.store.metadata().get('manifest')
        if not meta or 'recipes.json' not in meta.get('files',{}):return False
        info=meta['files']['recipes.json'];digest=info.get('sha256')
        raw=self.store.payload('recipes.json',digest)
        if raw is None or len(raw)!=info.get('bytes') or hashlib.sha256(raw).hexdigest()!=digest:raw=self.fetch_bytes(API+'recipes.json')
        token.check();proofs=recipe_proofs(self.store,meta,raw,guard=token.check)
        # Cache verified bytes and publish proofs in one guarded transaction.
        return bool(self.store.confirm(proofs,'recipe',guard=token.check,manifest=meta,payload=raw))
