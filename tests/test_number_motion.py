"""First values, thousands boundaries and mid-roll changes keep real digit positions."""
import os,unittest
from PySide6.QtCore import QRect,QSize,QSettings
from PySide6.QtWidgets import QApplication,QWidget
from PySide6.QtTest import QTest
from price_lens.number_motion import NumberRoll
from price_lens.motion import RollingLabel,MotionLabel
from price_lens import window_size


class NumberMotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen');cls.app=QApplication.instance() or QApplication([])

    def test_first_numeric_value_rolls_and_separators_do_not(self):
        roll=NumberRoll('—');self.assertTrue(roll.set_text('+1,200 mesos'))
        self.assertEqual(roll.progress,0)
        for key,char in roll.columns:
            if char.isdigit():self.assertIsNotNone(key)
            else:self.assertIsNone(key)

    def test_thousands_transition_keeps_digit_place_and_mid_roll_retargets_without_jump(self):
        roll=NumberRoll('999');roll.set_text('1,000');roll.progress=.4
        before=roll.layers((0,'integer',0),'0')
        roll.set_text('1,001')
        after=roll.layers((0,'integer',0),'1')
        self.assertEqual([x for x in after if x[2]>0],before)
        roll.progress=1
        self.assertEqual(roll.layers((0,'integer',0),'1'),[('1',0,1)])

    def test_hidden_and_reduce_motion_labels_stop_animation(self):
        self.app.setProperty('reduceMotion',False)
        label=RollingLabel('—');label.show();self.app.processEvents();label.setText('1,200')
        self.assertEqual(label.animation.state(),label.animation.State.Running)
        label.hide();self.assertEqual(label.animation.state(),label.animation.State.Stopped)
        self.app.setProperty('reduceMotion',True);label.show();label.setText('1,300')
        self.assertEqual(label.animation.state(),label.animation.State.Stopped)
        label.close();label.deleteLater();self.app.setProperty('reduceMotion',False)

    def test_digit_updates_keep_static_caption_opaque_and_numeric_geometry_stable(self):
        self.app.setProperty('reduceMotion',False)
        caption=MotionLabel('Measured over 31 seconds');caption.resize(350,30);caption.show()
        value=RollingLabel('9.99%');value.show();self.app.processEvents()
        hint=value.sizeHint();caption.setText('Measured over 32 seconds')
        self.assertEqual(caption.alpha,1.0)
        self.assertEqual(caption.animation.state(),caption.animation.State.Stopped)
        self.assertEqual(caption.digits.state(),caption.digits.State.Running)
        value.setText('100,000,000');self.assertEqual(value.sizeHint(),hint)
        caption.hide();value.hide();caption.deleteLater();value.deleteLater()

    def test_static_caption_pixels_do_not_shift_during_or_after_a_digit_roll(self):
        self.app.setProperty('reduceMotion',False)
        label=MotionLabel('Training for 31 seconds');label.resize(300,30);label.show();self.app.processEvents()
        before=label.grab().toImage().copy(0,0,60,30)
        label.setText('Training for 32 seconds')
        label.digits.setCurrentTime(80)
        self.assertEqual(label.grab().toImage().copy(0,0,60,30),before)
        label.digits.setCurrentTime(160)
        self.assertEqual(label.grab().toImage().copy(0,0,60,30),before)
        label.hide();label.deleteLater()


class WindowSizeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):NumberMotionTests.setUpClass();cls.app=NumberMotionTests.app

    def test_screen_filling_saved_geometry_reopens_at_compact_width(self):
        class Settings:
            def value(self,key,default=None):
                return QSize(1896,948) if key=='window-size' else default
        window=QWidget();window_size.restore(window,Settings())
        self.assertEqual(window.width(),509)
        self.assertLess(window.width(),self.app.primaryScreen().availableGeometry().width()*.95)
        window.close();window.deleteLater()

    def test_normal_state_desktop_geometry_does_not_replace_the_last_compact_size(self):
        class Settings:
            def __init__(self):self.values={}
            def value(self,key,default=None):return self.values.get(key,default)
            def setValue(self,key,value):self.values[key]=value
        settings=Settings();window=QWidget();window_size.restore(window,settings)
        compact=window.size()
        window.resize(self.app.primaryScreen().availableGeometry().size())
        window_size.remember(window);window_size.save(window,settings)
        self.assertEqual(window._normal_size,compact)
        self.assertEqual(settings.value('window-size'),compact)
        window.close();window.deleteLater()

    def test_normal_size_survives_reopen_and_oversized_saved_size_is_clamped(self):
        class Settings:
            values={}
            def value(self,key,default=None):return self.values.get(key,default)
            def setValue(self,key,value):self.values[key]=value
        settings=Settings();first=QWidget();window_size.restore(first,settings)
        cap=self.app.primaryScreen().availableGeometry().size()
        desired=QSize(min(670,cap.width()-24),min(730,cap.height()-32))
        first.resize(desired);first._normal_size=first.size();window_size.save(first,settings)
        second=QWidget();window_size.restore(second,settings);self.assertEqual(second.size(),first.size())
        settings.setValue('window-size',QSize(10000,10000));third=QWidget();window_size.restore(third,settings)
        self.assertLessEqual(third.height(),cap.height()-32);self.assertLessEqual(third.width(),cap.width()-24)
        for widget in (first,second,third):widget.close();widget.deleteLater()
