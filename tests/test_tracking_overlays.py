"""Real overlay pixels must preserve the independently verified game HUD."""
import json,os,subprocess,tempfile,unittest
from pathlib import Path
from PySide6.QtCore import QRect,Qt,QPoint
from PySide6.QtGui import QImage,QPainter
from PySide6.QtWidgets import QApplication
from price_lens.annotations import AnnotationWindow
from price_lens.overlay_layout import tracking_rows
from price_lens.platform_paths import reader_binary
import test_game_area as fixtures

ROOT=Path(__file__).resolve().parents[1]


def rows():
    return [dict(key='experience',kind='tracking',name='EXP · Character · Lv. 30',text='+1.20%',color='#e4bd7b',clock='01:20',
                 metrics=[('Gained','+1.20%'),('Per minute','+0.90%'),('Per hour','+54.0%')],footer='Level 31 - ETA 1h 20m',basis='Last 5 min',progress='24.10%',status='Rates average the last 5m tracked'),
            dict(key='meso-gain',kind='tracking',name='Meso gained',text='1,200',clock='01:20',color='#b7d4a9',
                 metrics=[('Picked up','1,200'),('Per minute','900'),('Per hour','54,000')],footer='',status='Watching pickup messages')]


class TrackingOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_compact_cards_stack_with_independent_single_card_placement(self):
        window=AnnotationWindow(start_listener=False)
        try:
            for scale in (1,2):
                for supplied in (rows(),rows()[:1],rows()[1:]):
                    placed=tracking_rows(supplied,[120,90,1366,768],[QRect(405*scale,820*scale,36*scale,37*scale)],scale_x=1/scale,scale_y=1/scale)
                    window.read_command(json.dumps(dict(geometry=[0,0,1920,1080],rows=placed,reduce_motion=True)).encode())
                    boxes=[window.label_rect(row,QPoint()) for row in window.rows]
                    self.assertTrue(all(48<=box.height()<=60 and box.left()==124 for box in boxes))
                    self.assertTrue(all(box.right()<405 and box.width()<=273 for box in boxes))
                    self.assertLessEqual(max(box.bottom() for box in boxes)-min(box.top() for box in boxes)+1,122)
                    self.assertEqual(max(box.bottom() for box in boxes),853)
                    if len(boxes)==2:self.assertLess(boxes[0].bottom(),boxes[1].top())
                    self.assertTrue(all(not box.intersects(QRect(405,820,36,37)) for box in boxes))
        finally:window.close();window.deleteLater()

    def test_leaving_both_mode_clears_the_extra_line_in_the_reused_compact_card(self):
        window=AnnotationWindow(start_listener=False)
        try:
            for secondary in ('+1,200 EXP · 900 EXP/min',''):
                supplied=rows()[:1]
                if secondary:supplied[0]['secondary']=secondary
                placed=tracking_rows(supplied,[120,90,1366,768],[QRect(405,820,36,37)])
                window.read_command(json.dumps(dict(geometry=[0,0,1920,1080],rows=placed,reduce_motion=True)))
                self.assertEqual(window.rows[0].get('secondary'),secondary)
                self.assertEqual('1,200' in window.rows[0]['_rolls']['detail'].text,bool(secondary))
                self.assertEqual(window.rows[0]['_rolls']['context'].text,'01:20')
                self.assertLessEqual(window.rows[0]['_height'],60)
                self.assertNotIn('secondary',window.rows[0]['_rolls'])
        finally:window.close();window.deleteLater()

    def test_large_totals_share_a_unit_column_without_overlap(self):
        window=AnnotationWindow(start_listener=False)
        try:
            for count in ('285','9,876,543,210','999,999,999,999,999'):
                supplied=rows();supplied[1]['metrics'][0]=('Picked up',count)
                placed=tracking_rows(supplied,[120,90,1366,768],[QRect(405,820,36,37)])
                window.read_command(json.dumps(dict(geometry=[0,0,1920,1080],rows=placed,reduce_motion=True)))
                columns=[window.tracking_columns(row,window.label_rect(row,QPoint())) for row in window.rows]
                self.assertEqual(columns[0]['gain'].left(),columns[1]['gain'].left())
                self.assertEqual(columns[0]['unit'].center().x(),columns[1]['unit'].center().x())
                for row,parts in zip(window.rows,columns):
                    self.assertLess(parts['gain'].right(),parts['unit'].left())
                    self.assertFalse(parts['unit'].intersects(parts['context']))
                    font,_=window.tracking_gain_style(window.label_rect(row,QPoint()))
                    self.assertGreaterEqual(parts['gain'].height(),font.pixelSize())
                    from PySide6.QtGui import QFontMetrics
                    metrics=QFontMetrics(font);roll=row['_rolls']['gain']
                    width=sum(metrics.horizontalAdvance('0') if key is not None else metrics.horizontalAdvance(char) for key,char in roll.columns)
                    self.assertLessEqual(width,parts['gain'].width())
                    self.assertTrue(window.label_rect(row,QPoint()).contains(parts['unit']))
                self.assertEqual(window.tracking_values(window.rows[1])['detail'],'Visible pickups')
                self.assertEqual(window.tracking_values(window.rows[0])['basis'],'Last 5 min')
                self.assertEqual(window.tracking_values(window.rows[0])['gain'],'+1.20')
            supplied=rows()[1];supplied['metrics'][0]=('Picked up','—')
            self.assertEqual(window.tracking_values(supplied)['unit'],'')
        finally:window.close();window.deleteLater()

    def test_real_painted_cards_no_longer_destroy_window_detection(self):
        binary=reader_binary(ROOT)
        if not binary.exists():self.skipTest('Build the reader first')
        for width,height,scale in ((1366,796,1.0),(960,600,1.0),(1400,850,1.5),(1760,960,2.0)):
            with self.subTest(width=width,scale=scale),tempfile.TemporaryDirectory() as folder:
                frame=fixtures.game_frame(x=70,y=55,width=width,height=height,scale=scale,desktop=(1920,1080))
                clean=Path(folder)/'clean.png';frame.save(str(clean))
                def read(paths):
                    text=''.join(json.dumps(dict(path=str(p),auto_game=True,locate_only=True))+'\n' for p in paths)
                    result=subprocess.run([str(binary)],input=text,text=True,capture_output=True,check=True,timeout=15)
                    return [json.loads(line) for line in result.stdout.splitlines()]
                initial=read([clean])[0];area=initial['gameArea'];self.assertIsNotNone(area)
                bounds=[area[k] for k in ('x','y','width','height')]
                guards=[QRect(*(g[k] for k in ('x','y','width','height'))) for g in initial['gameGuards']]
                old=[dict(row,x=74,y=900,anchor='bottom_left',bounds=bounds,left_offset=i*304,bottom_offset=0,tracking_width=296,tracking_height=132) for i,row in enumerate(rows())]
                new=tracking_rows(rows(),bounds,guards)
                paths=[]
                for name,supplied in (('old',old),('new',new)):
                    overlay=AnnotationWindow(start_listener=False)
                    overlay.read_command(json.dumps(dict(geometry=[0,0,1920,1080],rows=supplied,reduce_motion=True)).encode())
                    pixels=overlay.grab().toImage();image=frame.copy();painter=QPainter(image);painter.drawImage(0,0,pixels);painter.end()
                    path=Path(folder)/(name+'.png');image.save(str(path));paths.append(path)
                    if name=='new':
                        for row in overlay.rows:
                            box=overlay.label_rect(row,QPoint());self.assertTrue(all(not box.intersects(guard) for guard in guards))
                    overlay.close();overlay.deleteLater()
                readings=read([clean,paths[0],clean,*([paths[1]]*4)])
                self.assertIsNone(readings[1]['gameArea'],'Control: the old card must reproduce HUD occlusion')
                for result in readings[2:]:self.assertEqual(result['gameArea'],area)
