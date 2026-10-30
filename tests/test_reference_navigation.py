"""Compact browsing state, exact links, positive release evidence and cropped maps."""
from pathlib import Path
import tempfile
import unittest
from PySide6.QtCore import QPointF,QRect,Qt
from PySide6.QtGui import QColor,QImage,QPainter
from PySide6.QtWidgets import QApplication
from price_lens.reference_data import ReferenceStore
from price_lens.reference_maps import MapPreview
from test_reference import documents,generation,allow_fixture
import test_reference_ui as fixtures
from test_reference_ui import FakeMedia


class NavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):fixtures.DatabaseUiTests.setUp(self)
    def tearDown(self):fixtures.DatabaseUiTests.tearDown(self)
    def search(self,kind,query):fixtures.DatabaseUiTests.search(self,kind,query)

    def test_kind_switch_restores_selected_entry_query_subpage_and_back_stack(self):
        p=self.panel;self.search('monsters','green');p.open_first();p.detail.tabs.setCurrentIndex(2)
        p.choose_kind('quests');p.query.setText('Jane');p.timer.stop();p.search();p.open_first()
        p.choose_kind('monsters')
        self.assertEqual(p.query.text(),'green');self.assertEqual(p.selected.key,('monsters',13));self.assertEqual(p.detail.tabs.currentIndex(),2)
        p.go_back();self.assertIsNone(p.selected);self.assertEqual(p.query.text(),'green');self.assertEqual(p.results.count(),1)
        p.choose_kind('quests');self.assertEqual(p.selected.key,('quests',10002))

    def test_skill_rank_survives_switching_sections(self):
        p=self.panel;self.search('skills','mastery');p.open_first();p.rank_slider.setValue(1)
        p.choose_kind('monsters');p.choose_kind('skills')
        self.assertEqual(p.rank_slider.value(),1);self.assertIn('Spear Mastery',p.breadcrumb.text())

    def test_breadcrumb_jumps_to_ancestor_and_back_restores_scope_and_selection(self):
        p=self.panel;p.enter_group(('category','Equipment','Equipment'));p.open(('items',1001))
        self.assertIn('Equipment',p.breadcrumb.text());self.assertIn('Leaf Earrings',p.breadcrumb.text())
        p.breadcrumb.root.click();self.assertFalse(p.scope);self.assertIsNone(p.selected)
        p.go_back();self.assertEqual(p.scope,(('category','Equipment','Equipment'),));self.assertEqual(p.selected.key,('items',1001))

    def test_search_all_retains_query_and_back_restores_the_scoped_results(self):
        docs=documents();docs['items.json'].append(dict(id=4002,name='Leaf Fragment',category='Etc'))
        self.service.store.replace(*generation(docs));allow_fixture(self.service.store);p=self.panel;p.reloaded()
        p.enter_group(('category','Equipment','Equipment'));self.assertIn('equipment',p.query.placeholderText())
        p.query.setText('Leaf');p.timer.stop();p.search();self.assertEqual(p.results.count(),1)
        p.search_all.click();self.assertEqual(p.query.text(),'Leaf');self.assertFalse(p.scope);self.assertEqual(p.results.count(),2)
        p.go_back();self.assertEqual(p.query.text(),'Leaf');self.assertEqual(p.results.count(),1);self.assertTrue(p.scope)

    def test_crosslinked_locations_are_clickable_and_return_to_monster(self):
        p=self.panel;p.open(('monsters',13));p.detail.tabs.setCurrentIndex(1)
        listing=p.detail.lists[0];self.assertEqual(listing.records[0]['target'],('maps',100))
        listing.activate_row(listing.item(0));self.assertEqual(p.selected.key,('maps',100));p.go_back()
        self.assertEqual(p.selected.key,('monsters',13));self.assertEqual(p.detail.tabs.currentIndex(),1)

    def test_kind_list_restores_its_sort_and_scroll(self):
        docs=documents();docs['monsters.json'] += [dict(id=100+n,name=f'Monster {n}',level=n) for n in range(90)]
        self.service.store.replace(*generation(docs));allow_fixture(self.service.store);p=self.panel;p.choose_kind('monsters')
        p.sort_choice.setCurrentIndex(p.sort_choice.findData('level-desc'));self.app.processEvents()
        p.results.verticalScrollBar().setValue(300);before=p.results.verticalScrollBar().value();self.assertGreater(before,0)
        p.choose_kind('items');p.choose_kind('monsters');self.app.processEvents()
        self.assertEqual(p.sort_choice.currentData(),'level-desc');self.assertEqual(p.results.verticalScrollBar().value(),before)


class CategoryEvidenceTests(unittest.TestCase):
    def test_missing_representative_image_uses_another_released_entry_without_hiding_quests(self):
        with tempfile.TemporaryDirectory() as folder:
            store=ReferenceStore(Path(folder)/'reference.sqlite');docs=documents()
            docs['quests.json'] += [dict(id=1,name='Start citizenship',region='Citizenship'),
                dict(id=2,name='Meet a resident',region='Citizenship',npc_id=103),
                dict(id=3,name='Crafting apprenticeship',region='Crafting'),
                dict(id=4,name='Warrior advancement',region='Warrior'),
                dict(id=5,name='Future quest',region='Forgotten Hollow')]
            store.replace(*generation(docs));allow_fixture(store)
            groups={row['value']:row for row in store.groups('quests','region')}
            self.assertEqual(groups['Citizenship']['count'],2);self.assertTrue(groups['Citizenship']['entry'].icon)
            self.assertIn('Crafting',groups);self.assertNotIn('Forgotten Hollow',groups)
            sections={row['value']:row['count'] for row in store.groups('quests','quest.section')}
            self.assertEqual(sections,{'Towns':1,'Systems & events':3,'Job advancement':1})


class MapCropTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_transparent_padding_is_cropped_without_moving_verified_markers(self):
        image=QImage(100,80,QImage.Format.Format_ARGB32);image.fill(Qt.GlobalColor.transparent)
        painter=QPainter(image);painter.fillRect(QRect(30,20,40,40),QColor('#879752'));painter.end()
        class Media(FakeMedia):
            def image(self,url):return image
        view=MapPreview(Media(),{'minimap_url':'fixture','mobs':[dict(mob_id=13,x=50,y=40)]});view.resize(400,128)
        view.set_geometry(dict(width=100,height=80,dx=0,dy=0,projection_verified=True),{13:'Green Mushroom'})
        view.show();self.app.processEvents();view.grab()
        bounds=view.source_bounds(image);self.assertLess(bounds.width(),image.width());self.assertLess(bounds.height(),image.height())
        self.assertEqual(len(view.markers),1);center,identity=view.markers[0]
        self.assertLess((center-QPointF(view.width()/2,view.height()/2)).manhattanLength(),5)
        self.assertEqual(view.target_at(center),13)
        view.set_geometry(None);view.grab();self.assertEqual(view.markers,[]);view.close()
