"""Exact source identities, last-good data and isolated TTLs, without HTTP."""
from pathlib import Path
import tempfile,unittest,time
from PySide6.QtWidgets import QApplication
from price_lens.http_json import RequestToken
from price_lens.reference_data import ReferenceStore
from price_lens.reference_sources import npc_shops,reward_boxes,ItemSources
from price_lens.reference_items import normalize
from test_reference import generation,documents,allow_fixture

PAGE=b'''<main><div><div><a href="/msclassic/npcs/103">Jane</a>Launch prices
<a href="/msclassic/maps/100">Mushroom Garden</a></div><table><tbody>
<tr><td><img src="/msclassic/api/assets/icons/1001"></td><td><a href="/msclassic/item-db/991">Leaf Earrings</a></td><td>2,000<span>mesos</span></td></tr>
<tr><td><img src="/msclassic/api/assets/icons/4001"></td><td><a href="/msclassic/item-db/993">Wrong Name</a></td><td>2,000<span>mesos</span></td></tr>
</tbody></table></div></main>'''
BOX=b'''<span>Found in: <a href="/msclassic/item-db/505">Magic Box</a></span>'''


class SourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.store=ReferenceStore(Path(self.folder.name)/'reference.sqlite')
        docs=documents();docs['items.json'].append(dict(id=2430000,name='Magic Box',category='Use'))
        self.store.replace(*generation(docs));allow_fixture(self.store)

    def test_shop_requires_exact_icon_identity_and_name_not_provider_id(self):
        rows=npc_shops(PAGE,self.store);self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['item_id'],1001);self.assertEqual(rows[0]['id'],103)
        self.assertEqual(rows[0]['price'],2000);self.store.save_sources('npc',rows)
        self.assertEqual(self.store.sources_for(1001),rows)
        self.assertTrue(self.store.available('npcs',103))

    def test_reward_boxes_use_verified_source_and_box_id_and_are_cached(self):
        calls=[]
        def fetch(url):calls.append(url);return BOX
        def resolver(entry,token):return {1001:991,2430000:505}.get(entry.id)
        service=ItemSources(self.store,resolver,fetch_bytes=fetch);self.addCleanup(service.close)
        service.load(self.store.entry('items',1001)[0],RequestToken())
        rows=self.store.sources_for(1001);self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['id'],2430000);self.assertEqual(rows[0]['basis'],'Player reported')
        service.enabled=True;service.select(self.store.entry('items',1001)[0]);self.assertIsNone(service.pending)
        self.assertEqual(len(calls),1)
        self.assertEqual(reward_boxes(BOX),[(505,'Magic Box')])

    def test_failure_retains_last_good_shop_and_box_generations(self):
        self.store.save_sources('npc',npc_shops(PAGE,self.store))
        row=dict(kind='box',id=2430000,name='Magic Box',item_id=1001,item_name='Leaf Earrings',basis='Player reported',source_url='https://meowdb.com/msclassic/item-db/991')
        self.store.save_sources('box',[row],item_id=1001);self.store.source_failed(1001)
        self.assertEqual([r['kind'] for r in self.store.sources_for(1001)],['npc','box'])
        self.assertEqual(self.store.source_check(1001)[1],1)

    def test_scroll_target_correction_requires_matching_family_and_name(self):
        for identity,name,target in ((2040605,'Bottomwear HP Scroll: Greater','Bottomwear'),(2040001,'Hat DEF Scroll: Intermediate','Hat'),(2048001,'Pet Equip Jump Scroll: Intermediate','Pet equipment')):
            row=dict(id=identity,name=name,scroll=dict(slot='Other',success_rate=10,stats={'incMHP':30}))
            fixed=normalize(row);self.assertEqual(fixed['scroll']['slot'],target)
            self.assertEqual(fixed['scroll']['stats'],row['scroll']['stats']);self.assertEqual(row['scroll']['slot'],'Other')
        ambiguous=dict(id=2040605,name='Unrecognized Scroll',scroll=dict(slot='Other'))
        self.assertEqual(normalize(ambiguous),ambiguous)
