"""Only fresh native item pixels can extend the released search catalog."""
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QRect
from PySide6.QtGui import QColor,QImage,QPainter

from price_lens.capture import PixelReader
from price_lens.domain import Catalog
from test_reference import documents,generation
import test_ui_context as fixtures


IDENTITY=2040807
NAME='Gloves Magic Attack Scroll: Chaos'


class NativeAvailabilityUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixtures.ContextUiTests.setUpClass.__func__(cls)

    def setUp(self):
        fixtures.ContextUiTests.setUp(self)
        w=self.window;docs=documents()
        docs['items.json'] += [dict(id=1,name='Example Hat',category='Equipment'),
            dict(id=IDENTITY,name=NAME,category='Consumable',sub_category='Scroll',scroll=dict(tier='Chaos')),
            dict(id=2043003,name='One-Handed Sword Attack Scroll: Chaos',category='Consumable',sub_category='Scroll',scroll=dict(tier='Chaos'))]
        w.reference.store.replace(*generation(docs))
        w.on_catalog(Catalog(dict(items=[dict(id=1,name='Example Hat')],scrolls=[
            dict(id=IDENTITY,name=NAME,tier='Chaos'),dict(id=2043003,name='One-Handed Sword Attack Scroll: Chaos',tier='Chaos')])))
        self.assertNotIn(IDENTITY,[i.game_id for i in w.search_panel.catalog.items])
        reader=w.reader;reader.live_source=True;reader.paused=False;reader.game_guards=[]
        reader.guard_matches=PixelReader.guard_matches
        self.base_image=QImage(800,800,QImage.Format.Format_RGBA8888);self.base_image.fill(QColor('#807a72'))
        paint=QPainter(self.base_image)
        paint.fillRect(QRect(30,750,50,20),QColor('#f1b57e'));paint.fillRect(QRect(100,750,80,20),QColor('#825923'));paint.end()
        self.frame(self.base_image)

    def tearDown(self):fixtures.ContextUiTests.tearDown(self)

    def frame(self,image):
        reader=self.window.reader;reader.image=image.copy();reader.submitted_image=image.copy()
        reader.last_frame=time.monotonic();reader.last_locator_check=reader.last_frame
        reader.game_area=QRect(0,0,800,800)
        reader.game_guards=[(r,PixelReader.guard_signature(image,r)) for r in (QRect(30,750,50,20),QRect(100,750,80,20))]
        return int(reader.last_frame*1000)

    def shop(self):
        w=self.window;image=self.base_image.copy();paint=QPainter(image)
        paint.fillRect(QRect(300,200,240,300),QColor('#eadfbd'))
        paint.fillRect(QRect(300,194,240,4),QColor('#343434'));paint.fillRect(QRect(542,196,16,308),QColor('#555555'))
        paint.setPen(QColor('#161923'));paint.drawText(342,238,NAME);paint.end()
        stamp=self.frame(image);w.reader.shop_context=QRect(300,200,240,300);w.reader.pointer=(340,240)
        return dict(atMs=stamp,pointerAtRead=[340,240],shop=dict(area=dict(x=300,y=200,width=240,height=300),rows=[
            dict(name=NAME,tier='chaos',price=dict(quantity=1,mesos=123456),area=dict(x=340,y=220,width=180,height=40))]),
            hover=dict(pointer=dict(x=340,y=240)),tooltip={})

    def description(self,*,inventory=False,pinned=False,name=NAME):
        w=self.window;image=self.base_image.copy();paint=QPainter(image)
        paint.fillRect(QRect(95,95,360,330),QColor('#464b78'));paint.setPen(QColor('#ffffff'));paint.drawText(106,124,name);paint.end()
        stamp=self.frame(image);w.reader.shop_context=None;w.reader.pointer=(520,240) if inventory else (340,240)
        result=dict(atMs=stamp,pointerAtRead=list(w.reader.pointer),shop=None,
            tooltip=dict(found=dict(name=name,area=dict(x=105,y=110,width=340,height=18))))
        if pinned:result['tooltip']['found']['pinned']=True
        if inventory:
            result['tooltipAssociation']=dict(state='inventory-primary',token='verified-source-cell',
                source=dict(x=500,y=200,width=200,height=300),slot=dict(x=510,y=224,width=36,height=36),
                panel=dict(x=95,y=95,width=360,height=330),guards=[dict(x=500,y=200,width=200,height=16),dict(x=95,y=95,width=360,height=2)])
        return result

    def assert_hidden(self):
        self.app.processEvents();self.assertFalse(self.window.reference.store.available('items',IDENTITY))
        self.assertNotIn(IDENTITY,[i.game_id for i in self.window.search_panel.catalog.items])

    def test_fresh_clean_native_shop_row_enters_search_once_without_a_market_price(self):
        w=self.window;result=self.shop();w.on_reading(result)
        self.assertTrue(w.reference.store.available('items',IDENTITY))
        self.app.processEvents();self.assertIn(IDENTITY,[i.game_id for i in w.search_panel.catalog.items])
        proof=w.reference.store.evidence('items',IDENTITY)[0];self.assertEqual(proof['source'],'screen');self.assertEqual(proof['surface'],'shop-row')
        with patch.object(w.reference.store,'confirm',side_effect=AssertionError('Repeated frame wrote another proof')):
            w.on_reading(result)

    def test_inventory_association_and_pinned_item_description_establish_exact_identity(self):
        for options in (dict(inventory=True),dict(pinned=True)):
            with self.subTest(options=options):
                w=self.window
                with w.reference.store.connect() as db:db.execute("DELETE FROM availability WHERE kind='items' AND id=?",(IDENTITY,))
                w.reference.screen_known.clear();result=self.description(**options);w.on_reading(result)
                self.assertTrue(w.reference.store.available('items',IDENTITY))
                self.assertEqual(w.reference.store.evidence('items',IDENTITY)[0]['surface'],'item-description')

    def test_fresh_validated_shop_description_can_prove_an_item_behind_a_covered_row(self):
        w=self.window;result=self.shop();result['shop']['rows'][0]['covered']=True
        image=w.reader.image.copy();paint=QPainter(image)
        paint.fillRect(QRect(360,190,360,330),QColor('#464b78'));paint.setPen(QColor('#ffffff'));paint.drawText(372,215,NAME);paint.end()
        result['atMs']=self.frame(image)
        result['hover']['tooltip']=dict(found=dict(name=NAME,area=dict(x=372,y=201,width=340,height=18)))
        w.on_reading(result)
        self.assertIsNotNone(w.shop_description)
        self.assertTrue(w.reference.store.available('items',IDENTITY))
        self.assertEqual(w.reference.store.evidence('items',IDENTITY)[0]['surface'],'item-description')

    def test_screenshots_manual_crops_missing_game_and_stale_or_future_reads_cannot_promote(self):
        w=self.window
        for mutation in ('screenshot','crop','no game','no guards','old locator','old frame','absent stamp','old stamp','future stamp','bad stamp'):
            with self.subTest(mutation=mutation):
                w.mode='live';w.reader.crop=None;result=self.description(pinned=True)
                if mutation=='screenshot':w.mode='screenshot'
                elif mutation=='crop':w.reader.crop=QRect(0,0,800,800)
                elif mutation=='no game':w.reader.game_area=None
                elif mutation=='no guards':w.reader.game_guards=[]
                elif mutation=='old locator':w.reader.last_locator_check-=4
                elif mutation=='old frame':w.reader.last_frame-=4
                elif mutation=='absent stamp':result.pop('atMs')
                elif mutation=='old stamp':result['atMs']-=4000
                elif mutation=='future stamp':result['atMs']+=1000
                elif mutation=='bad stamp':result['atMs']=True
                w.on_reading(result);self.assert_hidden()
        w.mode='live';w.reader.crop=None

    def test_covered_held_and_cached_shop_rows_never_establish_circulation(self):
        w=self.window
        for flag in ('covered','retained','reference_only','listing_old','presentation_held'):
            with self.subTest(flag=flag):
                w.shop_rows.reset();result=self.shop();result['shop']['rows'][0][flag]=True
                w.on_reading(result);self.assert_hidden()
        w.shop_rows.reset();result=self.shop();row=result['shop']['rows'][0]
        processed=w.shop_rows.observe(result['shop'],w.reader.submitted_image)
        result['shop']['rows']=[]
        self.assertFalse(w.observe_native_availability(result,w.reader.submitted_image,w.reader.image,rows=processed));self.assert_hidden()

    def test_changed_native_row_pixels_or_game_guards_revoke_current_frame_authority(self):
        w=self.window
        for changed in ('row','game guard','shop guard'):
            with self.subTest(changed=changed):
                w.shop_rows.reset();result=self.shop()
                rect={'row':QRect(340,220,180,40),'game guard':QRect(30,750,50,20),'shop guard':QRect(300,194,240,4)}[changed]
                paint=QPainter(w.reader.image);paint.fillRect(rect,QColor('#ffffff'));paint.end()
                w.on_reading(result);self.assert_hidden()

    def test_raw_ocr_alias_cannot_become_proof_after_price_name_canonicalization(self):
        w=self.window;result=self.description(pinned=True,name='Gloves Magic Attack Scroil: Chaos')
        with patch.object(w.tooltip_names,'resolve',side_effect=lambda found,*args:{**found,'name':NAME}):w.on_reading(result)
        self.assert_hidden()

    def test_retained_description_and_typed_chat_text_do_not_establish_a_new_item(self):
        w=self.window;result=self.description(pinned=True)
        # Seed presentation only; the next actual read has no native title.
        w.tooltip_reference.observe(result['tooltip']['found'],w.reader.image,w.reader.pointer)
        result['tooltip']['found']=None;w.on_reading(result);self.assert_hidden()
        result=self.description();w.reader.image=self.base_image.copy();w.reader.submitted_image=self.base_image.copy()
        w.on_reading(result);self.assert_hidden()
        w.search_panel.query.setText(NAME);w.search_panel.timer.stop();w.search_panel.find_items();self.assert_hidden()

    def test_changed_name_pixels_and_overlay_masks_cannot_supply_description_proof(self):
        w=self.window
        for hidden in (False,True):
            result=self.description(pinned=True)
            if hidden:
                with patch.object(w,'annotation_exclusions',return_value=[QRect(105,110,340,18)]):w.on_reading(result)
            else:
                w.reader.image.setPixelColor(110,115,QColor('#000000'));w.on_reading(result)
            self.assert_hidden()

    def test_catalog_refresh_is_deferred_and_coalesced_outside_the_ocr_callback(self):
        w=self.window;result=self.description(pinned=True)
        with patch.object(w,'on_reference_data') as refresh:
            w.on_reading(result);self.assertTrue(w.reference.store.available('items',IDENTITY));refresh.assert_not_called()
            # A second identity and repeated frames share the one deferred update.
            second=self.description(pinned=True,name='One-Handed Sword Attack Scroll: Chaos')
            w.on_reading(second);self.assertTrue(w.reference.store.available('items',2043003))
            w.on_reading(second);self.app.processEvents();refresh.assert_called_once()
