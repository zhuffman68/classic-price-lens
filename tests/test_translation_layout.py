"""Source-local popup geometry and real offscreen painting, without capture."""
import json
import unittest
from unittest.mock import patch
from PySide6.QtCore import QPoint,QRect,QCoreApplication,QEvent
from PySide6.QtWidgets import QApplication
from price_lens.translation_layout import Box,TranslationLayout,distance
from price_lens.annotations import AnnotationWindow


def message(key,x=120,y=100,*,width=100,height=36,size=(160,80),visible=True):
    return dict(key=key,source=(x,y,width,height),bounds=(0,0,1000,700),size=size,visible=visible)


class TranslationGeometryTests(unittest.TestCase):
    def test_short_card_is_five_pixels_beside_its_source(self):
        supplied=message('a');placement=TranslationLayout().place([supplied],now=0)['a']
        self.assertEqual(placement.side,'right')
        self.assertEqual(placement.rect.x-(supplied['source'][0]+supplied['source'][2]),5)
        self.assertEqual(placement.rect.width,160)

    def test_distinct_crowded_messages_avoid_each_other_and_all_sources(self):
        supplied=[message('a',250,200),message('b',360,200),message('c',400,290,width=140)]
        result=TranslationLayout().place(supplied,now=0)
        for row in supplied:
            rect=result[row['key']].rect
            self.assertTrue(rect.inside(Box(*row['bounds'])))
            self.assertLessEqual(distance(rect,Box(*row['source'])),30)
            for source in supplied:self.assertEqual(rect.overlap(Box(*source['source'])),0)
            for key,other in result.items():
                if key!=row['key']:self.assertEqual(rect.overlap(other.rect),0)

    def test_reordering_and_modest_source_movement_retain_side_and_offset(self):
        layout=TranslationLayout();first=layout.place([message('a'),message('b',600,400)],now=0)
        second=layout.place([message('b',600,400),message('a',123,102)],now=.2)
        self.assertEqual(second['a'].side,first['a'].side)
        self.assertEqual((second['a'].rect.x-first['a'].rect.x,second['a'].rect.y-first['a'].rect.y),(3,2))
        self.assertEqual(second['b'].rect,first['b'].rect)

    def test_clear_nearby_tracking_does_not_repeat_the_candidate_search(self):
        layout=TranslationLayout();layout.place([message('a')],now=0)
        with patch.object(layout,'candidates',side_effect=AssertionError('Unnecessary repacking')):
            result=layout.place([message('a',123,102)],now=.2)['a']
        self.assertEqual(result.rect.x,228)

    def test_unchanged_crowded_geometry_reuses_the_placement_without_repacking(self):
        layout=TranslationLayout();rows=[message('a',250,200),message('b',360,200),message('c',400,290)]
        first=layout.place(rows,now=0)
        with patch.object(layout,'candidates',side_effect=AssertionError('Unchanged frame repacked')):
            second=layout.place(list(reversed(rows)),now=.2)
        self.assertEqual({key:value.rect for key,value in first.items()},{key:value.rect for key,value in second.items()})

    def test_collision_changes_side_but_clearing_it_does_not_flip_back(self):
        layout=TranslationLayout();row=message('a',240,200);first=layout.place([row],now=0)['a']
        obstruction=first.rect.padded(6)
        second=layout.place([row],[obstruction],now=.2)['a']
        self.assertEqual(second.rect.overlap(obstruction),0);self.assertNotEqual(second.rect,first.rect)
        third=layout.place([row],now=.4)['a']
        self.assertEqual(third.side,second.side);self.assertEqual(third.rect,second.rect)

    def test_duplicate_surfaces_are_reserved_and_existing_status_position_is_respected(self):
        layout=TranslationLayout();row=message('a',700,500)
        row['sources']=[row['source'],(100,540,400,24)]
        status=Box(650,530,346,76)
        result=layout.place([row],[status],now=0)['a'].rect
        self.assertEqual(result.overlap(status),0)
        for source in row['sources']:self.assertEqual(result.overlap(Box(*source)),0)

    def test_lost_anchor_freezes_last_confirmed_position_and_scan_interruption_retains_identity(self):
        layout=TranslationLayout();first=layout.place([message('a')],now=0)['a']
        lost=layout.place([message('a',500,400,visible=False)],now=.2)['a']
        self.assertEqual(lost.rect,first.rect);self.assertEqual(lost.source,first.source)
        layout.place([],now=.3)
        returned=layout.place([message('a',124,101)],now=.4)['a']
        self.assertEqual(returned.side,first.side)
        self.assertEqual((returned.rect.x-first.rect.x,returned.rect.y-first.rect.y),(4,1))
        layout.place([],now=4);self.assertEqual(layout.states,{})

    def test_frozen_anchor_is_reserved_before_a_new_moving_card(self):
        layout=TranslationLayout();layout.place([message('a')],now=0)
        result=layout.place([message('b',350,100),message('a',120,100,visible=False)],now=.2)
        self.assertEqual(result['a'].rect.overlap(result['b'].rect),0)

    def test_small_game_bounds_fit_the_card_without_changing_content(self):
        row=message('a',200,100,size=(360,250));row['bounds']=(50,40,200,160)
        result=TranslationLayout().place([row],now=0)['a'].rect
        self.assertTrue(result.inside(Box(*row['bounds'])));self.assertEqual(result.width,196);self.assertEqual(result.height,156)


class TranslationRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):self.window=AnnotationWindow(start_listener=False)

    def tearDown(self):
        self.window.pointer_timer.stop();self.window.watchdog.stop();self.window.close();self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.app.processEvents()

    def send(self,rows,*,reduce=True):
        self.window.read_command(json.dumps(dict(geometry=[0,0,1000,700],reduce_motion=reduce,rows=rows)))

    @staticmethod
    def row(key='chat:a',x=120,y=100,**extra):
        return dict(kind='translation',key=key,name='Player',text='Hello!',original='안녕하세요',
                    source_box=[x,y,100,36],bounds=[0,0,1000,700],x=x+108,y=y,animate_move=True,**extra)

    def test_compact_real_card_preserves_readable_fonts_original_and_price_geometry(self):
        shop=dict(kind='shop',key='shop:a',name='Work Gloves',text='FM 250,000',x=600,y=50)
        self.send([shop]);shop_rect=self.window.label_rect(self.window.rows[0],QPoint())
        self.send([shop,self.row()]);card=self.window.rows[1];rect=self.window.label_rect(card,QPoint())
        self.assertEqual(card['_width'],160);self.assertEqual(rect.x(),225)
        self.assertEqual(card['original'],'안녕하세요');self.assertEqual(self.window.translation_font.pixelSize(),13)
        self.assertEqual(self.window.original_font.pixelSize(),11)
        self.assertEqual(self.window.label_rect(self.window.rows[0],QPoint()),shop_rect)
        image=self.window.grab().toImage();self.assertFalse(image.isNull())
        self.assertGreater(sum(image.pixelColor(x,y).alpha()>0 for x in range(rect.left()+8,rect.right()-8)
                               for y in range(rect.top()+36+card['_english_height'],rect.bottom()-6)),50)

    def test_long_card_wraps_at_maximum_width_and_keeps_native_sources_uncovered(self):
        row=self.row();row['text']='Looking for two people for a Kerning PQ bonus party; please invite the warrior.'
        row['original']='보너스팟 전사껴주시나요?'
        self.send([row]);card=self.window.rows[0];rect=self.window.label_rect(card,QPoint())
        self.assertEqual(card['_width'],360);self.assertGreater(card['_english_height'],15)
        self.assertFalse(rect.intersects(QRect(*row['source_box'])))

    def test_multiple_popups_avoid_each_other_and_the_existing_status(self):
        rows=[self.row('chat:a',250,200),self.row('chat:b',360,200),self.row('chat:c',400,290)]
        status=dict(kind='translation_status',key='chat:status',name='Korean translation',text='Scanning Korean',
                    x=996,y=696,anchor='bottom_right',bounds=[0,0,1000,700])
        self.send([*rows,status]);boxes=[self.window.label_rect(row,QPoint()) for row in self.window.rows]
        for index,rect in enumerate(boxes[:-1]):
            for other in boxes[index+1:]:self.assertFalse(rect.intersects(other))
            for source in rows:self.assertFalse(rect.intersects(QRect(*source['source_box'])))
        self.assertEqual(boxes[-1].right(),995);self.assertEqual(boxes[-1].bottom(),695)

    def test_small_motion_interrupts_from_current_pixels_and_reduce_motion_cancels_it(self):
        self.send([self.row()],reduce=False);row=self.window.rows[0]
        self.send([self.row(x=128,y=104)],reduce=False);movement=row['_move'];movement.setCurrentTime(40)
        current=row['_draw_pos'];self.send([self.row(x=132,y=106)],reduce=False)
        self.assertIs(self.window.rows[0],row);self.assertEqual(row['_move'].startValue(),current)
        self.send([self.row(x=135,y=107)],reduce=True)
        self.assertIsNone(row.get('_move'));self.assertNotIn('_draw_pos',row)
        rect=self.window.label_rect(row,QPoint());self.assertEqual((rect.x(),rect.y()),(240,107))
