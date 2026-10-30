"""Released scrolls need obtaining evidence, not merely a known catalog name."""
from concurrent.futures import CancelledError
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import hashlib
import json
import tempfile
import time
import unittest

from price_lens.domain import Catalog,Item
from price_lens.http_json import RequestToken
from price_lens.reference_availability import screen_proof,user_confirmed_proofs
from price_lens.reference_data import ReferenceStore
from price_lens.reference_recipes import CATALYST_TEXT,RecipeAvailability,recipe_proofs,verified_recipes
from price_lens.reference_service import ReferenceService
from test_reference import documents,generation


# Current reachable recipe families; this fixture deliberately leaves other
# unproven families and the crafting-9/10 recipes outside the release ledger.
BASES=((2040000,'Hat Accuracy',2),(2040004,'Hat HP',2),(2040008,'Hat MP',2),
    (2040404,'Topwear HP',3),(2040408,'Topwear MP',3),(2040604,'Bottomwear HP',4),
    (2040608,'Bottomwear MP',4),(2040900,'Shield DEF',5),(2040904,'Shield Accuracy',5),
    (2040500,'Overall Armor DEF',5),(2040700,'Shoes Jump',6),(2040704,'Shoes Speed',6),
    (2041000,'Cape Weapon Def.',7),(2041004,'Cape Magic Def.',7),(2040300,'Earring STR',8),
    (2040304,'Earring DEX',8),(2040308,'Earring INT',8),(2040312,'Earring LUK',8))
EXTRA=((2040800,'Gloves Attack',0),(2040804,'Gloves Magic Attack',0),(2040708,'Shoes Evasion',0),
    (2040808,'Gloves Accuracy',9),(2040812,'Gloves Crit. Rate',9),(2041012,'Cape DEX',10),
    (2043000,'One-Handed Sword Attack',0))
EXPECTED={2040003,2040007,2040011,2040407,2040411,2040607,2040609,2040611,
          2040903,2040503,2040703,2041003,2041007,2040307}


def fixture():
    docs=documents();recipes=[]
    for base,family,level in (*BASES,*EXTRA):
        for offset,tier in enumerate(('Lesser','Intermediate','Greater','Chaos')):
            scroll=dict(slot=family,stat='Fixture stat',tier=tier,success_rate=(100,60,10,10)[offset],stats={'incACC':offset+1})
            if family in ('Shield DEF','Overall Armor DEF','Cape Weapon Def.','Cape Magic Def.'):
                scroll['stats']={'incMDD' if family=='Cape Magic Def.' else 'incPDD':offset+2}
                if offset:scroll['stats']={'incPDD':offset+2,'incMDD':offset+1}
            if tier=='Chaos':scroll['destroy_rate']=50
            docs['items.json'].append(dict(id=base+offset,name=family+' Scroll: '+tier,category='Consumable',sub_category='Scroll',scroll=scroll))
        if level:recipes.append(dict(id=len(recipes)+1,discipline='Arcforge',discipline_skill_id=92050000,
            output_item_id=base,output_count=1,req_skill_level=level,craft_exp=level*10,meso_cost=10000,
            ingredients=[dict(item_id=4003009,count=1),dict(item_id=4000063,count=10),dict(item_id=4020100,count=3)]))
    for identity,name in ((4003009,'Processed Parchment'),(4000063,'Fragment of Magic'),(4020100,'Garnet')):
        docs['items.json'].append(dict(id=identity,name=name,category='Etc'))
    docs['items.json'].append(dict(id=4130003,name='Scroll Crafting Catalyst',category='Etc',description=CATALYST_TEXT))
    docs['skills.json'].append(dict(id=92050000,name='Arcforge',job_id=9205,job_tier='Crafting',max_level=10))
    meta,payloads=generation(docs);raw=json.dumps(recipes,separators=(',',':')).encode()
    meta['files']['recipes.json']=dict(sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),records=len(recipes))
    return docs,meta,payloads,raw


class ScrollEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.store=ReferenceStore(Path(self.folder.name)/'reference.sqlite')
        self.docs,self.meta,self.payloads,self.raw=fixture();self.store.replace(self.meta,self.payloads)
        allowed={4003009,4000063,4020100,4130003}
        for base,_,_ in BASES:allowed.update((base,base+1,base+2))
        allowed.remove(2040609)
        allowed.update((2040303,2040311,2040315,2040707,2040907))
        self.store.confirm([dict(kind='items',id=i,name=self.store.entry('items',i)[0].name) for i in allowed],'nia-release')
        self.catalog=Catalog.from_items([Item(row['id'],row['name'],tier=(row.get('scroll') or {}).get('tier')) for row in self.docs['items.json']])

    def service(self):
        return SimpleNamespace(store=self.store,closed=False,screen_known=set(),screen_notification_pending=False,
            updated=SimpleNamespace(emit=Mock()),_notify_screen=Mock())

    def sighting(self,**changes):
        return dict(game_id=2040803,visible_name='Gloves Attack Scroll: Chaos',tier='Chaos',surface='item-description',
            captured_at=time.time(),game_verified=True,panel_verified=True,**changes)

    def test_user_report_has_honest_provenance_and_survives_reference_replacement(self):
        proofs=user_confirmed_proofs(self.store);self.assertEqual([r['id'] for r in proofs],[2040803])
        self.store.confirm(proofs,'user-confirmed');self.assertEqual(user_confirmed_proofs(self.store),[])
        evidence=self.store.evidence('items',2040803)[0]
        self.assertEqual(evidence['source'],'user-confirmed');self.assertEqual(evidence['context'],'Super Megaphone')
        self.assertNotIn('observed_at',evidence);self.assertNotIn('sale',evidence['basis'])
        self.store.replace(self.meta,self.payloads)
        self.assertTrue(self.store.available('items',2040803));self.assertEqual(self.store.search('items','2040803')[1],1)

    def test_service_migrates_the_confirmed_item_offline_without_claiming_a_sale(self):
        fetch_json=Mock(side_effect=AssertionError('Migration fetched a price'))
        fetch_bytes=Mock(side_effect=AssertionError('Migration fetched a source'))
        service=ReferenceService(self.store.path,fetch_json=fetch_json,fetch_bytes=fetch_bytes);self.addCleanup(service.close)
        self.assertTrue(service.store.available('items',2040803))
        self.assertEqual(service.store.evidence('items',2040803)[0]['source'],'user-confirmed')
        fetch_json.assert_not_called();fetch_bytes.assert_not_called()

    def test_background_refresh_applies_recipe_proofs_after_core_verification(self):
        service=SimpleNamespace(store=self.store,fetch_json=lambda url:self.meta if url.endswith('meta.json') else {'cargoquery':[]},
            fetch_bytes=Mock(return_value=self.raw),sources=SimpleNamespace(refresh_shops=Mock()))
        with patch('price_lens.reference_service.AvailabilityLoader.refresh'):
            self.assertEqual(ReferenceService.refresh(service,RequestToken(),False),{})
        self.assertTrue(self.store.available('items',2040803))
        for identity in EXPECTED:self.assertTrue(self.store.available('items',identity))
        service.fetch_bytes.assert_called_once()

    def test_rename_or_wrong_tier_does_not_inherit_the_user_report(self):
        for field,value in (('name','Other scroll'),('scroll',{'tier':'Greater'})):
            docs=deepcopy(self.docs);next(row for row in docs['items.json'] if row['id']==2040803)[field]=value
            self.store.replace(*generation(docs));self.assertEqual(user_confirmed_proofs(self.store),[])
            self.assertFalse(self.store.available('items',2040803))

    def test_only_the_fourteen_reachable_catalyst_outcomes_are_added(self):
        proofs=recipe_proofs(self.store,self.meta,self.raw)
        self.assertEqual({r['id'] for r in proofs},EXPECTED)
        self.store.confirm(proofs,'recipe',manifest=self.meta,payload=self.raw)
        for identity in EXPECTED:self.assertTrue(self.store.available('items',identity))
        for identity in (2040803,2040807,2040808,2040812,2041012,2040710,2043003):
            self.assertFalse(self.store.available('items',identity))
        self.assertEqual(recipe_proofs(self.store,self.meta,self.raw),[])
        self.assertEqual(self.store.payload('recipes.json',self.meta['files']['recipes.json']['sha256']),self.raw)

    def test_unreleased_ingredient_or_catalyst_does_not_establish_an_outcome(self):
        for identity in (4020100,4130003):
            with self.store.connect() as db:db.execute("DELETE FROM availability WHERE kind='items' AND id=?",(identity,))
            self.assertEqual(recipe_proofs(self.store,self.meta,self.raw),[])
            self.store.confirm([dict(kind='items',id=identity,name=self.store.entry('items',identity)[0].name)],'nia-release')

    def test_wrong_name_id_stat_tier_or_catalyst_text_is_not_guessed(self):
        mutations=(('name','Hat HP Scroll: Chaos'),('scroll',{'tier':'Greater','success_rate':10,'stats':{'incACC':4}}),
            ('scroll',{'tier':'Chaos','success_rate':10,'destroy_rate':50,'slot':'Another slot','stat':'Fixture stat','stats':{'incACC':4}}),
            ('scroll',{'tier':'Chaos','success_rate':10,'destroy_rate':50,'slot':'Hat Accuracy','stat':'Fixture stat','stats':{'incMMP':4}}))
        for field,value in mutations:
            docs=deepcopy(self.docs);next(x for x in docs['items.json'] if x['id']==2040003)[field]=value
            meta,payloads=generation(docs);meta['files']['recipes.json']=self.meta['files']['recipes.json']
            self.store.replace(meta,payloads)
            self.assertNotIn(2040003,{p['id'] for p in recipe_proofs(self.store,meta,self.raw)})
        docs=deepcopy(self.docs);next(x for x in docs['items.json'] if x['id']==4130003)['description']='Unknown mechanic'
        meta,payloads=generation(docs);meta['files']['recipes.json']=self.meta['files']['recipes.json'];self.store.replace(meta,payloads)
        self.assertEqual(recipe_proofs(self.store,meta,self.raw),[])

    def test_hash_count_malformed_id_and_future_generation_are_rejected(self):
        with self.assertRaises(ValueError):verified_recipes(self.meta,self.raw+b' ')
        rows=json.loads(self.raw)
        for field,value in (('id',True),('output_item_id',2040000.0),('req_skill_level',True),('ingredients',[{'item_id':4020100,'count':0}])):
            broken=deepcopy(rows);broken[0][field]=value;raw=json.dumps(broken).encode();meta=deepcopy(self.meta)
            meta['files']['recipes.json'].update(sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
            with self.assertRaises(ValueError):verified_recipes(meta,raw)
        meta=deepcopy(self.meta);meta['files']['recipes.json']['records']+=1
        with self.assertRaises(ValueError):verified_recipes(meta,self.raw)
        meta=deepcopy(self.meta);meta['data_updated_at']='2099-01-01T00:00:00Z'
        with self.assertRaises(ValueError):verified_recipes(meta,self.raw)

    def test_stale_generations_cannot_publish_proofs_or_replace_the_current_catalog(self):
        proofs=recipe_proofs(self.store,self.meta,self.raw);new=deepcopy(self.meta);new['data_updated_at']='2026-10-29T15:56:20Z'
        self.store.replace(new,self.payloads)
        with self.assertRaises(ValueError):recipe_proofs(self.store,self.meta,self.raw)
        with self.assertRaises(ValueError):self.store.confirm(proofs,'recipe',manifest=self.meta,payload=self.raw)
        with self.assertRaises(ValueError):self.store.replace(self.meta,self.payloads)
        self.assertFalse(self.store.available('items',2040003))
        self.assertIsNone(self.store.payload('recipes.json',self.meta['files']['recipes.json']['sha256']))

    def test_cancelled_recipe_transaction_rolls_back_proofs_and_cached_bytes(self):
        proofs=recipe_proofs(self.store,self.meta,self.raw);calls=[]
        def guard():
            calls.append(1)
            if len(calls)>1:raise CancelledError()
        with self.assertRaises(CancelledError):self.store.confirm(proofs,'recipe',manifest=self.meta,payload=self.raw,guard=guard)
        self.assertFalse(self.store.available('items',2040003));self.assertIsNone(self.store.payload('recipes.json',self.meta['files']['recipes.json']['sha256']))
        token=RequestToken()
        def fetch(url):token.cancel();return self.raw
        with self.assertRaises(CancelledError):RecipeAvailability(self.store,fetch).refresh(token)
        self.assertFalse(self.store.available('items',2040003))

    def test_recipe_payload_is_reused_and_failed_download_preserves_existing_proofs(self):
        fetch=Mock(return_value=self.raw);loader=RecipeAvailability(self.store,fetch)
        self.assertTrue(loader.refresh(RequestToken()));self.assertFalse(loader.refresh(RequestToken()));self.assertEqual(fetch.call_count,1)
        meta=deepcopy(self.meta);meta['files']['recipes.json']['sha256']='0'*64;self.store.replace(meta,self.payloads)
        fetch.return_value=b'bad'
        with self.assertRaises(ValueError):loader.refresh(RequestToken())
        self.assertTrue(self.store.available('items',2040003))

    def test_exact_fresh_screen_identity_adds_availability_without_a_market_price(self):
        service=self.service();args=self.sighting()
        self.assertTrue(ReferenceService.observe_screen(service,self.catalog,**args,notify=False))
        self.assertTrue(self.store.available('items',2040803));self.assertEqual(self.store.evidence('items',2040803)[0]['source'],'screen')
        self.assertIsNotNone(self.store.catalog(self.catalog).resolve('Gloves Attack Scroll: Chaos'))
        with patch.object(self.store,'connect',side_effect=AssertionError('Repeated frame touched SQLite')):
            self.assertFalse(ReferenceService.observe_screen(service,self.catalog,**args,notify=False))

    def test_screen_rejects_wrong_identity_tier_alias_or_unverified_context(self):
        base=self.sighting()
        for changes in ({'game_id':True},{'game_id':2040802},{'visible_name':'Gloves Attack Scroil: Chaos'},
                {'visible_name':'Gloves Attack Scroll: Ch...'},{'tier':'Greater'},{'tier':None},{'surface':'chat'},
                {'surface':'search'},{'game_verified':False},{'panel_verified':False},{'game_verified':1},
                {'captured_at':time.time()-4},{'captured_at':float('nan')},{'captured_at':time.time()+10},{'mode':'screenshot'}):
            self.assertIsNone(screen_proof(self.store,self.catalog,**{**base,**changes}))
        duplicate=Catalog.from_items([*self.catalog.items,Item(99999,'Gloves Attack Scroll: Chaos',tier='Chaos')])
        self.assertIsNone(screen_proof(self.store,duplicate,**base))
        self.assertFalse(self.store.available('items',2040803))

    def test_already_released_items_do_not_gain_per_frame_records_or_notifications(self):
        service=self.service();args={**self.sighting(),'game_id':2040000,'visible_name':'Hat Accuracy Scroll: Lesser','tier':'Lesser'}
        with patch.object(self.store,'confirm',side_effect=AssertionError('Existing release was written again')):
            self.assertFalse(ReferenceService.observe_screen(service,self.catalog,**args))
        self.assertFalse(service.screen_notification_pending);service.updated.emit.assert_not_called()

    def test_new_screen_evidence_coalesces_catalog_notifications(self):
        service=self.service()
        with patch('price_lens.reference_service.QTimer.singleShot') as schedule:
            self.assertTrue(ReferenceService.observe_screen(service,self.catalog,**self.sighting()))
            second={**self.sighting(),'game_id':2040807,'visible_name':'Gloves Magic Attack Scroll: Chaos'}
            self.assertTrue(ReferenceService.observe_screen(service,self.catalog,**second));self.assertEqual(schedule.call_count,1)
        ReferenceService._notify_screen(service);service.updated.emit.assert_called_once()
