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

    def read_images(self, images):
        binary=reader_binary(ROOT)
        if not binary.exists():self.skipTest('Build the native reader first')
        with tempfile.TemporaryDirectory() as folder:
            requests=[]
            for index,image in enumerate(images):
                path=Path(folder)/f'capture-{index}.png';image.save(str(path))
                requests.append({'path':str(path),'pickups_only':True,'at_ms':1000+index*200})
            result=subprocess.run([str(binary)],input=''.join(json.dumps(row)+'\n' for row in requests),
                text=True,capture_output=True,check=True,timeout=30,env={**os.environ,'RAYON_NUM_THREADS':'1'})
        return [json.loads(line)['pickups'] for line in result.stdout.splitlines()]

    @staticmethod
    def outlined(lines, *, brightness='#eeeeee', offset=0, height=240):
        image=QImage(600,height,QImage.Format.Format_RGBA8888);image.fill(QColor('#080808'))
        painter=QPainter(image);font=QFont('Arial');font.setPixelSize(14)
        font.setStyleStrategy(QFont.StyleStrategy.NoAntialias);painter.setFont(font)
        for index,text in enumerate(lines):
            y=25+offset+index*18
            x=580-painter.fontMetrics().horizontalAdvance(text)
            for dx,dy in ((-1,0),(1,0),(0,-1),(0,1)):
                painter.setPen(QColor('#000000'));painter.drawText(x+dx,y+dy,text)
            painter.setPen(QColor(brightness));painter.drawText(x,y,text)
        painter.end();return image

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
        self.assertEqual(first['pickups']['state'],'readable')
        self.assertTrue(all(row['kind']=='meso' and row['visualKey'] for row in first['pickups']['lines']))
        self.assertEqual(len({row['rect']['y'] for row in first['pickups']['lines']}),3)

    def test_classic_exp_party_and_item_receipts_anchor_without_currency(self):
        result=self.read_images([self.outlined([
            'You received EXP (+23)',
            'Bonus EXP for PARTY (+2)',
            'Green Mushroom x1 earned. (Etc)',
            'You have gained mesos (+29)',
        ])])[0]
        self.assertEqual([row['kind'] for row in result['lines']],['exp','party_exp','item','meso'])
        self.assertEqual([row['mesos'] for row in result['lines']],[None,None,None,29])
        self.assertEqual(result['state'],'readable')

    def test_fading_and_line_movement_preserve_verified_name_and_visual_key(self):
        bright,faded=self.read_images([
            self.outlined(['You have gained mesos (+29)']),
            self.outlined(['You have gained mesos (+29)'],brightness='#555555',offset=20),
        ])
        self.assertEqual([row['mesos'] for row in faded['lines']],[29])
        self.assertEqual(bright['lines'][0]['visualKey'],faded['lines'][0]['visualKey'])
        self.assertEqual(faded['lines'][0]['rect']['y']-bright['lines'][0]['rect']['y'],20)

    def test_empty_and_unreadable_are_distinct_and_neither_adds_currency(self):
        blank,unknown=self.read_images([self.outlined([]),self.outlined(['Your inventory is full'])])
        self.assertEqual(blank['state'],'empty');self.assertFalse(blank['partial'])
        self.assertEqual(unknown['state'],'unreadable');self.assertTrue(unknown['partial'])
        self.assertEqual(blank['lines'],[])
        self.assertTrue(unknown['lines'])
        self.assertTrue(all(row['kind']=='unknown' and row['mesos'] is None and row['visualKey']
            for row in unknown['lines']))

    def test_budget_exhaustion_keeps_previously_verified_rows(self):
        result=self.read_images([self.outlined(['You have gained mesos (+29)']+
            [f'An unclassified system notice number {index}' for index in range(15)],height=320)])[0]
        self.assertEqual([row['mesos'] for row in result['lines'] if row['mesos'] is not None],[29])
        self.assertEqual(result['state'],'readable');self.assertTrue(result['partial'])

    def test_chat_prefix_and_invalid_amounts_never_become_currency(self):
        messages=['Player: You have gained mesos (+29)',
            'You have gained mesos (+2.5m)','You have gained mesos (+2,50)',
            'You have gained mesos (-29)']
        for text,result in zip(messages,self.read_images([self.outlined([text]) for text in messages])):
            self.assertFalse(any(row['mesos'] is not None for row in result['lines']),text)
