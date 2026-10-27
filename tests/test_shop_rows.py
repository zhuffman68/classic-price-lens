from copy import deepcopy
import unittest
from PySide6.QtGui import QColor,QImage
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

    def test_occluded_row_keeps_verified_identity_and_short_lived_listing(self):
        result=self.memory.observe(self.covered(),self.image,1)[0]
        self.assertEqual(result["name"],"Work Gloves")
        self.assertEqual(result["price"]["mesos"],100)
        self.assertTrue(result["retained"])

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
