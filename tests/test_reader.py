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
