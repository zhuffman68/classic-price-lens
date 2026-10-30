from copy import deepcopy
import unittest
from PySide6.QtCore import QRect
from PySide6.QtGui import QColor,QImage,QPainter
from price_lens.shop_rows import ShopRows


class ShopRowsTests(unittest.TestCase):
    def setUp(self):
        self.image=QImage(800,800,QImage.Format.Format_RGBA8888);self.image.fill(QColor("#223344"))
        self.row={"name":"Work Gloves","price":{"quantity":1,"mesos":100},"area":{"x":160,"y":170,"width":180,"height":40}}
        self.shop={"area":{"x":100,"y":150,"width":260,"height":300},"rows":[self.row]}
        self.memory=ShopRows();self.memory.observe(self.shop,self.image,0)

    def covered(self):
        result=deepcopy(self.shop)
        result["rows"][0].update(name=None,price=None,covered=True)
        return result

    def test_occluded_row_keeps_reference_without_an_assumed_listing(self):
        result=self.memory.observe(self.covered(),self.image,1)[0]
        self.assertEqual(result["name"],"Work Gloves")
        self.assertIsNone(result["price"])
        self.assertTrue(result["retained"])

    def test_held_presentation_is_separate_from_a_current_offer_and_expires(self):
        row=self.memory.observe(self.covered(),self.image,1)[0]
        self.assertIsNone(row['price']);self.assertTrue(row['reference_only'])
        self.assertTrue(row['presentation_held'])
        self.assertEqual(self.memory.presentation_for(row,1),{'quantity':1,'mesos':100})
        expired=self.memory.observe(self.covered(),self.image,31)[0]
        self.assertIsNone(self.memory.presentation_for(expired,31))
        self.assertIsNone(expired['presentation_price'])
        self.assertFalse(expired['presentation_held'])

    def test_changed_page_invalidates_a_previously_returned_presentation(self):
        held=self.memory.observe(self.covered(),self.image,1)[0]
        changed=deepcopy(self.shop);changed['rows'][0]['price']['mesos']=200
        self.memory.observe(changed,self.image,2)
        self.assertIsNone(self.memory.presentation_for(held,2))
        current=self.memory.observe(self.covered(),self.image,3)[0]
        self.assertEqual(self.memory.presentation_for(current,3)['mesos'],200)

    def test_held_deal_cannot_be_rerated_by_a_new_market_quote(self):
        visible=self.memory.observe(self.shop,self.image,1)[0]
        first_quote=(1000,100,20);new_quote=(2000,101,21)
        self.memory.presentation_for(visible,1,quote_key=first_quote)
        held=self.memory.observe(self.covered(),self.image,2)[0]
        self.assertEqual(self.memory.presentation_for(held,2,quote_key=first_quote)['mesos'],100)
        self.assertIsNone(self.memory.presentation_for(held,2,quote_key=new_quote))
        # Only newly verified row pixels/OCR may establish the new comparison.
        visible=self.memory.observe(self.shop,self.image,3)[0]
        self.memory.presentation_for(visible,3,quote_key=new_quote)
        held=self.memory.observe(self.covered(),self.image,4)[0]
        self.assertEqual(self.memory.presentation_for(held,4,quote_key=new_quote)['mesos'],100)

    def test_unsafe_guard_invalidates_held_presentation_even_without_another_read(self):
        held=self.memory.observe(self.covered(),self.image,1)[0]
        self.image.setPixelColor(363,160,QColor('white'))
        self.memory.observe(self.covered(),self.image,2)
        self.assertIsNone(self.memory.presentation_for(held,2))

    def test_slot_and_page_identity_survive_ocr_order_changes_and_shop_drag(self):
        shop=deepcopy(self.shop);other=deepcopy(self.row)
        other['name']='Other Hat';other['area']['y']+=50;shop['rows'].append(other)
        original=self.memory.observe(shop,self.image,1)
        keys={r['name']:(r['shop_page'],r['shop_slot']) for r in original}
        moved=deepcopy(shop);moved['area']['x']+=30;moved['area']['y']+=20
        for row in moved['rows']:row['area']['x']+=30;row['area']['y']+=20
        moved['rows'].reverse()
        latest=self.memory.observe(moved,self.image,2)
        self.assertEqual(keys,{r['name']:(r['shop_page'],r['shop_slot']) for r in latest})

    def test_reset_ends_the_page_identity_even_for_the_same_item(self):
        row=self.memory.observe(self.shop,self.image,1)[0]
        self.memory.reset()
        self.assertIsNone(self.memory.presentation_for(row,2))
        new=self.memory.observe(self.shop,self.image,2)[0]
        self.assertNotEqual(row['shop_page'],new['shop_page'])

    def test_slot_recovery_cache_is_bounded_even_with_unstable_geometry(self):
        for index in range(self.memory.ROW_LIMIT+8):
            noisy=deepcopy(self.shop)
            noisy['rows'][0]['area']['y']=170+index*5
            self.memory.observe(noisy,self.image,index+1)
        self.assertLessEqual(len(self.memory.rows),self.memory.ROW_LIMIT)
        self.assertTrue(set(self.memory.row_pixels)<=set(self.memory.rows))
        self.assertTrue(set(self.memory.quote_proofs)<=set(self.memory.rows))

    def test_watch_page_revision_changes_for_another_listing_but_not_occlusion_or_drag(self):
        initial=self.memory.page_revision
        self.memory.observe(self.covered(),self.image,1)
        self.assertEqual(self.memory.page_revision,initial)
        moved=deepcopy(self.shop)
        moved['area']['x']+=30;moved['rows'][0]['area']['x']+=30
        self.memory.observe(moved,self.image,2)
        self.assertEqual(self.memory.page_revision,initial)
        changed=deepcopy(moved);changed['rows'][0]['name']='Another item'
        self.memory.observe(changed,self.image,3)
        self.assertGreater(self.memory.page_revision,initial)

    def test_long_occlusion_keeps_reference_identity_without_a_deal_rating(self):
        result=self.memory.observe(self.covered(),self.image,4)[0]
        self.assertEqual(result["name"],"Work Gloves")
        self.assertIsNone(result["price"])
        self.assertTrue(result["listing_old"])

    def test_unreadable_selected_name_keeps_reference_with_no_assumed_listing(self):
        selected=deepcopy(self.shop);selected['rows'][0].update(name=None,price=None,covered=False)
        row=self.memory.observe(selected,self.image,1)[0]
        self.assertEqual(row['name'],'Work Gloves');self.assertFalse(row['covered'])
        self.assertIsNone(row['price']);self.assertTrue(row['reference_only'])

    def test_listing_returns_without_ocr_only_when_the_exact_visible_pixels_return(self):
        rows=self.memory.observe(self.covered(),self.image,1)
        changed=self.image.copy();changed.setPixelColor(180,180,QColor('white'))
        self.assertIsNone(self.memory.restore_visible(changed,rows)[0]['price'])
        restored=self.memory.restore_visible(self.image,rows)[0]
        self.assertEqual(restored['price']['mesos'],100)
        self.assertFalse(restored.get('covered'))

    def test_changed_scrollbar_invalidates_covered_rows(self):
        self.image.setPixelColor(363,160,QColor("white"))
        result=self.memory.observe(self.covered(),self.image,1)[0]
        self.assertIsNone(result["name"])

    def test_store_movement_and_close_clear_old_coordinates(self):
        moved=self.covered();moved["area"]["x"]+=20
        self.assertIsNone(self.memory.observe(moved,self.image,1)[0]["name"])
        self.image.fill(QColor("black"))
        self.assertEqual(self.memory.observe(None,self.image,2),[])
        self.assertFalse(self.memory.active)

    def test_verified_shop_pixels_suppress_inventory_even_when_list_is_occluded(self):
        rows=self.memory.observe(None,self.image,1)
        self.assertTrue(self.memory.active)
        self.assertEqual(rows[0]["name"],"Work Gloves")
        self.image.fill(QColor("black"))
        self.assertEqual(self.memory.observe(None,self.image,2),[])
        self.assertFalse(self.memory.active)

    def test_changed_visible_listing_invalidates_hidden_page_rows(self):
        other=deepcopy(self.row);other["area"]["y"]+=50;other["name"]="Other Hat"
        self.shop["rows"].append(other);self.memory.observe(self.shop,self.image,1)
        changed=self.covered();changed["rows"][1]["name"]="New page"
        self.assertIsNone(self.memory.observe(changed,self.image,2)[0]["name"])

    def test_small_row_geometry_noise_keeps_the_same_anchor(self):
        for delta in (1,-1,2,-2):
            noisy=deepcopy(self.shop)
            noisy['area']['y']+=delta
            noisy['rows'][0]['area']['y']+=delta
            result=self.memory.observe(noisy,self.image,1)[0]
            self.assertEqual(result['area'],self.row['area'])

    def test_guard_occlusion_does_not_destroy_recovery_data(self):
        original=self.image.copy()
        self.image.setPixelColor(363,160,QColor('white'))
        self.assertIsNone(self.memory.observe(self.covered(),self.image,1)[0]['name'])
        result=self.memory.observe(self.covered(),original,2)[0]
        self.assertEqual(result['name'],'Work Gloves')
        self.assertIsNone(result['price'])
        visible=self.memory.observe(self.shop,original,3)[0]
        self.assertEqual(visible['price']['mesos'],100)

    def test_native_tooltip_can_keep_a_hidden_reference_but_never_an_assumed_deal(self):
        tip=QRect(200,150,220,300)
        self.image.setPixelColor(363,160,QColor('white'))
        row=self.memory.observe(self.covered(),self.image,10,tooltip=tip)[0]
        self.assertTrue(row['reference_only']);self.assertTrue(row['covered'])
        self.assertEqual(row['name'],'Work Gloves');self.assertIsNone(row['price'])
        self.assertEqual(row['area'],self.row['area'])

    def test_guard_changed_outside_tooltip_cannot_reuse_a_hidden_reference(self):
        self.image.setPixelColor(110,146,QColor('white'))
        row=self.memory.observe(self.covered(),self.image,10,tooltip=QRect(200,150,220,300))[0]
        self.assertFalse(row.get('reference_only'));self.assertIsNone(row['name'])

    def test_partial_guard_overlap_does_not_excuse_changes_outside_tooltip(self):
        # This tooltip overlaps the right guard only below y=250. Its upper
        # scrollbar change still proves that the old page cannot be held.
        self.image.setPixelColor(363,160,QColor('white'))
        row=self.memory.observe(self.covered(),self.image,1,tooltip=QRect(200,250,220,200))[0]
        self.assertIsNone(row['name']);self.assertIsNone(row['presentation_price'])

    def test_fully_hidden_guards_do_not_prove_a_page(self):
        self.image.fill(QColor('black'))
        row=self.memory.observe(self.covered(),self.image,1,tooltip=QRect(0,0,800,800))[0]
        self.assertIsNone(row['name']);self.assertIsNone(row['presentation_price'])

    def test_animated_owner_portrait_is_not_a_page_guard(self):
        self.image.setPixelColor(110,120,QColor('white'))
        self.assertEqual(self.memory.observe(self.covered(),self.image,1)[0]['name'],'Work Gloves')

    def test_own_overlay_pixels_do_not_invalidate_a_page_but_visible_scrollbar_changes_do(self):
        mask=QRect(360,170,230,36)
        original=self.image.copy();painter=QPainter(self.image);painter.fillRect(mask,QColor('white'));painter.end()
        self.assertEqual(self.memory.observe(self.covered(),self.image,1,exclude=[mask])[0]['name'],'Work Gloves')
        self.memory.observe(self.shop,self.image,2,exclude=[mask])
        self.assertEqual(self.memory.observe(self.covered(),original,3)[0]['name'],'Work Gloves')
        original.setPixelColor(363,160,QColor('white'))
        self.assertIsNone(self.memory.observe(self.covered(),original,4)[0]['name'])

    def test_small_ocr_punctuation_changes_do_not_invalidate_other_covered_rows(self):
        shop=deepcopy(self.shop);other=deepcopy(self.row);other['area']['y']+=50;shop['rows'].append(other)
        shop['rows'][0]['name']='Overall Armor LUK Scroll:...';shop['rows'][0]['tier']='greater'
        self.memory.observe(shop,self.image,1)
        changed=deepcopy(shop);changed['rows'][0]['name']='Overall Armor LUK Soroll....'
        changed['rows'][1].update(name=None,price=None,covered=True)
        self.assertEqual(self.memory.observe(changed,self.image,2)[1]['name'],'Work Gloves')
