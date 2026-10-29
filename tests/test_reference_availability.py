"""Release evidence excludes raw/never-sold content while retaining past releases."""
from concurrent.futures import CancelledError
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs,urlsplit
import json
import tempfile
import time
import unittest
from price_lens.domain import Catalog,Quote
from price_lens.http_json import RequestToken
from price_lens.reference_data import ReferenceStore
from price_lens.reference_availability import AvailabilityLoader,market_proofs
from test_reference import generation,documents
from test_reference_community import index_html


class ReleaseEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.store=ReferenceStore(Path(self.folder.name)/'ref.sqlite');self.store.replace(*generation());self.calls=[]
        def fetch(url):
            self.calls.append(url);q=parse_qs(urlsplit(url).query);kind=q['type'][0];page=int(q['page'][0]);rows=[]
            if kind=='Equip':rows=[self.item(1001,'Leaf Earrings','Equip',sources=['npc','mob'])]
            if kind=='Etc':rows=[self.item(4001,'Green Mushroom Cap','Etc',sources=['mob'])]
            if kind=='Cash Equip':rows=[self.item(5001,'Test Cash Hat','Cash Equip',stats={'onSale':False})]
            return {'page':page,'hasMore':False,'items':rows}
        def fetch_bytes(url):
            self.calls.append(url)
            if url.endswith('maps/all'):return b'<a href="/msclassic/maps/100">Mushroom Garden</a>'
            if url.endswith('quest-tracker/all'):return b'<button aria-controls="quest-10002">+ Jane and the Mushroom</button>'
            return index_html()
        self.loader=AvailabilityLoader(self.store,fetch,fetch_bytes)

    @staticmethod
    def item(identity,name,kind,*,stats=None,sources=None):
        return dict(id=identity+100,name=name,type=kind,iconKey=str(identity),stats=json.dumps(stats or {}),sources=sources or [])

    def test_catalog_presence_has_no_release_evidence_until_a_verified_source_arrives(self):
        self.assertEqual(self.store.search('items')[1],0);self.assertEqual(self.store.groups('items','category'),[])
        self.assertFalse(self.store.available('items',1001));self.assertIsNotNone(self.store.entry('items',1001))
        self.loader.refresh(RequestToken());self.assertTrue(self.store.available('items',1001))
        self.assertEqual(self.store.released_counts(),{'items':3,'monsters':2})
        self.assertEqual(self.store.evidence('items',1001)[0]['label'],'NPC shop / Monster drop')

    def test_shared_catalog_contains_only_released_items_and_preserves_exact_original_identity(self):
        raw=Catalog({'items':[dict(id=1001,name='Leaf Earrings',category='Equipment'),dict(id=4001,name='Green Mushroom Cap')]})
        self.assertEqual(self.store.catalog(raw).items,[])
        self.store.confirm([dict(kind='items',id=1001,name='Leaf Earrings')],'nia-release')
        shared=self.store.catalog(raw);self.assertEqual([i.game_id for i in shared.items],[1001])
        self.assertIs(shared.items[0],raw.resolve('Leaf Earrings'))
        self.assertIsNone(shared.resolve('Green Mushroom Cap'))

    def test_formerly_released_cosmetics_stay_available_after_sale_records_disappear(self):
        self.loader.refresh(RequestToken());self.assertTrue(self.store.available('items',5001))
        self.loader.fetch_json=lambda url:{'items':[],'page':int(parse_qs(urlsplit(url).query)['page'][0]),'hasMore':False}
        self.loader.refresh(RequestToken(),True)
        self.assertTrue(self.store.available('items',5001));self.assertEqual(self.store.search('items',category='Cash')[1],1)

    def test_never_sold_future_and_old_beta_rows_are_not_promoted_from_client_flags(self):
        for changes in ({'stats':{'onSale':True,'cashShopLastSeenIn':'COT1'}}, {'stats':{'availableDate':'2099-11-18','onSale':True}}):
            row=self.item(5001,'Test Cash Hat','Cash Equip',**changes)
            self.assertIsNone(self.loader.item(row,'Cash Equip'))
        self.assertFalse(self.store.available('items',5001))
        self.assertIsNone(self.loader.item(self.item(5001,'Wrong cosmetic','Cash Equip'),'Cash Equip'))
        self.assertIsNone(self.loader.item({**self.item(5001,'Test Cash Hat','Cash Equip'),'iconKey':'5001.0'},'Cash Equip'))

    def test_future_expansion_and_gm_test_entities_remain_hidden_despite_provider_claims(self):
        docs=documents();docs['monsters.json'] += [dict(id=54,name='Glowshroom',level=39,hp=1374),dict(id=9990000,name='Test(Basic)',level=1,hp=1)]
        docs['items.json'].append(dict(id=2100001,name='GM Black Sack: Mano Level 20',category='Consumable'))
        self.store.replace(*generation(docs))
        for kind,identity,name in [('monsters',54,'Glowshroom'),('monsters',9990000,'Test(Basic)'),('items',2100001,'GM Black Sack: Mano Level 20')]:
            with self.assertRaises(ValueError):self.store.confirm([dict(kind=kind,id=identity,name=name)],'nia-release')
            self.assertFalse(self.store.available(kind,identity))

    def test_evidence_is_bound_to_exact_names_and_does_not_survive_an_id_rename(self):
        self.loader.refresh(RequestToken());docs=documents();docs['items.json'][0]['name']='Other item';self.store.replace(*generation(docs))
        self.assertFalse(self.store.available('items',1001));self.assertEqual(self.store.search('items','Other')[1],0)
        with self.assertRaises(ValueError):self.store.confirm([dict(kind='items',id=True,name='Other item')],'nia-release')

    def test_daily_source_cache_and_queries_exclude_ossyria_unsold_and_closed_test_content(self):
        self.loader.refresh(RequestToken());calls=list(self.calls);self.calls.clear();self.loader.refresh(RequestToken())
        self.assertEqual(self.calls,[])
        queries=[parse_qs(urlsplit(url).query) for url in calls if '/api/items?' in url]
        self.assertEqual(len(queries),6)
        for q in queries:
            self.assertEqual(q['ossyria'],['0']);self.assertEqual(q['cot1'],['0'])
            self.assertEqual(q.get('unsold') if q['type']==['Cash Equip'] else q['avail'],['hide'] if q['type']==['Cash Equip'] else ['launch'])

    def test_failed_and_cancelled_refresh_preserve_prior_positive_evidence(self):
        self.loader.refresh(RequestToken());before=self.store.released_counts()
        self.loader.fetch_bytes=lambda url:b'not a monster table'
        with self.assertRaises(ValueError):self.loader.refresh(RequestToken(),True)
        self.assertEqual(self.store.released_counts(),before)
        token=RequestToken();token.cancel()
        with self.assertRaises(CancelledError):self.loader.refresh(token,True)
        self.assertEqual(self.store.released_counts(),before)

    def test_live_market_sales_prove_circulation_but_catalog_rows_and_undated_prices_do_not(self):
        catalog=Catalog({'items':[{'id':1001,'name':'Leaf Earrings'}]})
        now=time.time();quote=asdict(Quote(1001,5000,now,now,2,'MesoWatch','','last 10 sales',basis='observed shop sales'))
        snapshot=SimpleNamespace(meta={'checked_at':now},rows={1001:dict(name='Leaf Earrings',quote=quote)})
        proofs=market_proofs(self.store,catalog,snapshot);self.assertEqual(len(proofs),1)
        self.store.confirm(proofs,'market');self.assertTrue(self.store.available('items',1001))
        for changes in ({'sample_count':0},{'observed_at':None},{'observed_at':0},{'observed_at':now+10000},{'world':'other-world'},{'basis':'catalog price'},{'game_id':4001}):
            snapshot.rows[1001]['quote']={**quote,**changes};self.assertEqual(market_proofs(self.store,catalog,snapshot),[])
        snapshot.rows[1001]=dict(name='Other item',quote=quote);self.assertEqual(market_proofs(self.store,catalog,snapshot),[])
