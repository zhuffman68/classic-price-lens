"""Small pixel proofs for a description's inventory source, without capture."""
from copy import deepcopy
import unittest

from PySide6.QtCore import QRect
from PySide6.QtGui import QColor,QImage

from price_lens.tooltip_association import TooltipAssociation,association_state


class TooltipAssociationTests(unittest.TestCase):
    def setUp(self):
        self.image=QImage(800,600,QImage.Format.Format_RGBA8888)
        self.image.fill(QColor('#24384b'))
        self.found={'area':dict(x=58,y=111,width=180,height=12)}
        self.value={'state':'inventory-primary','token':'source:tab:slot',
                    'source':dict(x=300,y=150,width=230,height=300),
                    'slot':dict(x=324,y=174,width=36,height=36),
                    'panel':dict(x=50,y=100,width=240,height=330),
                    'guards':[dict(x=300,y=150,width=230,height=20),
                              dict(x=50,y=100,width=240,height=2)]}

    def proof(self):
        return TooltipAssociation.read(self.value,self.found,self.image)

    def test_only_explicit_primary_metadata_extends_the_normal_path(self):
        self.assertEqual(association_state(None),'normal')
        self.assertEqual(association_state({'state':'normal'}),'normal')
        for value in ({},{'state':'rejected'},{'state':'future'},[],False):
            self.assertEqual(association_state(value),'rejected')
        self.assertIsNotNone(self.proof())
        self.assertTrue(self.proof().matches(self.image,(340,190)))

    def test_small_pointer_move_to_another_cell_invalidates_the_binding(self):
        proof=self.proof()
        self.assertTrue(proof.matches(self.image,(350,200)))
        self.assertFalse(proof.matches(self.image,(376,190)))
        for point in (None,(340,),('340',190),(True,190)):
            self.assertFalse(proof.contains_pointer(point))

    def test_name_header_and_panel_guards_expire_independently(self):
        proof=self.proof()
        for point in ((60,112),(301,151),(51,100)):
            with self.subTest(point=point):
                changed=self.image.copy();changed.setPixelColor(*point,QColor('red'))
                self.assertFalse(proof.matches(changed,(340,190)))
        changed=self.image.copy();changed.setPixelColor(740,500,QColor('red'))
        self.assertTrue(proof.matches(changed,(340,190)))

    def test_incomplete_out_of_bounds_or_unbounded_proofs_fail_closed(self):
        mutations=[('token',''),('token','x'*513),('guards',[]),('guards',[{}]*13),
                   ('guards',[dict(x=0,y=0,width=800,height=600)]),
                   ('source',dict(x=300,y=150,width=20,height=20)),
                   ('slot',dict(x=324,y=174,width=True,height=36)),
                   ('panel',dict(x=50,y=100,width=40,height=40)),
                   ('guards',[dict(x=-1,y=0,width=10,height=10)]),
                   ('guards',[dict(x=0,y=0,width=0,height=10)])]
        for key,value in mutations:
            with self.subTest(key=key,value=value):
                metadata=deepcopy(self.value);metadata[key]=value
                self.assertIsNone(TooltipAssociation.read(metadata,self.found,self.image))
        self.assertIsNone(TooltipAssociation.read(self.value,None,self.image))
        self.assertIsNone(TooltipAssociation.read(self.value,self.found,QImage()))

    def test_scaled_translated_pixels_and_tokens_remain_in_one_coordinate_space(self):
        image=QImage(1700,1300,QImage.Format.Format_RGBA8888);image.fill(QColor('navy'))
        def transform(rect):
            return dict(x=rect['x']*2+30,y=rect['y']*2+40,
                        width=rect['width']*2,height=rect['height']*2)
        value={**self.value,'token':'origin30,40:scale2',
               **{key:transform(self.value[key]) for key in ('source','slot','panel')},
               'guards':[transform(rect) for rect in self.value['guards']]}
        proof=TooltipAssociation.read(value,{'area':transform(self.found['area'])},image)
        self.assertIsNotNone(proof)
        self.assertEqual(proof.token,'origin30,40:scale2')
        self.assertEqual(proof.slot,QRect(678,388,72,72))
        self.assertTrue(proof.matches(image,(710,420)))
        self.assertFalse(proof.matches(image,(340,190)))


if __name__=='__main__':unittest.main()
