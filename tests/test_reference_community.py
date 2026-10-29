"""Fresh identity proof, cached report updates and votes/rates separation."""
from pathlib import Path
import tempfile
import threading
import time
import unittest
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from price_lens.reference_community import BASE,MonsterIndex,CommunityDrops
from price_lens.reference_data import ReferenceStore
from price_lens.http_json import RequestToken
from test_reference import generation,report,allow_fixture


def index_html(extra=''):
    rows=[f'<tr><td></td><td><a href="/msclassic/monsters/{n}">Dummy {n}</a></td><td>1</td><td>1</td></tr>' for n in range(100,111)]
    rows.append('<tr><td></td><td><a href="/msclassic/monsters/13">Green Mushroom</a></td><td>14</td><td>233</td><td><a href="/msclassic/maps/100">Location</a></td></tr>')
    rows.append('<tr><td></td><td><a href="/msclassic/monsters/14">Blue Mushroom</a></td><td>19</td><td>342</td></tr>')
    return ('<table><tr><th></th><th>NAME</th><th>LV▲</th><th>HP</th></tr>'+''.join(rows)+extra+'</table>').encode()


class CommunityReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.store=ReferenceStore(Path(self.folder.name)/'references.sqlite');self.store.replace(*generation())
        allow_fixture(self.store)
        self.store.save_drops([report()]);self.calls=[]
        def fetch_bytes(url):self.calls.append(url);return index_html()
        def fetch_json(url):
            self.calls.append(url)
            if '/api/items?' in url:return {'items':[{'id':77,'name':'Leaf Earrings','iconKey':'1001'}],'hasMore':False}
            if 'monsterId=' in url:return {'drops':[{'itemIconKey':'4001','itemName':'Green Mushroom Cap','upvotes':99.5,'downvotes':2},
                {'itemIconKey':'1001','itemName':'Wrong name','upvotes':4,'downvotes':0}]}
            return {'drops':[{'monsterId':13,'upvotes':10,'downvotes':0},{'monsterId':9000,'upvotes':5,'downvotes':0}]}
        self.service=CommunityDrops(self.store,fetch_bytes=fetch_bytes,fetch_json=fetch_json);self.service.enabled=True
        self.addCleanup(self.folder.cleanup);self.addCleanup(self.service.close)

    def wait(self):
        deadline=time.monotonic()+3
        while self.service.pending is not None and time.monotonic()<deadline:QTest.qWait(10)
        self.assertIsNone(self.service.pending)

    def test_index_uses_the_actual_name_link_level_and_hp_and_rejects_conflicting_ids(self):
        parser=MonsterIndex();parser.feed(index_html().decode())
        self.assertEqual(parser.rows['13'],{'name':'Green Mushroom','level':14,'hp':233})
        conflict='<tr><td></td><td><a href="/msclassic/monsters/13">Different mob</a></td><td>14</td><td>233</td></tr>'
        parser=MonsterIndex();parser.feed(index_html(conflict).decode());self.assertNotIn('13',parser.rows)
        self.assertIsNone(self.service.verified_monster(13,parser.rows))

    def test_item_reports_bind_only_a_fresh_exact_icon_id_and_name(self):
        entry=self.store.entry('items',1001)[0];self.service.load(entry,RequestToken())
        rows=self.store.drops_for('items',1001);self.assertEqual(len(rows),1);self.assertEqual(rows[0]['monster_id'],13)
        self.assertEqual(rows[0]['source'],'meow');self.assertIsNone(rows[0]['rate'])
        self.assertIn(BASE+'api/drops?itemId=77',self.calls)
        self.assertEqual(self.store.community_check('items',1001)[1]['source_url'],BASE+'item-db/77')

    def test_votes_do_not_overwrite_a_wiki_observed_rate_or_create_a_percentage(self):
        entry=self.store.entry('monsters',13)[0];self.service.load(entry,RequestToken())
        rows=self.store.drops_for('monsters',13)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['rate'],40);self.assertTrue(rows[0]['also_reported'])
        self.assertEqual(rows[0]['kills'],100)
        with self.store.connect() as db:raw=db.execute('SELECT body FROM community_reports').fetchone()[0]
        import json
        saved=json.loads(raw);self.assertEqual(saved['upvotes'],99.5);self.assertIsNone(saved['rate'])
        with self.assertRaises(ValueError):self.store.save_community('monsters',13,[{**saved,'rate':99.5}],{})

    def test_ambiguous_item_ids_do_not_request_or_cache_an_unverified_drop_feed(self):
        self.service.fetch_json=lambda url:{'items':[{'id':77,'name':'Leaf Earrings','iconKey':'1001'},
            {'id':78,'name':'Leaf Earrings','iconKey':'1001'}],'hasMore':False}
        self.service.load(self.store.entry('items',1001)[0],RequestToken())
        self.assertEqual(self.store.drops_for('items',1001),[])
        self.assertTrue(self.store.community_check('items',1001)[1]['error'])

    def test_repeated_selection_and_reopening_reuses_the_cached_empty_or_populated_result(self):
        entry=self.store.entry('items',1001)[0];self.service.select(entry);self.wait();calls=list(self.calls)
        self.service.select(entry);self.service.select(None);self.service.select(entry);self.app.processEvents()
        self.assertEqual(self.calls,calls);self.assertIsNone(self.service.pending)

    def test_new_selection_cancels_the_previous_scan_and_discards_its_late_reply(self):
        entered=threading.Event();release=threading.Event();finished=[]
        def fetch(url):entered.set();release.wait(3);return index_html()
        self.service.fetch_bytes=fetch;self.service.updated.connect(finished.append)
        self.service.select(self.store.entry('monsters',13)[0])
        deadline=time.monotonic()+2
        while not entered.is_set() and time.monotonic()<deadline:QTest.qWait(5)
        self.assertTrue(entered.is_set());self.service.select(self.store.entry('items',1001)[0]);release.set();self.wait()
        self.assertEqual(finished,[('items',1001)]);self.assertIsNone(self.store.community_check('monsters',13))

    def test_failed_report_refresh_retains_saved_relationships_and_does_not_touch_wiki_rates(self):
        entry=self.store.entry('items',1001)[0];self.service.load(entry,RequestToken())
        self.service.fetch_json=lambda url: {'items':[{'id':77,'name':'Leaf Earrings','iconKey':'1001'}]} if '/items?' in url else {'error':'offline'}
        self.service.load(entry,RequestToken())
        self.assertEqual(len(self.store.drops_for('items',1001)),1);self.assertTrue(self.store.community_check('items',1001)[1]['error'])
        self.assertEqual(self.store.drops_for('items',4001)[0]['rate'],40)
