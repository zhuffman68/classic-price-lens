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
