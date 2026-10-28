"""Offline reference navigation, real image decoders and visible-only motion."""
import base64
from pathlib import Path
import tempfile
import time
import unittest
from PySide6.QtCore import QByteArray,QBuffer,QIODevice,QObject,QSettings,Qt,Signal,QCoreApplication,QEvent
from PySide6.QtGui import QColor,QImage,QMovie
from PySide6.QtNetwork import QNetworkReply
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QLabel
from price_lens.domain import Catalog,Quote
from price_lens.reference_service import ReferenceService
from price_lens.reference_media import ReferenceMedia,ReferenceSprite,decode
from price_lens.reference_ui import DatabasePanel
from price_lens.watchlist import Watchlist
from test_reference import generation,report,documents

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
        values=[];self.panel.price_requested.connect(values.append);self.panel.market_button.click();self.assertEqual(values,[1001])
        self.market.quote=Quote(1001,6000,time.time(),time.time(),25,'MesoWatch','','24h');self.panel.update_market()
        self.assertIn('6,000',self.panel.market_label.text());self.assertEqual(self.market.requests,[])
        self.panel.set_catalog(Catalog({'items':[{'id':1001,'name':'Wrong item'}]}))
        self.assertTrue(self.panel.watch_button.isHidden());self.assertTrue(self.panel.market_button.isHidden())

    def test_monster_locations_and_drop_links_round_trip_to_the_search_results(self):
        self.search('monsters','green');p=self.panel;p.open_first();self.app.processEvents()
        self.assertEqual(p.selected.id,13);self.assertIn('Locations',p.section_targets);self.assertIn('Drops',p.section_targets)
        labels=' '.join(w.text() for w in p.detail.findChildren(QLabel))
        self.assertIn('Mushroom Garden',labels);self.assertIn('40.00% observed',labels);self.assertIn('100 kills',labels)
        p.open(('items',4001));self.assertEqual(p.selected.kind,'items')
        self.assertIn('Green Mushroom',' '.join(w.text() for w in p.detail.findChildren(QLabel)))
        p.go_back();self.assertEqual(p.selected.key,('monsters',13))
        p.go_back();self.assertIsNone(p.selected);self.assertEqual(p.kind,'monsters');self.assertEqual(p.query.text(),'green')
        self.assertEqual(p.results.count(),1)

    def test_currency_drop_renders_the_small_coin_without_an_item_identity(self):
        self.service.store.save_drops([report(item_id=None,item_name=None,item_page='Meso',category='meso',minimum='10',maximum='20')])
        self.search('monsters','green');self.panel.open_first();self.app.processEvents()
        self.assertFalse(self.panel.icon(':meso').isNull())
        self.assertIn('Currency',' '.join(w.text() for w in self.panel.detail.findChildren(QLabel)))
        self.assertTrue(any(icon==':meso' for _,_,icon in self.panel.related))

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
        urls=[ICON,MOVIE,ICON.replace('1001','1002')]
        self.cache.observe(urls);self.assertEqual(len(self.replies),2);self.cache.observe(urls);self.assertEqual(len(self.replies),2)
        self.replies[0][1].complete(png());self.assertEqual(len(self.replies),3)
        self.replies[1][1].complete(ANIMATION);self.replies[2][1].complete(png())
        self.cache.observe(urls);self.assertEqual(len(self.replies),3);self.assertFalse(self.cache.image(MOVIE).isNull())
        disk=ReferenceMedia(self.folder.name)
        try:self.assertFalse(disk.image(ICON).isNull());self.assertIsNotNone(disk.path(MOVIE))
        finally:disk.close();disk.deleteLater()

    def test_misses_and_oversized_responses_do_not_repeat_until_the_negative_cache_expires(self):
        self.cache.observe([ICON]);self.replies[0][1].complete(b'invalid');self.cache.observe([ICON]);self.assertEqual(len(self.replies),1)
        self.cache.observe([MOVIE]);reply=self.replies[-1][1];reply.data=b'x'*(4*1024*1024+1);reply.readyRead.emit()
        self.assertTrue(reply.aborted);self.assertIsNone(self.cache.path(MOVIE))

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
