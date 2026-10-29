"""Atomic reference generations, exact drop identities and offline refresh reuse."""
from concurrent.futures import CancelledError
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from price_lens.reference_data import ReferenceStore,FILES,API,drop_url,image_url
from price_lens.reference_service import ReferenceService
from price_lens.http_json import RequestToken


def documents():
    return {'items.json':[{'id':1001,'name':'Leaf Earrings','category':'Equipment','price':100,'stats':{'reqLevel':25,'incMDD':10},
                            'icon_url':'https://osmsdataexplorer.com/data/current/images/items/00001001.png'},
                           {'id':4001,'name':'Green Mushroom Cap','category':'Etc','price':3}],
        'cash_shop.json':[{'item_id':5001,'name':'Test Cash Hat','category':'Equipment','price':5500},
                          {'item_id':1001,'name':'Conflicting cash alias','price':500}, {'item_id':5002,'name':''}],
        'monsters.json':[{'id':13,'name':'Green Mushroom','level':14,'hp':233,'mp':30,'exp':26,'stats':{'PADamage':54,'PDDamage':0},
            'spawns':[{'map_id':100,'count':31},{'map_id':9999,'count':1}],
            'icon_url':'https://osmsdataexplorer.com/data/images/monsters/example.png'},
            {'id':14,'name':'Blue Mushroom','level':19,'hp':342,'exp':35,'spawns':[]}],
        'skills.json':[{'id':1300000,'name':'Spear Mastery','class_name':'Spearman','job_tier':'2nd Job','max_level':3,
            'description':'Improves spear mastery.','levels':[{'level':n,'mpCon':n,'damage':n*10} for n in (1,2,3)],
            'level_descriptions':['Rank one','Rank two','Rank three']}],
        'maps.json':[{'id':100,'name':'Mushroom Garden','region':'Victoria Island','street_name':'Henesys','mobs':[{'mob_id':13,'x':10,'y':20}]}],
        'npcs.json':[{'id':103,'name':'Jane','maps':[100],'icon_url':'https://osmsdataexplorer.com/data/current/images/npcs/0000103.png'}],
        'quests.json':[{'id':10002,'name':'Jane and the Mushroom','region':'Lith Harbor','npc_id':103,'level_min':20,
            'description':'Help Jane.','requirements':[{'type':'mob','id':13,'count':30}],
            'rewards':[{'type':'exp','value':1610},{'type':'money','value':658},{'type':'item','id':1001,'count':1}]}]}


