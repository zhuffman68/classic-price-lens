"""Quest/map identities, linked reward pools and verified map coordinates."""
import hashlib,json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import QBuffer,QIODevice,QRect
from PySide6.QtGui import QImage,QColor,QPainter
from price_lens.reference_data import ReferenceStore
from price_lens.reference_indexes import ReleaseIndex,release_name
from price_lens.reference_relations import quest_rewards,item_quest_sources
from price_lens.reference_geometry import MapGeometry,alignment,native_size,matching_projection
from test_reference import generation,documents,allow_fixture
from test_reference_ui import ANIMATION


class ExpandedReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.store=ReferenceStore(Path(self.folder.name)/'reference.sqlite');self.store.replace(*generation());allow_fixture(self.store)

    def test_quest_portrait_reward_sources_and_map_relationships_use_canonical_ids(self):
        quest=self.store.entry('quests',10002)
        self.assertEqual(quest[0].icon,self.store.entry('npcs',103)[0].icon)
        self.assertEqual(self.store.search('quests','Jane')[1],1)
        self.assertEqual(self.store.map_monsters(100)[0][0].name,'Green Mushroom')
        source=item_quest_sources(self.store,1001)[0]
        self.assertEqual(source['name'],'Jane and the Mushroom');self.assertEqual(source['target'],('quests',10002))
        self.assertEqual(source['icon'],quest[0].icon)

    def test_unreleased_hollow_and_dev_places_are_hidden_even_with_saved_index_evidence(self):
        docs=documents();docs['quests.json'].append(dict(id=999,name='Unreleased quest',region='Forgotten Hollow'))
        docs['maps.json'].append(dict(id=999,name='Test chamber',region='Dev'))
        self.store.replace(*generation(docs));allow_fixture(self.store)
        self.assertFalse(self.store.available('quests',999));self.assertFalse(self.store.available('maps',999))
        self.assertEqual(self.store.search('quests','Unreleased')[1],0)
        self.assertNotIn('Forgotten Hollow',[g['value'] for g in self.store.groups('quests','region')])

    def test_quest_chain_labels_match_only_exact_name_chain_and_class(self):
        row=dict(name='Finding the Instructor',chain="The Warrior's Next Journey",region='Warrior')
        self.assertTrue(release_name('quests',row,"+ The Warrior's Next Journey (2)Finding the Instructor (Warrior)"))
        self.assertFalse(release_name('quests',row,"+ The Warrior's Next Journey (2)Finding the Instructor (Magician)"))
        self.assertFalse(release_name('quests',row,"+ A different chain (2)Finding the Instructor (Warrior)"))
        parser=ReleaseIndex('maps');parser.feed('<a href="/msclassic/maps/100">Mushroom Garden</a><a href="/msclassic/maps/100">Wrong map</a>')
        self.assertNotIn(100,parser.rows)

    def test_random_and_choice_rewards_preserve_class_pools_and_do_not_duplicate_flat_rows(self):
        row=dict(rewards=[dict(type='exp',value=10),dict(type='item',id=1,count=1,guaranteed=False)],
            reward_random=[dict(groups=[dict(classes=['Warrior'],items=[dict(id=1,count=1,weight=1),dict(id=2,count=1,weight=3)])])])
        result=quest_rewards(row)
        self.assertEqual(len(result),3);self.assertIn('25%',result[1]['caption']);self.assertIn('Warrior',result[1]['caption'])
        self.assertIn('75%',result[2]['caption'])

    def test_map_alignment_requires_two_distinct_consistent_anchors_and_exact_destinations(self):
        row=dict(portals=[dict(name='a',type=2,x=-10,y=5,dest_map_id=1),dict(name='b',type=2,x=15,y=30,dest_map_id=2)])
        targets=[dict(name='a',type=2,x=0,y=10,dest_map='1'),dict(name='b',type=2,x=25,y=35,dest_map='2')]
        self.assertEqual(alignment(row,targets),dict(dx=10,dy=5,anchors=2))
        self.assertIsNone(alignment(row,targets[:1]))
        self.assertIsNone(alignment(row,[targets[0],{**targets[1],'x':26}]))
        self.assertIsNone(alignment(row,[targets[0],{**targets[1],'dest_map':'99'}]))

    def test_native_image_size_requires_matching_content_hash_and_bounded_valid_webp(self):
        url='https://osmsdataexplorer.com/data/maps/'+hashlib.md5(ANIMATION).hexdigest()+'.webp'
        self.assertEqual(native_size(ANIMATION,url),(8,8));self.assertIsNone(native_size(ANIMATION+b'corrupt',url))
        self.assertIsNone(native_size(ANIMATION,'https://example.com/map.webp'))
        self.assertFalse(matching_projection(ANIMATION,b'not an image'))

    def test_marker_projection_requires_matching_terrain_and_rejects_a_shifted_minimap(self):
        image=QImage(64,48,QImage.Format.Format_RGB32)
        painter=QPainter(image)
        for y in range(0,48,8):
            for x in range(0,64,8):painter.fillRect(QRect(x,y,8,8),QColor('#d4bc72' if (x+y)//8%2 else '#28464d'))
        painter.end()
        def encoded(frame,kind):
            buffer=QBuffer();buffer.open(QIODevice.OpenModeFlag.WriteOnly);self.assertTrue(frame.save(buffer,kind,100));return bytes(buffer.data())
        native=encoded(image,'WEBP');small=encoded(image,'PNG')
        self.assertTrue(matching_projection(native,small))
        shifted=QImage(image.size(),image.format());shifted.fill(QColor('#172027'));painter=QPainter(shifted);painter.drawImage(4,0,image);painter.end()
        self.assertFalse(matching_projection(native,encoded(shifted,'PNG')))

    def test_geometry_downloads_once_and_reuses_cached_metadata_without_decoding_the_full_image(self):
        url='https://osmsdataexplorer.com/data/maps/'+hashlib.md5(ANIMATION).hexdigest()+'.webp'
        row=dict(id=100,render_url=url,portals=[dict(name='a',type=2,x=1,y=1,dest_map_id=1),dict(name='b',type=2,x=6,y=6,dest_map_id=2)])
        calls=[]
        def fetch_json(url):calls.append('index');return {'000000100':[dict(name='a',type=2,x=1,y=1,dest_map='1'),dict(name='b',type=2,x=6,y=6,dest_map='2')]}
        def fetch_bytes(url):calls.append('image');return ANIMATION
        service=MapGeometry(self.store,fetch_bytes=fetch_bytes,fetch_json=fetch_json);self.addCleanup(service.close)
        service.select(row);service.select(row)
        deadline=time.monotonic()+3
        while service.pending and time.monotonic()<deadline:QTest.qWait(10)
        self.assertEqual(service.cached(row),dict(dx=0,dy=0,anchors=2,width=8,height=8,projection_verified=False))
        service.select(row);self.assertEqual(calls,['index','image']);self.assertIsNone(service.pending)
