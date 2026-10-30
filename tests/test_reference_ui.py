"""Offline reference navigation, real image decoders and visible-only motion."""
import base64
from pathlib import Path
from unittest.mock import patch
import tempfile
import time
import unittest
from PySide6.QtCore import QByteArray,QBuffer,QIODevice,QObject,QSettings,Qt,Signal,QCoreApplication,QEvent
from PySide6.QtGui import QColor,QImage,QMovie
from PySide6.QtNetwork import QNetworkReply
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QLabel,QSlider,QPushButton
from price_lens.domain import Catalog,Quote
from price_lens.reference_service import ReferenceService
from price_lens.reference_media import ReferenceMedia,ReferenceSprite,decode
from price_lens.reference_ui import DatabasePanel
from price_lens.watchlist import Watchlist
from test_reference import generation,report,documents,allow_fixture

ANIMATION=base64.b64decode('UklGRoQAAABXRUJQVlA4WAoAAAACAAAABwAABwAAQU5JTQYAAAAAAAAAAABBTk1GKAAAAAAAAAAAAAcAAAcAAFAAAAJWUDhMDwAAAC8HwAEABxD9j/4HIqL/AQBBTk1GKAAAAAAAAAAAAAcAAAcAAHgAAABWUDhMDwAAAC8HwAEAB1DAiP4HIqL/AQA=')
ICON='https://osmsdataexplorer.com/data/current/images/items/00001001.png'
MOVIE='https://osmsdataexplorer.com/data/images/monsters/example.webp'


def png(width=16,height=16):
    image=QImage(width,height,QImage.Format.Format_RGBA8888);image.fill(QColor('#ff9900'))
    buffer=QBuffer();buffer.open(QIODevice.OpenModeFlag.WriteOnly);image.save(buffer,'PNG');return bytes(buffer.data())


class FakeMedia(QObject):
    ready=Signal(str)
    def __init__(self):super().__init__();self.demands=[]
    def image(self,url):return QImage()
    def path(self,url):return None
    def observe(self,urls):self.demands.append(list(urls))
    def close(self):pass


class Market:
    def __init__(self):self.quote=Quote(1001,5000,time.time(),time.time(),20,'MesoWatch','','24h');self.requests=[]
    def cached(self,item):return self.quote if item.game_id==1001 else None


class DatabaseUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.path=Path(self.folder.name)
        self.service=ReferenceService(self.path/'reference.sqlite');self.service.store.replace(*generation());self.service.store.save_drops([report()])
        allow_fixture(self.service.store)
        self.media=FakeMedia();self.panel=DatabasePanel(self.service,self.path/'images',media=self.media)
        self.catalog=Catalog({'items':[{'id':1001,'name':'Leaf Earrings','category':'Equipment'},{'id':4001,'name':'Green Mushroom Cap'}]})
        self.panel.set_catalog(self.catalog);self.watches=Watchlist(QSettings(str(self.path/'settings.ini'),QSettings.Format.IniFormat))
        self.panel.set_watchlist(self.watches);self.market=Market();self.panel.set_market(self.market,900)
        self.app.setProperty('reduceMotion',False);self.panel.resize(428,480);self.panel.show();self.panel.set_active(True);self.app.processEvents()

    def tearDown(self):
        self.panel.close();self.panel.deleteLater();self.service.close();self.service.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.app.processEvents();self.folder.cleanup()

    def search(self,kind,query):
        self.panel.choose_kind(kind);self.panel.query.setText(query);self.panel.timer.stop();self.panel.search();self.app.processEvents()

    def test_item_stars_and_prices_share_exact_catalog_ids_without_market_requests(self):
        self.search('items','Leaf');self.panel.open_first();self.app.processEvents()
        self.assertIn('5,000',self.panel.market_label.text());self.assertTrue(self.panel.watch_button.isVisible())
        self.panel.watch_button.click();self.assertIn(1001,self.watches.ids)
        self.assertIsNotNone(self.panel.detail.summary_card)
        self.assertEqual(self.panel.detail.tabs.tabText(1),'Sources')
        self.market.quote=Quote(1001,6000,time.time(),time.time(),25,'MesoWatch','','24h');self.panel.update_market()
        self.assertIn('6,000',self.panel.market_label.text());self.assertEqual(self.market.requests,[])
        self.panel.set_catalog(Catalog({'items':[{'id':1001,'name':'Wrong item'}]}))
        self.assertEqual(self.panel.detail.summary_card.data['quote'].game_id,1001)
        self.assertIsNone(self.panel.catalog_item(self.panel.selected))

    def test_monster_locations_and_drop_links_round_trip_to_the_search_results(self):
        self.search('monsters','green');p=self.panel;p.open_first();self.app.processEvents()
        self.assertEqual(p.selected.id,13);self.assertIn('Locations',[p.detail.tabs.tabText(i) for i in range(p.detail.tabs.count())])
        labels=' '.join(row['name']+' '+row.get('subtitle','') for listing in p.detail.lists for row in listing.records)
        self.assertIn('Mushroom Garden',labels);self.assertIn('40.00% observed',labels);self.assertIn('100 kills',labels)
        p.open(('items',4001));self.assertEqual(p.selected.kind,'items')
        self.assertIn('Green Mushroom',' '.join(row['name'] for row in p.detail.drop_list.records))
        p.go_back();self.assertEqual(p.selected.key,('monsters',13))
        p.go_back();self.assertIsNone(p.selected);self.assertEqual(p.kind,'monsters');self.assertEqual(p.query.text(),'green')
        self.assertEqual(p.results.count(),1)

    def test_two_column_monster_drops_return_to_the_same_monster_tab_and_scroll(self):
        docs=documents();docs['items.json'] += [dict(id=6000+n,name=f'Drop {n}',category='Etc') for n in range(20)]
        self.service.store.replace(*generation(docs));allow_fixture(self.service.store)
        self.service.store.save_drops([report(item_id=str(6000+n),item_name=f'Drop {n}',item_page=f'Drop {n}') for n in range(20)])
        p=self.panel;self.app.setProperty('reduceMotion',True);p.open(('monsters',13));p.detail.tabs.setCurrentIndex(2);self.app.processEvents()
        listing=p.detail.drop_list;self.assertTrue(listing.drop_tiles)
        self.assertEqual(listing.visualItemRect(listing.item(0)).top(),listing.visualItemRect(listing.item(1)).top())
        self.assertGreater(listing.visualItemRect(listing.item(1)).left(),listing.visualItemRect(listing.item(0)).left())
        listing.verticalScrollBar().setValue(listing.verticalScrollBar().maximum());self.app.processEvents();position=listing.verticalScrollBar().value()
        listing.activate_row(listing.item(19));self.assertEqual(p.selected.kind,'items')
        p.go_back();self.app.processEvents();self.assertEqual(p.selected.key,('monsters',13));self.assertEqual(p.detail.tabs.currentIndex(),2)
        self.assertEqual(p.detail.drop_list.verticalScrollBar().value(),position)

    def test_sort_controls_are_relevant_to_kind_and_match_shared_search_style(self):
        p=self.panel;p.choose_kind('monsters');self.assertEqual(p.sort_group.checkedAction().data(),'level')
        p.choose_kind('skills');self.assertTrue(p.sort_row.isHidden())
        p.choose_kind('items');p.enter_group(('category','Equipment','Equipment'))
        self.assertIn('class',p.sort_actions)
        from price_lens.search_field import SearchField
        self.assertIsInstance(p.query,SearchField);self.assertEqual(p.query.minimumHeight(),42)

    def test_sort_popup_preserves_navigation_space_and_does_not_add_a_row(self):
        p=self.panel;p.resize(460,480);p.enter_group(('category','Equipment','Equipment'))
        p.query.setText('Leaf');p.timer.stop();p.search();self.app.processEvents()
        self.assertEqual(p.sort_button.width(),60)
        self.assertGreater(p.breadcrumb.width(),200)
        self.assertIn('Equipment',p.breadcrumb.path.text())
        self.assertNotIn('…',p.breadcrumb.path.text())
        centers=[widget.mapTo(p,widget.rect().center()).y() for widget in (p.back,p.breadcrumb,p.summary,p.sort_button)]
        self.assertLessEqual(max(centers)-min(centers),1)
        list_top=p.pages.mapTo(p,p.pages.rect().topLeft()).y()
        p.sort_menu.popup(p.sort_button.mapToGlobal(p.sort_button.rect().bottomLeft()));self.app.processEvents()
        self.assertEqual(p.pages.mapTo(p,p.pages.rect().topLeft()).y(),list_top)
        p.sort_actions['level-desc'].trigger();p.sort_menu.hide();self.app.processEvents()
        self.assertEqual(p.sort_mode,'level-desc');self.assertTrue(p.sort_actions['level-desc'].isChecked())
        self.assertEqual(p.query.text(),'Leaf');self.assertEqual(p.scope,(('category','Equipment','Equipment'),))
        self.assertEqual(p.summary.text(),'1 results')

    def test_named_quest_source_and_reward_round_trip_preserves_sources_subpage(self):
        p=self.panel;self.app.setProperty('reduceMotion',True);p.open(('items',1001));p.detail.tabs.setCurrentIndex(1)
        listing=p.detail.drop_list;quest=next(listing.item(i) for i,r in enumerate(listing.records) if r.get('target')==('quests',10002))
        listing.activate_row(quest);self.app.processEvents();self.assertEqual(p.selected.key,('quests',10002))
        self.assertEqual(p.detail.entry.icon,self.service.store.entry('npcs',103)[0].icon)
        self.assertEqual([p.detail.tabs.tabText(i) for i in range(p.detail.tabs.count())],['Overview','Requirements','Rewards'])
        self.assertIsNone(p.detail.rank_slider);p.go_back();self.app.processEvents()
        self.assertEqual(p.selected.key,('items',1001));self.assertEqual(p.detail.tabs.currentIndex(),1)

    def test_map_monster_links_and_back_restore_map_without_starting_an_image_geometry_request(self):
        p=self.panel;self.app.setProperty('reduceMotion',True)
        with patch.object(self.service.geometry,'select'):
            p.open(('maps',100));self.app.processEvents();self.assertIsNotNone(p.detail.map_preview)
            self.assertEqual(p.kind_bar.count(),5);self.assertEqual(p.detail.tabs.tabText(0),'Monsters')
            listing=p.detail.lists[0];self.assertEqual(listing.records[0]['target'],('monsters',13))
            listing.activate_row(listing.item(0));p.go_back();self.app.processEvents();self.assertEqual(p.selected.key,('maps',100))

    def test_price_refresh_keeps_card_geometry_and_only_updates_retained_price_fields(self):
        p=self.panel;self.app.setProperty('reduceMotion',True);p.open(('items',1001));self.app.processEvents()
        view=p.detail;name=view.item_name;geometry=view.geometry();panel=view.tabs.geometry()
        for count,price in ((100,999999),(200,1),(300,10000)):
            self.market.quote=Quote(1001,price,time.time(),time.time(),count,'MesoWatch','','24h')
            p.update_market();self.app.processEvents()
            self.assertIs(p.detail,view);self.assertIs(view.item_name,name);self.assertEqual(view.geometry(),geometry);self.assertEqual(view.tabs.geometry(),panel)
            self.assertEqual(view.fields['sales'].text(),f'{count} sales in the last 24hr')

    def test_currency_drop_renders_the_small_coin_without_an_item_identity(self):
        self.service.store.save_drops([report(item_id=None,item_name=None,item_page='Meso',category='meso',minimum='10',maximum='20')])
        self.search('monsters','green');self.panel.open_first();self.app.processEvents()
        self.assertFalse(self.panel.icon(':meso').isNull())
        self.assertIn('Currency',[row['name'] for row in self.panel.detail.drop_list.records])
        self.assertTrue(any(row['icon']==':meso' for row in self.panel.detail.drop_list.records))

    def test_skill_rank_changes_keep_header_and_controls_in_place(self):
        self.search('skills','mastery');p=self.panel;p.open_first();self.app.processEvents()
        self.assertEqual(p.rank_slider.value(),3);before=p.item_name.geometry()
        p.rank_slider.setValue(1);self.app.processEvents();self.assertEqual(p.item_name.geometry(),before)
        labels=' '.join(w.text() for w in p.detail.findChildren(QLabel));self.assertIn('Rank one',labels);self.assertIn('Rank 1 / 3',labels)

    def test_refining_results_retains_rows_icons_and_ignores_stale_clicks(self):
        self.search('items','le');p=self.panel;row=p.results.item(0);icon=row.icon().cacheKey()
        p.query.setText('leaf');self.assertTrue(p.results.isEnabled());p.choose_result(row);self.assertIsNone(p.selected)
        p.timer.stop();p.search();self.assertIs(p.results.item(0),row);self.assertEqual(p.results.item(0).icon().cacheKey(),icon)

    def test_visibility_and_reduced_motion_stop_image_demand_and_content_animation(self):
        self.search('items','leaf');p=self.panel;p.observe_media();self.assertTrue(self.media.demands[-1])
        p.set_active(False);self.app.processEvents();self.assertEqual(self.media.demands[-1],[])
        self.app.setProperty('reduceMotion',True)
        try:
            p.open_first();self.assertIsNone(p.content.outgoing);p.go_back();self.assertIsNone(p.content.outgoing)
        finally:self.app.setProperty('reduceMotion',False)

    def test_source_update_replaces_selected_details_and_removal_returns_to_results(self):
        self.search('items','leaf');p=self.panel;p.open_first()
        docs=documents();docs['items.json'][0]['price']=999;self.service.store.replace(*generation(docs));p.reloaded()
        self.assertEqual(p.selected.id,1001);self.assertIn('999',' '.join(w.text() for w in p.detail.findChildren(QLabel)))
        docs['items.json']=[docs['items.json'][1]];docs['cash_shop.json']=[docs['cash_shop.json'][0]]
        self.service.store.replace(*generation(docs));p.reloaded();self.assertIsNone(p.selected);self.assertEqual(p.pages.currentWidget(),p.list_page)


    def test_entry_controls_are_owned_by_their_entry_and_never_leak_into_other_kinds(self):
        p=self.panel;self.app.setProperty('reduceMotion',True)
        self.search('skills','mastery');p.open_first();self.assertEqual(len(p.detail.findChildren(QSlider)),1)
        for key in (('items',1001),('monsters',13),('items',5001)):
            p.open(key);QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.app.processEvents()
            self.assertEqual(p.detail.findChildren(QSlider),[]);self.assertIsNone(p.rank_slider)
        self.assertEqual(p.detail.tabs.count(),1);self.assertEqual(p.detail.tabs.tabText(0),'Sources');self.assertIsNone(p.detail.drop_list)
        labels=' '.join(w.text() for w in p.detail.findChildren(QLabel))
        self.assertNotIn('No confirmed',labels)
        self.assertFalse(any(w.isVisible() and 'reports' in w.text().lower() for w in p.detail.findChildren(QPushButton)))

    def test_background_reports_retain_header_controls_scroll_and_skill_rank(self):
        p=self.panel;self.app.setProperty('reduceMotion',True)
        self.search('monsters','green');p.open_first();header=p.item_name;view=p.detail
        p.detail.tabs.setCurrentIndex(2)
        self.service.store.save_drops([report(rate='50',observed='50')]);p.extra_updated(p.selected.key)
        self.assertIs(p.item_name,header);self.assertIs(p.detail,view);self.assertEqual(view.tabs.currentIndex(),2)
        self.assertIn('50.00% observed',view.drop_list.item(0).text())
        self.search('skills','mastery');p.open_first();p.rank_slider.setValue(1);header=p.item_name;slider=p.rank_slider
        p.reloaded();self.assertIs(p.item_name,header);self.assertIs(p.rank_slider,slider);self.assertEqual(slider.value(),1)
        self.assertIsNone(p.content.outgoing)

    def test_cash_entries_do_not_request_generic_drop_reports_even_when_online(self):
        self.service.extra.enabled=True
        with patch.object(self.service.extra.pool,'submit') as submit:
            self.panel.open(('items',5001));submit.assert_not_called()
        self.assertIsNone(self.panel.detail.drop_list);self.assertIsNone(self.service.extra.pending)

    def test_detail_subpages_slide_and_background_updates_do_not_restart_navigation(self):
        self.app.setProperty('reduceMotion',False);self.search('monsters','green');self.panel.open_first();QTest.qWait(270)
        view=self.panel.detail;view.tabs.setCurrentIndex(2);self.assertTrue(view.tabs.sliding)
        self.panel.extra_updated(self.panel.selected.key);self.assertIs(self.panel.detail,view)
        QTest.qWait(340);self.assertFalse(view.tabs.sliding)
        self.app.setProperty('reduceMotion',True);view.tabs.setCurrentIndex(1);self.assertFalse(view.tabs.sliding)

    def test_category_and_job_navigation_keep_search_and_restore_breadcrumbs(self):
        docs=documents();docs['items.json'] += [dict(id=1302000,name='Sword',category='Equipment',sub_category='Weapon',weapon={'type':'1H Sword'}),
            dict(id=1432000,name='Spear',category='Equipment',sub_category='Weapon',weapon={'type':'Spear'})]
        docs['skills.json'][0]['job_id']=130
        self.service.store.replace(*generation(docs));allow_fixture(self.service.store);p=self.panel;p.reloaded()
        self.assertIs(p.pages.currentWidget(),p.tiles)
        p.enter_group(('category','Equipment','Equipment'));p.enter_group(('sub_category','Weapon','Weapons'))
        self.assertEqual({r['name'] for r in p.tiles.records},{'1H Sword','Spear'})
        p.enter_group(('weapon.type','Spear','Spear'));self.assertEqual(p.results.count(),1)
        p.open_first();self.assertEqual(p.selected.id,1432000);p.go_back();self.assertIn('Spear',p.breadcrumb.text())
        p.go_back();self.assertEqual({r['name'] for r in p.tiles.records},{'1H Sword','Spear'})
        p.choose_kind('skills');self.assertIn('Warrior',[r['name'] for r in p.tiles.records])
        p.enter_group(('family',1,'Warrior'));self.assertEqual([r['name'] for r in p.tiles.records],['Spearman'])
        p.enter_group(('job_id',130,'Spearman'));p.query.setText('mastery');p.timer.stop();p.search();self.assertEqual(p.results.count(),1)

    def test_nearby_thumbnail_prefetch_starts_before_rows_enter_the_viewport(self):
        listing=self.panel.results;records=[dict(key=n,target=('items',n),name=f'Item {n}',subtitle='Example',icon=ICON.replace('1001',str(n+2000))) for n in range(60)]
        listing.populate(records);listing.resize(360,220);listing.show();self.app.processEvents()
        viewport=listing.viewport().rect();visible=[listing.item(i).data(Qt.ItemDataRole.UserRole+1) for i in range(listing.count()) if listing.visualItemRect(listing.item(i)).intersects(viewport)]
        demand=listing.nearby_urls();self.assertEqual(demand[:len(visible)],visible);self.assertGreater(len(demand),len(visible))
        listing.verticalScrollBar().setValue(listing.verticalScrollBar().maximum());self.app.processEvents()
        self.assertNotEqual(listing.nearby_urls()[0],demand[0]);self.assertIn(records[-1]['icon'],listing.nearby_urls())