def generation(docs=None):
    docs=documents() if docs is None else docs
    payloads={name:json.dumps(docs[name],separators=(',',':')).encode() for name in FILES}
    meta={'game':'MapleStory Classic World','schema_version':1,'client_build':'a'*40,'data_updated_at':'2026-10-26T16:46:04Z',
          'files':{name:{'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'records':len(docs[name])} for name,raw in payloads.items()}}
    return meta,payloads


def allow_fixture(store):
    rows=[]
    for kind in ('items','monsters','maps','quests'):
        rows.extend(dict(kind=kind,id=entry.id,name=entry.name,detail={'label':'Fixture release evidence'}) for entry in store.search(kind,limit=1000,released=False)[0])
    store.confirm(rows,'nia-release')


def report(**changes):
    return {'monster_id':'13','monster_name':'Green Mushroom','item_id':'4001','item_name':'Green Mushroom Cap',
            'category':'etc','rate':'40','kills':'100','observed':'40','minimum':'1','maximum':'1','version':'0.9.0',
            'date':'2026-10-11','page':'Green Mushroom','item_page':'Green Mushroom Cap','low':'30','high':'50',**changes}


class ReferenceStoreTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.store=ReferenceStore(Path(self.folder.name)/'reference.sqlite');self.meta,self.payloads=generation();self.store.replace(self.meta,self.payloads,at=100)
        allow_fixture(self.store)

    def test_bulk_generation_preserves_stats_images_skills_and_named_cash(self):
        self.assertEqual(self.store.metadata()['counts'],{'items':3,'monsters':2,'skills':1})
        self.assertEqual(self.store.entry('items',1001)[1]['price'],100)
        self.assertFalse(self.store.entry('items',1001)[1].get('cash'))
        self.assertEqual(self.store.entry('items',5001)[1]['nx_price'],5500)
        self.assertIsNone(self.store.entry('items',5002))
        self.assertEqual(self.store.entry('skills',1300000)[1]['levels'][1]['damage'],20)
        self.assertEqual(self.store.locations(13)[0]['name'],'Mushroom Garden')
        self.assertEqual(self.store.locations(13)[0]['count'],31)

    def test_search_is_local_prefix_and_exact_id_with_safe_query_syntax(self):
        self.assertEqual([r.id for r in self.store.search('items','mush cap')[0]],[4001])
        self.assertEqual([r.id for r in self.store.search('skills','spear',category='Spearman')[0]],[1300000])
        self.assertEqual([r.id for r in self.store.search('items','1001')[0]],[1001])
        self.assertEqual(self.store.search('items','" OR * ; DROP TABLE entities --')[1],0)
        self.assertEqual(self.store.search('items',category='Cash')[1],1)

    def test_equipment_class_level_name_and_other_sort_orders_use_local_data(self):
        docs=documents();docs['items.json'] += [
            dict(id=1002,name='Axe',category='Equipment',stats={'reqLevel':40},req_classes=['Warrior']),
            dict(id=1003,name='Bow',category='Equipment',stats={'reqLevel':10},req_classes=['Bowman']),
            dict(id=1004,name='Wand',category='Equipment',stats={'reqLevel':30},req_classes=['Magician'])]
        self.store.replace(*generation(docs));allow_fixture(self.store)
        def names(order):return [e.name for e in self.store.search('items',category='Equipment',sort=order)[0]]
        self.assertEqual(names('name'),['Axe','Bow','Leaf Earrings','Wand'])
        self.assertEqual(names('level'),['Bow','Leaf Earrings','Wand','Axe'])
        self.assertEqual(names('level-desc'),list(reversed(names('level'))))
        self.assertEqual(names('class'),['Leaf Earrings','Axe','Wand','Bow'])
        self.assertEqual(self.store.search('items','Bow')[0][0].job,'Bowman')
        self.assertEqual([e.name for e in self.store.search('monsters',sort='level')[0]],['Green Mushroom','Blue Mushroom'])
        self.assertEqual([e.name for e in self.store.search('monsters',sort='name')[0]],['Blue Mushroom','Green Mushroom'])
        with self.assertRaises(ValueError):self.store.search('items',sort='SQL is not accepted')

    def test_crafting_is_not_browsable_or_openable_but_remains_in_verified_payload(self):
        docs=documents();docs['skills.json'].append(dict(id=1000,name='Mining',job_tier='Crafting',job_id=900))
        self.store.replace(*generation(docs))
        self.assertEqual(self.store.search('skills','Mining')[1],0)
        self.assertFalse(self.store.available('skills',1000));self.assertIsNotNone(self.store.entry('skills',1000))
        self.assertNotIn(9,[r['value'] for r in self.store.groups('skills','family')])

    def test_bad_hash_wrong_world_duplicates_and_bad_shapes_preserve_previous_generation(self):
        for reason in ('hash','world','duplicate','shape','date'):
            with self.subTest(reason=reason):
                docs=documents()
                if reason=='duplicate':docs['items.json'].append(docs['items.json'][0])
                if reason=='shape':docs['skills.json'][0]['levels']='not a rank list'
                meta,payloads=generation(docs)
                if reason=='hash':payloads['items.json']+=b' '
                if reason=='world':meta['game']='Original MapleStory'
                if reason=='date':meta['data_updated_at']=123
                with self.assertRaises((ValueError,TypeError)):self.store.replace(meta,payloads,at=200)
                self.assertEqual(self.store.metadata()['checked_at'],100)
                self.assertEqual(self.store.entry('items',1001)[0].name,'Leaf Earrings')

    def test_cancellation_before_commit_rolls_back_entities_and_drop_rows(self):
        self.store.save_drops([report()],at=100)
        docs=documents();docs['items.json'][0]['name']='Changed';meta,payloads=generation(docs)
        calls=[]
        def guard():
            calls.append(1)
            if len(calls)>1:raise CancelledError()
        with self.assertRaises(CancelledError):self.store.replace(meta,payloads,at=200,guard=guard)
        self.assertEqual(self.store.entry('items',1001)[0].name,'Leaf Earrings')
        self.assertEqual(len(self.store.drops_for('items',4001)),1)

    def test_drop_relationships_require_both_exact_ids_and_names_and_keep_observation_units(self):
        bad=[report(monster_id='14'),report(item_id='1001'),report(rate='NaN'),report(observed='101'),report(item_id=True),report(kills=100.5)]
        self.assertEqual(self.store.save_drops([report(),*bad]),1)
        item=self.store.drops_for('items',4001)[0];monster=self.store.drops_for('monsters',13)[0]
        self.assertEqual(item,monster);self.assertEqual(item['rate'],40);self.assertEqual(item['kills'],100)
        self.assertEqual(item['version'],'0.9.0');self.assertEqual(item['low'],30)
        with self.assertRaises(ValueError):self.store.save_drops(bad)
        self.assertEqual(len(self.store.drops_for('items',4001)),1)

    def test_meso_and_nothing_reports_are_not_fake_items_and_missing_rates_stay_unknown(self):
        rows=[report(item_id=None,item_name=None,item_page='Meso',category='meso',rate='60',minimum='20',maximum='30'),
              report(item_id=None,item_name=None,item_page='',category='nothing',rate='15'),
              report(rate=None,kills=None,observed=None)]
        self.assertEqual(self.store.save_drops(rows),3)
        self.assertEqual(len(self.store.drops_for('items',4001)),1)
        self.assertIsNone(self.store.drops_for('items',4001)[0]['rate'])

    def test_new_generation_drops_unmatched_old_relationships(self):
        self.store.save_drops([report()]);docs=documents();docs['items.json'][1]['name']='Different item'
        self.store.replace(*generation(docs))
        self.assertEqual(self.store.drops_for('monsters',13),[])
        self.assertEqual(self.store.metadata()['drop_count'],0)

    def test_media_urls_are_public_dataset_images_only(self):
        good='https://osmsdataexplorer.com/data/images/monsters/a.webp';self.assertEqual(image_url(good),good)
        for url in ('file:///tmp/test.png','https://example.com/a.png','https://osmsdataexplorer.com@evil.test/data/a.png',
                    'https://osmsdataexplorer.com/data/a.png?credential=x','https://osmsdataexplorer.com/private/a.png'):
            self.assertEqual(image_url(url),'')


class ReferenceRefreshTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup);self.meta,self.payloads=generation();self.calls=[]
        release_patch=patch('price_lens.reference_service.AvailabilityLoader.refresh',lambda loader,token,force=False:allow_fixture(loader.store))
        release_patch.start();self.addCleanup(release_patch.stop)
        def fetch_json(url):
            self.calls.append(url)
            if url==API+'meta.json':return deepcopy(self.meta)
            return {'cargoquery':[{'title':report()}]}
        def fetch_bytes(url):self.calls.append(url);return self.payloads[url.rsplit('/',1)[1]]
        self.service=ReferenceService(Path(self.folder.name)/'reference.sqlite',fetch_bytes=fetch_bytes,fetch_json=fetch_json)
        self.addCleanup(self.service.close)

    def test_initial_download_then_only_manifest_until_a_file_or_report_interval_changes(self):
        s=self.service;self.assertEqual(s.refresh(RequestToken(),False),{})
        self.assertEqual(sum(url.startswith(API) and not url.endswith('meta.json') for url in self.calls),len(FILES))
        self.calls.clear();self.assertEqual(s.refresh(RequestToken(),False),{});self.assertEqual(self.calls,[API+'meta.json'])
        docs=documents();docs['items.json'][0]['price']=101;self.meta,self.payloads=generation(docs)
        self.calls.clear();s.refresh(RequestToken(),False)
        self.assertEqual(self.calls,[API+'meta.json',API+'items.json'])
        self.assertEqual(s.store.entry('items',1001)[1]['price'],101)

    def test_drop_pagination_is_bounded_and_malformed_refresh_keeps_the_good_table(self):
        s=self.service;s.refresh(RequestToken(),False)
        s.fetch_json=lambda url:self.meta if url==API+'meta.json' else {'error':'temporary'}
        self.assertIn('drops',s.refresh(RequestToken(),True));self.assertEqual(len(s.store.drops_for('items',4001)),1)
        s.fetch_json=lambda url:self.meta if url==API+'meta.json' else {'cargoquery':[]}
        self.assertIn('drops',s.refresh(RequestToken(),True));self.assertEqual(len(s.store.drops_for('items',4001)),1)

    def test_failed_core_refresh_preserves_search_and_valid_drop_reports(self):
        s=self.service;s.refresh(RequestToken(),False);s.fetch_json=lambda url:{'schema_version':9}
        self.assertIn('core',s.refresh(RequestToken(),False));self.assertEqual(s.store.search('items','leaf')[1],1)
        self.assertEqual(len(s.store.drops_for('items',4001)),1)

    def test_cancelled_refresh_cannot_publish_or_commit(self):
        token=RequestToken();token.cancel()
        with self.assertRaises(CancelledError):self.service.refresh(token,False)
        self.assertEqual(self.service.store.metadata(),{})

    def test_worker_completion_reaches_the_qt_owner_and_coalesces_overlapping_updates(self):
        finished=[];self.service.updated.connect(lambda:finished.append(threading.get_ident()))
        self.service.start();self.service.start(True)
        deadline=time.monotonic()+3
        while self.service.busy and time.monotonic()<deadline:QTest.qWait(10)
        self.assertEqual(finished,[threading.get_ident()]);self.assertFalse(self.service.busy)
        self.assertEqual(self.calls.count(API+'meta.json'),1)
        self.assertEqual(self.service.timer.interval(),86400000)

    def test_closing_inflight_update_discards_late_results(self):
        entered=threading.Event();release=threading.Event();finished=[]
        def fetch(url):entered.set();release.wait(3);return self.meta
        self.service.fetch_json=fetch;self.service.updated.connect(lambda:finished.append(True));self.service.start()
        deadline=time.monotonic()+2
        while not entered.is_set() and time.monotonic()<deadline:QTest.qWait(5)
        self.assertTrue(entered.is_set());self.service.close();release.set();self.service.pool.shutdown(wait=True)
        self.app.processEvents();self.assertEqual(finished,[]);self.assertEqual(self.service.store.metadata(),{})
