"""Actual reader IPC fed generated screenshots; never starts OS sharing."""
import os,json
from pathlib import Path
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent, QRect
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from price_lens.capture import PixelReader,pointer_in_shop
from test_game_area import game_frame

ROOT=Path(__file__).resolve().parents[1]


class AreaCaptureTests(unittest.TestCase):
    def test_writer_exclusions_convert_full_display_to_manual_crop_before_roi(self):
        reader=PixelReader(ROOT);reader.timer.stop()
        try:
            self.assertTrue(reader.process.waitForStarted(3000))
            reader.image=QImage(1000,800,QImage.Format.Format_RGBA8888);reader.image.fill(QColor('#cccccc'))
            reader.crop=QRect(100,80,600,500)
            reader.shop_rect=QRect(120,90,250,250);reader.roi_clean=True
            reader.writer_regions=lambda:[QRect(350,260,250,200),QRect(500,500,300,200),QRect(50,40,100,100),QRect(750,10,100,100)]
            with patch.object(reader.process,'write') as write:
                reader.scan();request=json.loads(bytes(write.call_args[0][0]))
            self.assertEqual(request['origin'],dict(x=104,y=74))
            self.assertEqual(request['exclude'],[
                dict(x=250,y=180,width=250,height=200),
                dict(x=400,y=420,width=200,height=80),
                dict(x=0,y=0,width=50,height=60)])
            self.assertTrue(reader.using_roi)
        finally:
            reader.close();reader.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.app.processEvents()

    def test_empty_blue_npc_table_does_not_suppress_inventory_tooltip_requests(self):
        reader=PixelReader(ROOT);reader.timer.stop();reader.tooltip_enabled=True
        frame=QImage(800,800,QImage.Format.Format_RGBA8888);frame.fill(QColor('#cccccc'))
        reader.image=reader.submitted_image=frame;reader.pointer=(450,250)
        reader.shop_context=QRect(400,200,200,300)
        table=dict(x=400,y=200,width=200,height=300)
        try:
            self.assertTrue(reader.process.waitForStarted(3000))
            message=json.dumps(dict(atMs=0,shop=dict(area=table,rows=[]),tooltip=None))+'\n'
            with patch.object(reader.process,'readAllStandardOutput',return_value=message.encode()):reader.on_output()
            self.assertFalse(pointer_in_shop(reader.pointer,reader.shop_context))
            with patch.object(reader.process,'write') as write:
                reader.scan()
                request=json.loads(bytes(write.call_args[0][0]))
            self.assertTrue(request['tooltip']);self.assertFalse(reader.using_roi)
        finally:
            reader.close();reader.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.app.processEvents()
    def test_inventory_hover_reads_alongside_an_open_shop_without_roi_clipping(self):
        reader=PixelReader(ROOT);reader.live_source=True;reader.tooltip_enabled=True
        readings=[];reader.reading.connect(readings.append)
        def wait_for(predicate):
            deadline=time.monotonic()+10
            while not predicate():
                self.assertLess(time.monotonic(),deadline,'Inventory/shop fixture did not finish')
                self.app.processEvents();time.sleep(.005)
        frame=game_frame(width=1200,height=800,desktop=(1600,1000));painter=QPainter(frame)
        painter.drawImage(650,180,QImage(str(ROOT/'vendor/minerva/samples/player-shop/gems-and-ores.png')))
        painter.drawImage(140,180,QImage(str(ROOT/'vendor/minerva/samples/item-tooltip/screw@60,20.png')));painter.end()
        try:
            wait_for(lambda:reader.process.state()==reader.process.ProcessState.Running)
            reader.on_stream_frame(frame,time.monotonic());wait_for(lambda:bool(readings) and not reader.pending)
            self.assertEqual(len(readings[-1]['shop']['rows']),5)
            count=len(readings);reader.pointer=(200,200)
            reader.on_stream_frame(frame,time.monotonic());wait_for(lambda:len(readings)>count and not reader.pending)
            self.assertEqual(readings[-1]['tooltip']['found']['name'],'Screw')
            self.assertEqual(len(readings[-1]['shop']['rows']),5)
            self.assertFalse(reader.using_roi)
        finally:
            reader.close();reader.deleteLater()
            QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.app.processEvents()

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
        cls.app=QApplication.instance() or QApplication([])

    def test_slightly_moved_shop_recovers_prices_from_partially_clipped_crop(self):
        reader=PixelReader(ROOT);reader.live_source=True
        readings=[];reader.reading.connect(readings.append)
        def wait_for(predicate):
            deadline=time.monotonic()+10
            while not predicate():
                self.assertLess(time.monotonic(),deadline,"Moved shop did not recover full listing prices")
                self.app.processEvents();time.sleep(.005)
        try:
            wait_for(lambda:reader.process.state()==reader.process.ProcessState.Running)
            for x in (160,185):
                frame=game_frame(x=0,y=0,width=800,height=800,desktop=(800,800))
                painter=QPainter(frame)
                painter.drawImage(x,140,QImage(str(ROOT/'vendor/minerva/samples/player-shop/gems-and-ores.png')))
                painter.end();count=len(readings)
                reader.on_stream_frame(frame,time.monotonic())
                wait_for(lambda:len(readings)>count and bool(readings[-1].get("shop")) and
                         len(readings[-1]["shop"]["rows"])==5 and all(r.get("price") for r in readings[-1]["shop"]["rows"]))
                self.assertEqual(readings[-1]["shop"]["rows"][0]["price"],{"quantity":1,"mesos":999})
        finally:
            reader.close();reader.deleteLater()
            QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.app.processEvents()

    def test_pixel_tracker_rejects_old_coordinates_and_stops_when_covered(self):
        reader=PixelReader(ROOT)
        reader.live_source=True
        results=[]
        reader.reading.connect(results.append)
        def wait_for(predicate):
            deadline=time.monotonic()+10
            while not predicate():
                self.assertLess(time.monotonic(),deadline,"Pixel reader did not finish fixture")
                self.app.processEvents()
                time.sleep(0.005)
        try:
            wait_for(lambda:reader.process.state()==reader.process.ProcessState.Running)
            reader.on_stream_frame(game_frame(),time.monotonic())
            wait_for(lambda:bool(results))
            self.assertIsNotNone(reader.game_area)
            self.assertEqual(len(reader.game_guards),2)
            reader.on_stream_frame(game_frame(x=320,y=180),time.monotonic())
            self.assertIsNone(reader.game_area,"Old coordinates must disappear before the new OCR result")
            wait_for(lambda:reader.game_area is not None)
            self.assertLessEqual(abs(reader.game_area.x()-320),8)
            blank=QImage(1600,900,QImage.Format.Format_RGBA8888)
            blank.fill(QColor("#171c25"))
            count=len(results)
            reader.on_stream_frame(blank,time.monotonic())
            self.assertIsNone(reader.game_area)
            wait_for(lambda:len(results)>count)
            self.assertIsNone(results[-1]["gameArea"])
            self.assertIsNone(results[-1]["shop"])
            self.assertEqual(reader.stream.socket.state(),reader.stream.socket.LocalSocketState.UnconnectedState)
        finally:
            reader.close()
            reader.deleteLater()
            QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
            self.app.processEvents()

    def test_focus_colours_keep_game_location_without_reacquisition(self):
        reader=PixelReader(ROOT);reader.live_source=True
        def wait_for(predicate):
            deadline=time.monotonic()+10
            while not predicate():
                self.assertLess(time.monotonic(),deadline)
                self.app.processEvents();time.sleep(.005)
        try:
            wait_for(lambda:reader.process.state()==reader.process.ProcessState.Running)
            reader.on_stream_frame(game_frame(),time.monotonic())
            wait_for(lambda:reader.game_area is not None and not reader.pending)
            area=QRect(reader.game_area);generation=reader.generation
            frame=game_frame();painter=QPainter(frame)
            painter.fillRect(120,90,960,24,QColor('#686868'));painter.end()
            reader.on_stream_frame(frame,time.monotonic())
            self.assertEqual(reader.game_area,area)
            self.assertEqual(reader.generation,generation)
            wait_for(lambda:not reader.pending)
            self.assertEqual(reader.game_area,area)
        finally:
            reader.close();reader.deleteLater()
            QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.app.processEvents()

    def test_tooltip_hiding_first_rows_cannot_shrink_the_recovery_crop(self):
        reader=PixelReader(ROOT);reader.live_source=True;readings=[];reader.reading.connect(readings.append)
        def wait_for(predicate):
            deadline=time.monotonic()+10
            while not predicate():
                self.assertLess(time.monotonic(),deadline,'Shop rows did not recover after tooltip')
                self.app.processEvents();time.sleep(.005)
        frame=game_frame(width=1200,height=800,desktop=(1600,1000));painter=QPainter(frame)
        painter.drawImage(340,180,QImage(str(ROOT/'vendor/minerva/samples/player-shop/gems-and-ores.png')));painter.end()
        try:
            wait_for(lambda:reader.process.state()==reader.process.ProcessState.Running)
            reader.on_stream_frame(frame,time.monotonic());wait_for(lambda:bool(readings) and not reader.pending)
            self.assertEqual(len(readings[-1]['shop']['rows']),5)
            original=QRect(reader.shop_context)
            masked=frame.copy();painter=QPainter(masked);painter.fillRect(440,184,220,125,QColor('#eeeeee'));painter.end()
            reader.pointer=(500,230);count=len(readings)
            reader.on_stream_frame(masked,time.monotonic());wait_for(lambda:len(readings)>count and not reader.pending)
            self.assertTrue(reader.shop_context.contains(original))
            reader.pointer=(250,100);count=len(readings)
            reader.on_stream_frame(frame,time.monotonic())
            wait_for(lambda:len(readings)>count and bool(readings[-1].get('shop')) and len(readings[-1]['shop']['rows'])==5)
            self.assertEqual(readings[-1]['shop']['rows'][0]['name'],'Garnet')
        finally:
            reader.close();reader.deleteLater()
            QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.app.processEvents()

    def test_stationary_shop_skips_ocr_until_geometry_check_is_due(self):
        reader=PixelReader(ROOT)
        reader.live_source=True
        results=[]
        reader.reading.connect(results.append)
        def wait_for(predicate):
            deadline=time.monotonic()+10
            while not predicate():
                self.assertLess(time.monotonic(),deadline,"Reader did not finish shop fixture")
                self.app.processEvents()
                time.sleep(0.005)
        try:
            wait_for(lambda:reader.process.state()==reader.process.ProcessState.Running)
            frame=game_frame(width=1200,height=800,desktop=(1600,1000))
            painter=QPainter(frame)
            painter.drawImage(340,180,QImage(str(ROOT/'vendor/minerva/samples/player-shop/gems-and-ores.png')))
            painter.end()
            reader.on_stream_frame(frame,time.monotonic())
            wait_for(lambda:bool(results))
            self.assertIsNotNone(reader.shop_rect)
            self.assertIsNotNone(reader.shop_fingerprint)
            count=len(results)
            submitted=reader.pending_since
            # Isolate the geometry interval from CPU contention during real OCR.
            with patch("price_lens.capture.time.monotonic", return_value=reader.last_geometry_check+.01):
                reader.on_stream_frame(frame,time.monotonic())
                self.app.processEvents()
                self.assertEqual(reader.pending_since,submitted,"Unchanged pixels should skip another OCR request")
            self.assertEqual(len(results),count)
            reader.last_locator_check=time.monotonic()-2
            reader.on_stream_frame(frame,time.monotonic())
            wait_for(lambda:len(results)>count)
            self.assertIsNotNone(reader.game_area)
        finally:
            reader.close()
            reader.deleteLater()
            QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
            self.app.processEvents()