class FakeReply(QObject):
    readyRead=Signal();finished=Signal()
    def __init__(self):super().__init__();self.data=b'';self.failure=QNetworkReply.NetworkError.NoError;self.aborted=False
    def setReadBufferSize(self,size):self.limit=size
    def readAll(self):result=self.data;self.data=b'';return QByteArray(result)
    def error(self):return self.failure
    def abort(self):self.aborted=True;self.failure=QNetworkReply.NetworkError.OperationCanceledError;self.finished.emit()
    def complete(self,data):self.data=data;self.readyRead.emit();self.finished.emit()


class ReferenceMediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.cache=ReferenceMedia(self.folder.name);self.replies=[]
        def get(request):
            reply=FakeReply();self.replies.append((request.url().toString(),reply));return reply
        self.cache.manager.get=get

    def tearDown(self):
        self.cache.close();self.cache.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.app.processEvents();self.folder.cleanup()

    def test_actual_png_and_animated_webp_decoders_reject_invalid_and_oversized_images(self):
        self.assertFalse(decode(png()).isNull());self.assertFalse(decode(ANIMATION).isNull())
        for data in (b'not an image',png(2048,1),b'RIFF'+b'\0'*30,b'x'*(4*1024*1024+1)):self.assertTrue(decode(data).isNull())

    def test_downloads_are_bounded_coalesced_and_reused_from_disk(self):
        urls=[ICON,MOVIE,*[ICON.replace('1001',str(n)) for n in (1002,1003,1004)]]
        self.cache.observe(urls);self.assertEqual(len(self.replies),4);self.cache.observe(urls);self.assertEqual(len(self.replies),4)
        self.replies[0][1].complete(png());self.assertEqual(len(self.replies),5)
        self.replies[1][1].complete(ANIMATION)
        for _,reply in self.replies[2:]:reply.complete(png())
        self.cache.observe(urls);self.assertEqual(len(self.replies),5);self.assertFalse(self.cache.image(MOVIE).isNull())
        disk=ReferenceMedia(self.folder.name)
        try:self.assertFalse(disk.image(ICON).isNull());self.assertIsNotNone(disk.path(MOVIE))
        finally:disk.close();disk.deleteLater()

    def test_misses_and_oversized_responses_do_not_repeat_until_the_negative_cache_expires(self):
        self.cache.observe([ICON]);self.replies[0][1].complete(b'invalid');self.cache.observe([ICON]);self.assertEqual(len(self.replies),1)
        self.cache.observe([MOVIE]);reply=self.replies[-1][1];reply.data=b'x'*(4*1024*1024+1);reply.readyRead.emit()
        self.assertTrue(reply.aborted);self.assertIsNone(self.cache.path(MOVIE))

    def test_obsolete_downloads_yield_to_the_current_viewport_without_caching_a_miss(self):
        old=[ICON.replace('1001',str(n)) for n in range(1001,1006)];new=ICON.replace('1001','9000')
        self.cache.observe(old);self.assertEqual(len(self.replies),4)
        self.cache.observe([new]);self.assertEqual(len(self.cache.active),1);self.assertEqual(self.replies[-1][0],new)
        self.assertTrue(all(reply.aborted for _,reply in self.replies[:4]));self.assertTrue(all(url not in self.cache.misses for url in old))
        self.replies[-1][1].complete(png());self.cache.observe([new]);self.assertEqual(len(self.replies),5)

    def test_native_thumbnail_pixels_and_memory_budget_are_preserved(self):
        self.cache.filename(ICON).write_bytes(png(37,26));image=self.cache.image(ICON)
        self.assertEqual((image.width(),image.height()),(37,26))
        for n in range(16):
            large=QImage(512,512,QImage.Format.Format_RGBA8888);large.fill(QColor('orange'));self.cache.remember(str(n),large)
        self.assertLessEqual(self.cache.memory_bytes,8*1024*1024);self.assertLessEqual(len(self.cache.memory),128)

    def test_only_the_visible_selected_sprite_plays_at_native_speed(self):
        self.cache.filename(MOVIE).write_bytes(ANIMATION);self.cache.filename(ICON).write_bytes(png())
        sprite=ReferenceSprite(self.cache);sprite.set_source(ICON,MOVIE);sprite.active=True;self.app.setProperty('reduceMotion',False);sprite.show();self.app.processEvents();sprite.sync()
        try:
            self.assertTrue(sprite.movie.isValid());self.assertEqual(sprite.movie.frameCount(),2);self.assertEqual(sprite.movie.speed(),100)
            self.assertEqual(sprite.movie.state(),QMovie.MovieState.Running)
            self.app.setProperty('reduceMotion',True);sprite.sync();self.assertEqual(sprite.movie.state(),QMovie.MovieState.Paused)
            self.app.setProperty('reduceMotion',False);sprite.hide();self.assertEqual(sprite.movie.state(),QMovie.MovieState.Paused)
            before=sprite.movie.currentFrameNumber();QTest.qWait(150);self.assertEqual(sprite.movie.currentFrameNumber(),before)
        finally:sprite.close();sprite.deleteLater();self.app.setProperty('reduceMotion',False)
