"""Real OCR of synthetic outlined pickup text; no live game or private frames."""
import json,os,subprocess,tempfile,unittest
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QPainter,QColor,QFont
from price_lens.platform_paths import reader_binary

ROOT=Path(__file__).resolve().parents[1]


class PickupReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_small_outlined_lines_keep_same_amount_as_distinct_rows_and_cache(self):
        binary=reader_binary(ROOT)
        if not binary.exists():self.skipTest('Build the native reader first')
        image=QImage(600,210,QImage.Format.Format_RGBA8888);image.fill(QColor('#373f45'));painter=QPainter(image)
        for y,size in ((45,12),(80,14),(115,16)):
            font=QFont('Arial');font.setPixelSize(size);font.setStyleStrategy(QFont.StyleStrategy.NoAntialias);painter.setFont(font)
            for dx,dy in ((-1,0),(1,0),(0,-1),(0,1)):
                painter.setPen(QColor('#111111'));painter.drawText(240+dx,y+dy,'You have gained mesos (+29)')
            painter.setPen(QColor('#eeeeee'));painter.drawText(240,y,'You have gained mesos (+29)')
        painter.end()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'synthetic.png';image.save(str(path))
            request={'path':str(path),'pickups_only':True}
            result=subprocess.run([str(binary)],input=''.join(json.dumps({**request,'at_ms':n})+'\n' for n in (1000,1200)),
                text=True,capture_output=True,check=True,timeout=20,env={**os.environ,'RAYON_NUM_THREADS':'2'})
        first,second=[json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual([row['mesos'] for row in first['pickups']['lines']],[29,29,29])
        self.assertEqual(first['pickups'],second['pickups']);self.assertEqual(second['atMs'],1200)
        self.assertNotIn('shop',second);self.assertNotIn('experience',second)
