"""Real bundled OCR, with upstream's public, cropped player-shop fixtures."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from price_lens.platform_paths import reader_binary

ROOT = Path(__file__).resolve().parents[1]
BINARY = reader_binary(ROOT)


@unittest.skipUnless(BINARY.exists(), "Build the screen reader with ./setup.sh first")
class ShopReaderTests(unittest.TestCase):
    def read(self, name):
        path = ROOT / "vendor/minerva/samples/player-shop" / (name + ".png")
        result = subprocess.run([str(BINARY)], input=json.dumps({"path": str(path), "at_ms": 123, "pointer": None}) + "\n",
                                text=True, capture_output=True, timeout=20, env={**os.environ, "RAYON_NUM_THREADS": "2"}, check=True)
        data = json.loads(result.stdout)
        self.assertNotIn("error", data)
        return data["shop"]["rows"]

    def test_gem_and_ore_names_bundle_quantities_and_prices(self):
        rows = self.read("gems-and-ores")
        expected = json.loads((ROOT / "vendor/minerva/samples/player-shop/gems-and-ores.json").read_text())
        actual = [{"name": r["name"], **r["price"]} for r in rows]
        self.assertEqual(actual, expected)

    def test_scroll_icon_tiers_disambiguate_cut_off_names(self):
        rows = self.read("live-greater-chaos-and-intermediate-scrolls")
        self.assertEqual(rows[1]["tier"], "chaos")
        self.assertEqual(rows[2]["tier"], "intermediate")
        self.assertEqual(rows[1]["price"], {"mesos": 99000, "quantity": 1})

    def test_sold_out_rows_do_not_become_active_listings(self):
        name = "equips-two-sold-out"
        rows = self.read(name)
        expected = json.loads((ROOT / "vendor/minerva/samples/player-shop" / (name + ".json")).read_text())
        self.assertEqual([{ "name": r["name"], **r["price"] } for r in rows], expected)

    def selected_image(self,rows,index,tint=(231,153,41),price_from=None):
        from PySide6.QtCore import QPoint,QRect
        from PySide6.QtGui import QImage,QColor,QPainter
        image=QImage(str(ROOT/'vendor/minerva/samples/player-shop/gems-and-ores.png'))
        area=rows[index]['area'];x,y,w,h=(area[k] for k in ('x','y','width','height'))
        if price_from is not None:
            other=rows[price_from]['area'];patch=image.copy(QRect(other['x'],other['y']+27,w,h-27))
            painter=QPainter(image);painter.drawImage(QPoint(x,y+27),patch);painter.end()
        blue=(202,213,223)
        # Render the same public glyphs on the game's darker selected palette,
        # preserving each text pixel's coverage and its light separator rule.
        for yy in range(y,y+h):
            for xx in range(x,x+w):
                p=image.pixelColor(xx,yy).getRgb()[:3]
                if p==(222,223,223):colour=(247,192,110)
                else:
                    k=sum(p[i]*blue[i] for i in range(3))/sum(c*c for c in blue)
                    if not (k<=1.08 and all(abs(p[i]-blue[i]*k)<=14 for i in range(3))):continue
                    colour=tuple(min(255,max(0,round(v*k))) for v in tint)
                image.setPixelColor(xx,yy,QColor(*colour))
        return image

    def test_dark_selected_rows_are_read_cold_in_first_middle_and_last_slots(self):
        rows=self.read('gems-and-ores');expected=[(r['name'],r['price']) for r in rows]
        with tempfile.TemporaryDirectory() as directory:
            for index,tint in ((0,(231,153,41)),(2,(221,145,38)),(len(rows)-1,(235,157,43))):
                with self.subTest(index=index,tint=tint):
                    path=Path(directory)/'selected.png';self.selected_image(rows,index,tint).save(str(path))
                    result=subprocess.run([str(BINARY)],input=json.dumps({'path':str(path)})+'\n',text=True,
                        capture_output=True,check=True,timeout=20,env={**os.environ,'RAYON_NUM_THREADS':'2'})
                    actual=json.loads(result.stdout)['shop']['rows']
                    self.assertEqual([(r['name'],r['price']) for r in actual],expected)

    def test_selected_cache_reads_changed_amounts_and_never_fills_a_covered_price(self):
        from PySide6.QtGui import QPainter,QColor
        rows=self.read('gems-and-ores');index=2;area=rows[index]['area']
        first=self.selected_image(rows,index)
        changed=self.selected_image(rows,index,price_from=len(rows)-1)
        covered=changed.copy();painter=QPainter(covered)
        painter.fillRect(area['x']+70,area['y']+34,12,12,QColor('#442255'));painter.end()
        with tempfile.TemporaryDirectory() as directory:
            requests=[]
            for n,image in enumerate((first,changed,covered)):
                path=Path(directory)/f'selected-{n}.png';image.save(str(path));requests.append(json.dumps({'path':str(path)}))
            result=subprocess.run([str(BINARY)],input='\n'.join(requests)+'\n',text=True,capture_output=True,
                check=True,timeout=20,env={**os.environ,'RAYON_NUM_THREADS':'2'})
        readings=[json.loads(line)['shop']['rows'] for line in result.stdout.splitlines()]
        selected=lambda data:[r for r in data if abs(r['area']['y']-area['y'])<5]
        self.assertEqual(selected(readings[0])[0]['price'],rows[index]['price'])
        self.assertEqual(selected(readings[1])[0]['price'],rows[-1]['price'])
        self.assertTrue(all(r.get('price') is None for r in selected(readings[2])))

    def test_fast_rgba_input_matches_the_png_reader(self):
        from PySide6.QtGui import QImage
        path = ROOT / "vendor/minerva/samples/player-shop/gems-and-ores.png"
        image = QImage(str(path)).convertToFormat(QImage.Format.Format_RGBA8888)
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory) / "frame.rgba"
            raw.write_bytes(image.constBits())
            request = {"path": str(raw), "width": image.width(), "height": image.height(), "at_ms": 123, "pointer": None}
            result = subprocess.run([str(BINARY)], input=json.dumps(request) + "\n", text=True, capture_output=True,
                                    timeout=20, env={**os.environ, "RAYON_NUM_THREADS": "2"}, check=True)
        actual = json.loads(result.stdout)
        self.assertEqual(actual["shop"]["rows"], self.read("gems-and-ores"))

    def test_incomplete_raw_frame_has_no_shop_reading(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory) / "frame.rgba"
            raw.write_bytes(b"\0" * 12)
            request = {"path": str(raw), "width": 8, "height": 8, "at_ms": 123, "pointer": None}
            result = subprocess.run([str(BINARY)], input=json.dumps(request) + "\n", text=True, capture_output=True,
                                    timeout=20, check=True)
        self.assertIn("length does not match", json.loads(result.stdout)["error"])

    def test_tooltip_name_is_read_only_when_requested(self):
        path = ROOT / "vendor/minerva/samples/item-tooltip/screw@60,20.png"
        request = {"path": str(path), "at_ms": 123, "pointer": {"x": 60, "y": 20}}
        off = subprocess.run([str(BINARY)], input=json.dumps(request) + "\n", text=True, capture_output=True, timeout=20, check=True)
        self.assertNotIn("tooltip", json.loads(off.stdout))
        request["tooltip"] = True
        on = subprocess.run([str(BINARY)], input=json.dumps(request) + "\n", text=True, capture_output=True,
                            timeout=20, env={**os.environ, "RAYON_NUM_THREADS": "2"}, check=True)
        self.assertEqual(json.loads(on.stdout)["tooltip"]["found"]["name"], "Screw")

    def test_open_item_description_far_from_pointer_uses_pixels_only(self):
        from PySide6.QtGui import QImage,QPainter,QColor
        image=QImage(1600,900,QImage.Format.Format_RGBA8888);image.fill(QColor('#eeeeee'))
        painter=QPainter(image)
        painter.drawImage(1150,160,QImage(str(ROOT/'vendor/minerva/samples/item-tooltip/screw@60,20.png')))
        painter.end()
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'popup.png';image.save(str(path))
            request={'path':str(path),'at_ms':123,'pointer':{'x':20,'y':800},'tooltip':True}
            result=subprocess.run([str(BINARY)],input=json.dumps(request)+'\n',text=True,capture_output=True,timeout=20,check=True)
        found=json.loads(result.stdout)['tooltip']['found']
        self.assertEqual(found['name'],'Screw');self.assertTrue(found['pinned'])

    def test_small_shop_capture_keeps_desktop_coordinates(self):
        path = ROOT / "vendor/minerva/samples/player-shop/gems-and-ores.png"
        request = {"path": str(path), "at_ms": 123, "pointer": None, "origin": {"x": 140, "y": 80}}
        result = subprocess.run([str(BINARY)], input=json.dumps(request) + "\n", text=True, capture_output=True,
                                timeout=20, env={**os.environ, "RAYON_NUM_THREADS": "2"}, check=True)
        shifted = json.loads(result.stdout)["shop"]["rows"]
        original = self.read("gems-and-ores")
        for row, before in zip(shifted, original, strict=True):
            self.assertEqual(row["name"], before["name"])
            self.assertEqual(row["price"], before["price"])
            self.assertEqual(row["area"]["x"], before["area"]["x"] + 140)
            self.assertEqual(row["area"]["y"], before["area"]["y"] + 80)


if __name__ == "__main__":
    unittest.main()
