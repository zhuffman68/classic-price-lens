"""Game-area tests use public HUD fragments and our own generated desktop pixels."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter

from price_lens.platform_paths import reader_binary

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures"


def game_frame(x=120, y=90, width=960, height=600, scale=1.0, desktop=(1600, 900), anchors=True, minimap_offset=(0,0), minimap=True):
    image = QImage(*desktop, QImage.Format.Format_RGBA8888)
    image.fill(QColor("#37302b"))
    painter = QPainter(image)
    painter.fillRect(x, y, width, height, QColor("#917c6c"))
    if anchors:
        header = QImage(str(FIXTURES / "area-minimap.png"))
        header = header.scaled(round(228*scale), round(69*scale), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        if minimap:
            painter.drawImage(x-round(3*scale)+minimap_offset[0], y+round(24*scale)-round(3*scale)+minimap_offset[1], header)
        bar_width=round(800*scale)
        lvx=x+(width-bar_width)//2+round(scale)
        lvy=y+height-round(38*scale)
        edge=QImage(str(FIXTURES / "area-footer-edge.png"))
        edge=edge.scaled(bar_width,round(10*scale),Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.SmoothTransformation)
        painter.drawImage(lvx-round(scale), lvy-round(6*scale), edge)
        level=QImage(str(FIXTURES / "area-level-box.png"))
        level=level.scaled(round(76*scale),round(37*scale),Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.SmoothTransformation)
        painter.drawImage(lvx,lvy,level)
        painter.fillRect(x,y,width,round(24*scale),QColor("#28303b"))
    painter.end()
    return image


class GameAreaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary=reader_binary(ROOT)
        if not cls.binary.is_file():
            raise unittest.SkipTest("Build or install the pixel reader first")

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.process=subprocess.Popen([str(self.binary)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)

    def tearDown(self):
        self.process.stdin.close()
        self.process.wait(timeout=10)
        self.process.stdout.close()
        self.process.stderr.close()
        self.temp.cleanup()

    def read(self,image,**options):
        path=Path(self.temp.name)/"frame.png"
        self.assertTrue(image.save(str(path)))
        request={"path":str(path),"auto_game":True,"locate_only":True,**options}
        self.process.stdin.write(json.dumps(request)+"\n")
        self.process.stdin.flush()
        return json.loads(self.process.stdout.readline())

    def assert_area(self,result,x,y,width,height,tolerance=8):
        self.assertIsNotNone(result.get("gameArea"),result)
        area=result["gameArea"]
        for key,value in zip(("x","y","width","height"),(x,y,width,height)):
            self.assertLessEqual(abs(area[key]-value),tolerance,(key,area,value))

    def test_visible_hud_locates_window_and_tracks_movement(self):
        self.assert_area(self.read(game_frame()),120,90,960,600)
        self.assert_area(self.read(game_frame(x=320,y=180)),320,180,960,600)

    def test_ui_scaling_and_resizing(self):
        for scale in (0.8,1.0,1.25,1.5):
            with self.subTest(scale=scale):
                image=game_frame(x=70,y=55,width=1400,height=850,scale=scale,desktop=(1600,1000))
                self.assert_area(self.read(image),70,55,1400,850,tolerance=14)

    def test_missing_or_covered_hud_clears_previous_match(self):
        self.assertIsNotNone(self.read(game_frame())["gameArea"])
        image=game_frame()
        painter=QPainter(image)
        painter.fillRect(110,620,500,80,QColor("#171c25"))
        painter.end()
        self.assertIsNone(self.read(image)["gameArea"])
        self.assertIsNone(self.read(game_frame(anchors=False))["gameArea"])

    def test_repeated_stationary_frame_reuses_small_anchor_checks(self):
        image=game_frame()
        first=self.read(image)
        for _ in range(10):
            result=self.read(image)
            self.assertEqual(result["gameArea"],first["gameArea"])
            self.assertEqual(len(result["gameGuards"]),2)

    def test_tall_description_crossing_footer_keeps_only_verified_window_bounds(self):
        image=game_frame();self.assert_area(self.read(image),120,90,960,600)
        painter=QPainter(image);painter.fillRect(500,580,240,110,QColor('#444477'));painter.end()
        self.assert_area(self.read(image),120,90,960,600)
        # The popup may hide the footer rim, but losing the independent level
        # anchor must still remove the game area immediately.
        painter=QPainter(image);painter.fillRect(195,645,90,45,QColor('#171c25'));painter.end()
        self.assertIsNone(self.read(image)['gameArea'])

    def test_fps_overlay_is_optional_and_never_an_anchor(self):
        # Start with the corner covered, forcing a fresh search with an FPS-like
        # overlay present; then move the game and search again without it.
        image=game_frame()
        painter=QPainter(image)
        painter.fillRect(120,114,100,14,QColor("#111111"))
        for x in range(123,215,7):
            painter.fillRect(x,116,3,8,QColor("#22aa44"))
        painter.end()
        self.assert_area(self.read(image),120,90,960,600)
        self.assert_area(self.read(game_frame(x=320,y=180)),320,180,960,600)

    def test_moving_or_hiding_minimap_does_not_change_bounds(self):
        initial=self.read(game_frame())["gameArea"]
        self.assertIsNotNone(initial)
        moved=self.read(game_frame(minimap_offset=(380,170)))["gameArea"]
        hidden=self.read(game_frame(minimap=False))["gameArea"]
        self.assertEqual(moved,initial)
        self.assertEqual(hidden,initial)

    def test_first_detection_also_works_with_minimap_hidden(self):
        self.assert_area(self.read(game_frame(minimap=False)),120,90,960,600)

    def test_two_visible_games_require_manual_selection(self):
        image=game_frame(x=0,y=0,width=800,height=600,desktop=(1800,800))
        second=game_frame(x=0,y=0,width=800,height=600,desktop=(800,600))
        painter=QPainter(image)
        painter.drawImage(950,100,second)
        painter.end()
        self.assertIsNone(self.read(image)["gameArea"])

    def test_shops_outside_the_game_are_excluded_from_ocr(self):
        image=game_frame()
        shop=QImage(str(ROOT/"vendor/minerva/samples/player-shop/gems-and-ores.png"))
        painter=QPainter(image)
        painter.drawImage(1120,140,shop)
        painter.end()
        outside=self.read(image,locate_only=False)
        self.assertIsNotNone(outside["gameArea"])
        self.assertIsNone(outside["shop"])
        full=self.read(image,auto_game=False,locate_only=False)
        self.assertIsNotNone(full["shop"],"Control: fixture must be a readable shop without automatic cropping")
