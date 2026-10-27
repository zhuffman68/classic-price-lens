"""Real OCR on public Classic UI fixtures; no OS capture or game interaction."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter

from price_lens.platform_paths import reader_binary

ROOT = Path(__file__).resolve().parents[1]


class ExperienceReaderTests(unittest.TestCase):
    def setUp(self):
        self.binary = reader_binary(ROOT)
        if not self.binary.exists():
            self.skipTest("Build the reader first")

    def read(self, requests):
        result = subprocess.run([str(self.binary)],input="".join(json.dumps(r)+"\n" for r in requests),
                                text=True,capture_output=True,check=True,timeout=25,
                                env={**os.environ,"RAYON_NUM_THREADS":"2"})
        return [json.loads(line) for line in result.stdout.splitlines()]

    def test_status_strip_reads_raw_exp_percentage_level_and_character_at_ui_sizes(self):
        names = ["100300__64.49--ideal-ratio-1366x768-strip",
                 "100300__64.49--default-ratio-1920x1080-strip",
                 "100300__64.49--ideal-ratio-2560x1440-strip"]
        for name in names:
            path = ROOT/"vendor/minerva/samples/exp-bar"/(name+".png")
            if not path.exists():
                continue  # Installers intentionally carry only a small fixture subset.
            with self.subTest(name=name):
                result = self.read([{"path":str(path),"experience_only":True,"at_ms":123}])[0]
                value = result["experience"]
                self.assertEqual(value["bar"],{"exp":100300,"percentHundredths":6449})
                self.assertEqual(value["level"],34)
                self.assertEqual(value["character"],"Egbert")
                self.assertNotIn("shop",result)
                self.assertEqual(result["atMs"],123)

    def test_unchanged_strip_uses_cached_reading_and_keeps_new_capture_time(self):
        path = ROOT/"vendor/minerva/samples/exp-bar/100300__64.49--ideal-ratio-1366x768-strip.png"
        requests = [{"path":str(path),"experience_only":True,"at_ms":at} for at in (1000,2000)]
        first, second = self.read(requests)
        self.assertFalse(first["experience"]["cached"])
        self.assertTrue(second["experience"]["cached"])
        self.assertEqual(first["experience"]["bar"],second["experience"]["bar"])
        self.assertEqual(second["atMs"],2000)

    def test_covered_exp_is_unreadable_instead_of_reusing_old_numbers(self):
        path = ROOT/"vendor/minerva/samples/exp-bar/100300__64.49--ideal-ratio-1366x768-strip.png"
        frame = QImage(str(path))
        painter = QPainter(frame)
        painter.fillRect(714,92,145,22,QColor("#171c25"))
        painter.end()
        with tempfile.TemporaryDirectory() as directory:
            covered = Path(directory)/"covered.png"
            self.assertTrue(frame.save(str(covered)))
            first, second = self.read([{"path":str(p),"experience_only":True} for p in (path,covered)])
        self.assertIsNotNone(first["experience"]["bar"])
        self.assertIsNone(second["experience"]["bar"])

    def test_movable_minimap_title_is_separate_from_exp_status_bar(self):
        minimap = ROOT/"vendor/minerva/samples/minimap/victoria-road__kerning-city--window.png"
        if not minimap.exists():
            self.skipTest("Full developer minimap fixtures are not installed")
        frame = QImage(1366,768,QImage.Format.Format_RGBA8888)
        frame.fill(QColor("#373f45"))
        painter = QPainter(frame)
        painter.drawImage(0,640,QImage(str(ROOT/"vendor/minerva/samples/exp-bar/100300__64.49--ideal-ratio-1366x768-strip.png")))
        painter.drawImage(400,90,QImage(str(minimap)).copy(0,27,345,340))
        painter.end()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"public-ui.png"
            self.assertTrue(frame.save(str(path)))
            result = self.read([{"path":str(path),"experience_only":True,"read_map":True}])[0]
        self.assertEqual(result["experience"]["bar"]["exp"],100300)
        self.assertEqual(result["experience"]["map"]["map"],"Kerning City")


if __name__ == "__main__":
    unittest.main()
