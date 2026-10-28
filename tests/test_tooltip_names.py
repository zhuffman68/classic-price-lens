"""Independent OCR must agree on one catalog ID; no nearest-name guessing."""
import unittest
from PySide6.QtGui import QImage,QColor
from price_lens.domain import Catalog
from price_lens.tooltip_names import TooltipNames,roles_agree
from price_lens.domain import Item


class TooltipNameTests(unittest.TestCase):
    def setUp(self):
        self.catalog=Catalog({'items':[{'id':1,'name':'Leaf Earrings','category':'Equipment'},
            {'id':2,'name':'Old Raggedy Cape','category':'Equipment'},
            {'id':3,'name':'Blue Cape','category':'Equipment'}]})
        self.image=QImage(300,100,QImage.Format.Format_RGBA8888);self.image.fill(QColor('#403b6c'))
        self.image.setPixelColor(40,20,QColor('white'))
        self.found={'area':{'x':20,'y':10,'width':150,'height':14},'name':'Leaf Earrins'}
        self.names=TooltipNames()

    def test_exact_second_read_is_reused_only_with_matching_name_pixels(self):
        corrected=self.names.resolve({**self.found,'alternatives':['Leaf Earrings','Leat Earinte']},self.image,self.catalog)
        self.assertEqual(corrected['name'],'Leaf Earrings')
        self.assertEqual(self.names.resolve(self.found,self.image,self.catalog)['name'],'Leaf Earrings')
        self.image.setPixelColor(45,20,QColor('white'))
        self.assertEqual(self.names.resolve(self.found,self.image,self.catalog)['name'],'Leaf Earrins')

    def test_competing_ids_or_no_exact_read_remain_unknown(self):
        for alternatives in (['Leaf Earrings','Blue Cape'],['Leaf Earring'],['Old Raqqedy Cape']):
            found={**self.found,'alternatives':alternatives}
            self.assertEqual(self.names.resolve(found,self.image,self.catalog)['name'],'Leaf Earrins')

    def test_upgrade_count_is_removed_only_for_a_unique_equipment_name(self):
        found={**self.found,'name':'Leaf Earrings (+3)'}
        resolved=self.names.resolve(found,self.image,self.catalog)
        self.assertEqual(resolved['name'],'Leaf Earrings');self.assertEqual(resolved['raw_name'],found['name'])
        catalog=Catalog({'items':[{'id':1,'name':'Screw','category':'Etc'},
            {'id':2,'name':'Cape','category':'Equipment'},{'id':3,'name':'Cape','category':'Equipment'},
            {'id':4,'name':'Leaf Earrings (+3)','category':'Equipment'}]})
        for name in ('Screw (+3)','Cape (+3)','Leaf Earrings (+3)','Leaf Earrings (M)','Leaf Earrings 10%'):
            self.assertEqual(self.names.resolve({**self.found,'name':name},self.image,catalog)['name'],name)

    def test_second_pass_cannot_change_explicit_stat_tier_color_or_gender(self):
        item=Item(1,'Test',equipment=True,gender='male')
        for before,after in [('Overall DEX Sorol: Greater','Overall LUK Scroll: Greater'),
                             ('Overall DEX Sorol: Greater','Overall DEX Scroll: Lesser'),
                             ('Glove ATK 10%','Glove ATK 60%'),('Red Shlrt','Blue Shirt')]:
            self.assertFalse(roles_agree(before,after,item))
        self.assertFalse(roles_agree('Test Shlrt (F)','Test Shirt',item))
        self.assertTrue(roles_agree('Test Shlrt (M)','Test Shirt',item))
