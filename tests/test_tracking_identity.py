"""Visual character binding must survive OCR spelling changes without merging people."""
import json
from pathlib import Path
import subprocess
import unittest

from PySide6.QtCore import QPoint
from PySide6.QtGui import QImage
from price_lens.platform_paths import reader_binary
from price_lens.tracking_identity import TrackingIdentity,name_proof,proof_pixels,same_name_pixels,WIDTH,HEIGHT

ROOT=Path(__file__).resolve().parents[1]


def proof(alternative=False):
    mask=bytearray(WIDTH*HEIGHT)
    for x in (3,12,21):
        for y in range(3,17):mask[y*WIDTH+x]=255
    for y in range(3,17):
        x=31+(y-3 if alternative else (16-y))//3
        mask[y*WIDTH+x]=255
    return {'version':1,'mask':bytes(mask).hex()}


class TrackingIdentityTests(unittest.TestCase):
    def test_ocr_variants_of_identical_pixels_keep_one_character(self):
        identity=TrackingIdentity();first=identity.prepare({'character':'achZ','nameProof':proof()});identity.accept(first)
        for name in ('ach2','achZ','','ach2'):
            value=identity.prepare({'character':name,'nameProof':proof()})
            self.assertEqual(value['identityKey'],first['identityKey']);self.assertEqual(value['character'],'achZ')

    def test_visually_different_names_are_not_aliases_even_when_ocr_text_matches(self):
        identity=TrackingIdentity();first=identity.prepare({'character':'ach2','nameProof':proof()});identity.accept(first)
        other=identity.prepare({'character':'ach2','nameProof':proof(True)})
        self.assertNotEqual(other['identityKey'],first['identityKey'])
        self.assertEqual(identity.reference.key,first['identityKey'])
        identity.accept(other);self.assertEqual(identity.reference.key,other['identityKey'])

    def test_missing_or_malformed_pixels_cannot_claim_a_known_character(self):
        identity=TrackingIdentity();first=identity.prepare({'character':'Player','nameProof':proof()});identity.accept(first)
        for bad in (None,{}, {'version':1,'mask':'f'*999999},{'version':1,'mask':'zz'*(WIDTH*HEIGHT)}):
            value=identity.prepare({'character':'Player','nameProof':bad})
            self.assertEqual(value['character'],'');self.assertNotIn('identityKey',value)
        self.assertFalse(same_name_pixels(None,None))

    def test_public_status_strip_proof_is_position_and_brightness_independent(self):
        binary=reader_binary(ROOT)
        if not binary.exists():self.skipTest('Build the reader first')
        path=ROOT/'vendor/minerva/samples/exp-bar/100300__64.49--ideal-ratio-1366x768-strip.png'
        result=subprocess.run([str(binary)],input=json.dumps({'path':str(path),'experience_only':True})+'\n',text=True,capture_output=True,check=True,timeout=15)
        area=json.loads(result.stdout)['experience']['area'];image=QImage(str(path))
        original=name_proof(image,area,QPoint());self.assertIsNotNone(proof_pixels(original))
        shifted={**area,'x':area['x']+100,'y':area['y']+200}
        self.assertEqual(original,name_proof(image,shifted,QPoint(100,200)))
        dim=image.convertToFormat(QImage.Format.Format_RGBA8888);pixels=bytearray(dim.constBits())
        for i in range(0,len(pixels),4):
            for c in range(3):pixels[i+c]=round(pixels[i+c]*.75)
        dim=QImage(bytes(pixels),dim.width(),dim.height(),QImage.Format.Format_RGBA8888).copy()
        darker=name_proof(dim,area,QPoint());self.assertTrue(same_name_pixels(proof_pixels(original),proof_pixels(darker)))

    def test_known_character_survives_verified_public_ui_scale_changes(self):
        binary=reader_binary(ROOT)
        if not binary.exists():self.skipTest('Build the reader first')
        base=ROOT/'vendor/minerva/samples/exp-bar'
        names=('100300__64.49--ideal-ratio-1366x768-strip.png','100300__64.49--ideal-ratio-2560x1440-strip.png',
               '100300__64.49--default-ratio-1920x1080-strip.png','100300__64.49--default-ratio-filter-1920x1080-strip.png')
        paths=[base/name for name in names if (base/name).exists()]
        result=subprocess.run([str(binary)],input=''.join(json.dumps({'path':str(path),'experience_only':True})+'\n' for path in paths),text=True,capture_output=True,check=True,timeout=20)
        identity=TrackingIdentity();key=None
        for path,line in zip(paths,result.stdout.splitlines()):
            payload=json.loads(line)['experience'];payload['nameProof']=name_proof(QImage(str(path)),payload['area'],QPoint())
            prepared=identity.prepare(payload);identity.accept(prepared)
            if key is None:key=prepared['identityKey']
            self.assertEqual(prepared['identityKey'],key);self.assertEqual(prepared['character'],'Egbert')


if __name__=='__main__':unittest.main()
