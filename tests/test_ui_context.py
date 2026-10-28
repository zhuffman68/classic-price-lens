"""Exercise real UI context rules with fake pixel/input data and no OS capture."""
import os
from dataclasses import replace
from pathlib import Path
import time
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QRect, Qt, QTimer, Signal,QPoint
from PySide6.QtGui import QColor, QImage, QKeySequence, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QKeySequenceEdit, QLabel, QPushButton

from price_lens.domain import Catalog, Quote
from price_lens.ui import LensWindow


class FakeOverlay(QObject):
    pointer = Signal(int, int)

    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.rows = []

    def update(self, geometry, rows, hover_enabled=False):
        self.rows = rows

    def close(self):
        pass


class FakeReader(QObject):
    reading = Signal(dict)
    status = Signal(str)
    image_ready = Signal(QImage)
    area_changed = Signal()
    experience = Signal(dict)

    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.image = QImage(800, 800, QImage.Format.Format_RGBA8888)
        self.crop = None
        self.pointer = (340, 240)
        self.shop_context = QRect(300, 200, 240, 300)
        self.latest_latency_ms = 30
        self.image_sequence = 0
        self.last_frame = time.monotonic()
        self.starts = 0
        self.pauses = []
        self.auto_active = True
        self.game_area = QRect(0, 0, 800, 800)

    def set_auto_area(self, enabled):
        self.auto_active = enabled

    def start(self, *args):
        self.starts += 1

    def pause(self, keep_stream=False):
        self.pauses.append(keep_stream)

    def close(self, keep_stream=False):
        pass


class FakeService(QObject):
    catalog_ready = Signal(object)
    quote_ready = Signal(int, object)
    error = Signal(int, str)
    identity_ready = Signal(object, object)
    identity_error = Signal(object, str)
    state_changed = Signal()

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.requests = []
        self.catalog_starts = 0
        self.visible = []
        self.hovered_id = None
        self.states = {}

    def start(self):
        self.catalog_starts += 1

    def request(self, item, ttl):
        self.requests.append(item.game_id)

    def observe(self, items, ttl, *, hovered_id=None, identities=(), hovered_identity=None):
        self.visible = [item.game_id for item in items]
        self.hovered_id = hovered_id
        self.requests.extend(self.visible)

    def clear_visible(self):
        self.visible = []

    def set_manual(self, item, ttl=900, **kwargs):
        self.manual_item = item

    def set_snapshot_enabled(self, enabled):
        self.refresh_snapshot = enabled

    def set_refresh_interval(self,seconds):self.interval=seconds

    def cached(self,item):return getattr(self,'cached_values',{}).get(item.game_id) if item else None

    def state_for(self, item_id):
        return self.states.get(item_id, "")

    def close(self):
        pass


class FakeSettings:
    def __init__(self, *args):
        self.values = {}

    def value(self, key, default, type=None):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value


class FakeHotkeys(QObject):
    activated = Signal()
    activation_token = Signal(str)
    changed = Signal(str)
    status = Signal(str)
    portal = False

    def start(self, text):
        self.changed.emit(text)
        return True

    def close(self):
        pass


class FakeThumbnails(QObject):
    ready=Signal(int)
    def __init__(self,*args):super().__init__();self.items=[]
    def image(self,item_id):return QImage()
    def observe(self,items):self.items=list(items)
    def close(self):pass


class ContextUiTests(unittest.TestCase):
    def test_real_panel_keeps_the_slide_running_after_page_layout_updates(self):
        w=self.window;w.resize(460,960);w.show();self.app.processEvents()
        self.app.setProperty('reduceMotion',False)
        for index in (w.exp_tab_index,w.translation_tab_index,0):
            w.tabs.setCurrentIndex(index)
            self.assertTrue(w.tabs.sliding)
            QTest.qWait(80)
            self.assertTrue(w.tabs.sliding)
            self.assertGreater(w.tabs.animation.currentTime(),0)
            QTest.qWait(260)
            for _ in range(10):
                if not w.tabs.sliding:break
                QTest.qWait(25)
            self.assertFalse(w.tabs.sliding)

    def test_display_resolution_fits_at_460_pixel_width(self):
        w=self.window;w.resize(460,960)
        index=w.monitor.currentIndex()
        w.monitor.setItemText(index,'Display 2 · Centre · 1920 × 1080')
        w.update_capture_controls();w.show();self.app.processEvents()
        self.assertEqual(w.width(),460)
        required=w.monitor.fontMetrics().horizontalAdvance(w.monitor.currentText())+46
        self.assertGreaterEqual(w.monitor.width(),required)

    def test_removed_on_top_preference_cannot_trap_a_new_panel(self):
        settings=FakeSettings();settings.values['keep-on-top']=True
        with patch('price_lens.ui.QSettings',return_value=settings):
            fresh=LensWindow(Path.cwd(),Path('unused-cache'))
        try:
            self.assertFalse(fresh.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
            self.assertFalse(settings.values['keep-on-top'])
            self.assertFalse(hasattr(fresh,'pin_check'))
        finally:fresh.close();fresh.deleteLater()

    def test_translation_timings_fit_inline_at_minimum_width(self):
        w=self.window;w.resize(460,960);w.show();w.tabs.setCurrentIndex(w.translation_tab_index)
        QTest.qWait(350);self.app.processEvents()
        panel=w.translation_panel
        for label,spin,value in zip(panel.timing_labels,(panel.scan,panel.linger),(10,5)):
            spin.setValue(value);self.app.processEvents()
            self.assertLess(abs(label.mapTo(panel,label.rect().center()).y()-spin.mapTo(panel,spin.rect().center()).y()),3)
            editor=spin.lineEdit()
            self.assertLess(editor.fontMetrics().horizontalAdvance(editor.text())+8,editor.width())

    def test_display_selector_and_tab_position_remain_stable_on_every_page(self):
        self.window.mode="idle"
        self.window.show();self.app.processEvents()
        height=self.window.height();positions=[]
        for index in (0,1,2,0,2,1):
            self.window.tabs.setCurrentIndex(index);self.app.processEvents()
            bar=self.window.tabs.tabBar()
            positions.append(bar.mapTo(self.window,bar.rect().topLeft()).y())
            self.assertTrue(self.window.monitor.isVisible())
            self.assertTrue(self.window.setup_frame.isVisible())
            self.assertEqual(self.window.height(),height)
        self.assertEqual(len(set(positions)),1)
        self.assertEqual(self.window.reader.starts,0)
        self.assertFalse(any(b.text() in ("Setup help","Preview with examples") for b in self.window.findChildren(QPushButton)))

    def test_rate_display_and_reduce_motion_settings_are_persistent(self):
        self.assertEqual(self.window.exp_panel.display_mode,"percent")
        self.window.exp_display_combo.setCurrentIndex(self.window.exp_display_combo.findData("both"))
        self.assertEqual(self.window.settings.values["exp-display"],"both")
        self.assertEqual(self.window.exp_panel.display_mode,"both")
        self.window.motion_check.setChecked(True)
        self.assertTrue(self.window.settings.values["reduce-motion"])
        self.assertTrue(self.window.overlay.reduce_motion)

    def test_quote_and_age_updates_keep_the_same_price_card(self):
        self.window.on_reading(self.reading(shop_hover=True))
        before=next(iter(self.window.card_views.values()))
        now=time.time()
        for value in (1000,1200):
            self.window.on_quote(1,Quote(1,value,now,now,20,"Test","","24h"))
            self.assertIs(next(iter(self.window.card_views.values())),before)
        self.assertEqual(before.fields["market"].text(),"1,200 mesos")
        with patch("price_lens.ui.time.time",return_value=now+6):self.window.render()
        self.assertIs(next(iter(self.window.card_views.values())),before)

    def test_shop_thumbnail_uses_exact_item_and_stays_left_of_name(self):
        self.window.on_reading(self.reading(shop_hover=True))
        card=next(iter(self.window.card_views.values()))
        self.assertEqual(card.property('gameItemId'),1)
        self.assertFalse(card.thumbnail.isHidden())
        self.window.resize(460,960);self.window.show();self.app.processEvents()
        self.assertLess(card.thumbnail.x(),card.fields['name'].mapTo(card,card.fields['name'].rect().topLeft()).x())
        self.assertIn(1,[item.game_id for item in self.window.thumbnails.items])

    def test_shop_and_inventory_cards_can_watch_the_exact_item_without_lookup(self):
        w=self.window;w.on_reading(self.reading(shop_hover=True))
        card=next(iter(w.card_views.values()));before=list(w.service.requests)
        self.assertFalse(card.watch_button.isHidden());card.watch_button.click()
        self.assertIn(1,w.watchlist.ids);self.assertTrue(card.watch_button.isChecked())
        self.assertEqual(w.service.requests,before)
        card.watch_button.click();self.assertNotIn(1,w.watchlist.ids)

    def test_inventory_appearing_before_shop_cards_does_not_recreate_the_shop_cards(self):
        w=self.window;w.on_reading(self.reading(shop_hover=True))
        old=next(iter(w.card_views.values()))
        w.tooltip_result={'name':'Example Hat','area':dict(x=100,y=100,width=120,height=16)}
        w.render()
        self.assertIn(old,w.card_views.values())

    def test_search_transitions_preserve_shop_cards_and_animate_their_return(self):
        self.window.on_reading(self.reading(shop_hover=True))
        self.window.resize(460,960);self.window.show();self.app.processEvents()
        before=dict(self.window.card_views)
        self.window.search_panel.query.setText('Example')
        self.assertTrue(self.window.scroll.isHidden())
        self.window.search_panel.timer.stop();self.window.search_panel.find_items()
        self.assertIn('1 matches',self.window.search_panel.hint.text())
        self.window.search_panel.query.clear()
        self.assertFalse(self.window.scroll.isHidden())
        self.assertEqual(self.window.card_views,before)
        self.assertIsNotNone(getattr(self.window.scroll,'_reveal',None))

    def test_price_search_works_without_starting_capture(self):
        self.window.mode = "idle"
        self.window.tabs.setCurrentIndex(self.window.search_tab_index)
        panel = self.window.search_panel
        panel.query.setText("Example Hat")
        panel.timer.stop()
        panel.find_items()
        panel.results.setCurrentRow(0)
        self.assertEqual(self.window.service.manual_item.game_id,1)
        self.assertEqual(self.window.reader.starts,0)
        self.window.tabs.setCurrentIndex(self.window.exp_tab_index)
        self.assertIsNone(self.window.service.manual_item)

    def test_watch_toggle_needs_no_price_request_and_marks_a_pending_reference(self):
        from price_lens.domain import Item
        before=list(self.window.service.requests)
        self.window.watchlist.toggle(Item(1,'Example Hat'))
        self.assertEqual(self.window.service.requests,before)
        self.window.on_reading(self.reading(shop_hover=True))
        row=self.window.overlay.rows[0]
        self.assertTrue(row['watched'])
        event=row['watch_event']
        self.window.on_quote(1,Quote(1,1000,time.time(),time.time(),20,'Test','','24h'))
        self.assertEqual(self.window.overlay.rows[0]['watch_event'],event)
        self.window.watchlist.remove(1)
        self.assertFalse(self.window.overlay.rows[0]['watched'])

    def test_watched_list_opens_without_details_and_collapse_restores_shop(self):
        from price_lens.domain import Item
        w=self.window;w.on_reading(self.reading(shop_hover=True));w.show();self.app.processEvents()
        quote=Quote(1,1000,time.time(),time.time(),20,'MesoWatch','','24h')
        w.service.cached_values={1:quote};w.watchlist.toggle(Item(1,'Example Hat'))
        section=w.search_panel.watched_items;QTest.qWait(230);self.app.processEvents()
        self.assertIsNone(w.search_panel.selected)
        self.assertTrue(w.search_panel.detail_scroll.isHidden())
        self.assertEqual(section.rows.item(0).data(Qt.ItemDataRole.UserRole+1)[0],1000)
        point=section.rows.visualItemRect(section.rows.item(0)).center()
        QTest.mouseClick(section.rows.viewport(),Qt.MouseButton.LeftButton,pos=point)
        self.assertEqual(w.search_panel.selected.game_id,1)
        self.assertTrue(w.scroll.isHidden())
        QTest.mouseClick(section.rows.viewport(),Qt.MouseButton.LeftButton,pos=point)
        self.assertIsNone(w.search_panel.selected)
        self.assertTrue(w.scroll.isHidden())
        QTest.mouseClick(section.rows.viewport(),Qt.MouseButton.LeftButton,pos=point)
        section.set_expanded(False)
        self.assertIsNone(w.search_panel.selected)
        self.assertFalse(w.scroll.isHidden())
        self.assertIsNone(w.service.manual_item)

    def test_watched_section_clips_stable_contents_and_limits_to_three_rows(self):
        from price_lens.domain import Item
        w=self.window;w.show();self.app.processEvents()
        for n in range(5):w.watchlist.toggle(Item(1000000+n,f'Example {n}'))
        section=w.search_panel.watched_items;QTest.qWait(230);self.app.processEvents()
        self.assertEqual(section.rows.height(),130)
        self.assertGreater(section.rows.verticalScrollBar().maximum(),0)
        full=section.body.height();contents=section.body.content.height()
        section.set_expanded(False);section.body.animation.setCurrentTime(100)
        self.assertGreater(section.body.height(),0);self.assertLess(section.body.height(),full)
        self.assertEqual(section.body.content.height(),contents)
        middle=section.body.height();section.set_expanded(True)
        self.assertEqual(section.body.height(),middle)
        section.body.animation.setCurrentTime(200)
        self.assertEqual(section.body.height(),full)
        for expanded in (False,True):
            section.set_expanded(expanded);positions=[]
            for ms in range(0,201,20):
                section.body.animation.setCurrentTime(ms);self.app.processEvents()
                positions.append(section.body.content.mapTo(w,QPoint()).y())
            self.assertEqual(len(set(positions)),1,positions)

    def test_windows_starting_state_does_not_request_a_system_chooser(self):
        self.window.mode='idle'
        with patch('price_lens.ui.uses_system_picker',return_value=False):
            self.window.start_capture()
            self.assertEqual(self.window.status_badge.text(),'Starting screen reading')
            self.assertEqual(self.window.capture_info.text(),f'Connecting to {self.window.selected_display()}.')
            self.assertNotIn('behind another window',self.window.capture_info.text())

    def test_wayland_starting_state_still_requests_the_system_picker(self):
        self.window.mode='idle'
        with patch('price_lens.ui.uses_system_picker',return_value=True):
            self.window.start_capture()
            self.assertEqual(self.window.status_badge.text(),'Waiting for screen sharing')
            self.assertIn('system sharing dialog',self.window.capture_info.text())

    def test_no_displays_disables_start_without_a_selectable_placeholder(self):
        with patch('price_lens.ui.QApplication.screens',return_value=[]):
            self.window.refresh_monitors()
        self.assertEqual(self.window.monitor.count(),0)
        self.assertIsNone(self.window.screen_index)
        self.assertFalse(self.window.share.isEnabled())
        self.assertEqual(self.window.status_badge.text(),'No display available')

    def test_catalog_certificate_error_keeps_the_diagnostic_and_explains_the_failure(self):
        message='Item catalog unavailable: [SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer certificate'
        self.window.on_error(0,message)
        self.assertEqual(self.window.last_diagnostic,message)
        self.assertIn('secure item connection',self.window.search_panel.hint.text())

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.exp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.exp_directory.cleanup)
        self.patchers = [patch("price_lens.ui." + name, replacement) for name, replacement in
                         [("Overlay", FakeOverlay), ("PixelReader", FakeReader),
                          ("PriceService", FakeService), ("QSettings", FakeSettings), ("HotkeyManager", FakeHotkeys),
                          ("data_directory", lambda: Path(self.exp_directory.name)),("ThumbnailCache",FakeThumbnails)]]
        for patcher in self.patchers:
            patcher.start()
        self.tray_show = patch("price_lens.tray.QSystemTrayIcon.show")
        self.tray_show.start()
        self.window = LensWindow(Path.cwd(), Path("unused-cache"))
        self.window.monitor.setCurrentIndex(0)
        self.window.on_catalog(Catalog({"items": [{"id": 1, "name": "Example Hat"}], "scrolls": []}))
        self.window.mode = "live"
        self.window.last_screen = time.time()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.tray_show.stop()

    def reading(self, shop_hover, store=None):
        store = shop_hover if store is None else store
        if not store:
            self.window.reader.shop_context=None
            self.window.shop_rows.reset()  # Closing removes the header/scrollbar pixels in a real frame.
        return {"atMs": 123, "shop": {"area": {"x": 300, "y": 200, "width": 240, "height": 300},
                "rows": [{"name": "Example Hat", "price": {"quantity": 1, "mesos": 100},
                          "area": {"x": 340, "y": 220, "width": 180, "height": 40}}]} if store else None,
                "hover": {"pointer": {"x": 340, "y": 240}} if shop_hover else None,
                "tooltip": {"found": {"name": "Example Hat", "area": {"x": 100, "y": 100, "width": 180, "height": 20}}}}

    def test_hover_is_on_by_default_and_the_import_button_is_gone(self):
        self.assertTrue(self.window.hover_check.isChecked())
        self.assertTrue(self.window.reader.tooltip_enabled)
        self.assertFalse(any("Import MesoWatch" in button.text() for button in self.window.findChildren(QPushButton)))

    def test_automatic_game_area_is_enabled_by_default(self):
        self.assertTrue(self.window.auto_area_check.isChecked())
        self.assertTrue(self.window.reader.auto_enabled)

    def test_market_updates_on_launch_with_the_selected_global_interval(self):
        self.assertTrue(self.window.service.refresh_snapshot)
        self.assertEqual(self.window.service.interval,self.window.ttl)
        self.window.ttl_combo.setCurrentIndex(0)
        self.assertEqual(self.window.service.interval,300)
        self.assertFalse(hasattr(self.window,'bulk_check'))

    def test_lost_game_area_hides_labels_and_stops_price_requests(self):
        self.window.on_reading(self.reading(shop_hover=True))
        count=len(self.window.service.requests)
        self.window.reader.game_area=None
        self.window.reader.area_changed.emit()
        self.assertEqual(self.window.rows,[])
        self.assertEqual(self.window.overlay.rows,[])
        self.assertEqual(self.window.status_badge.text(),"Looking for Classic World")
        self.window.on_reading(self.reading(shop_hover=True))
        self.window.tick()
        self.assertEqual(len(self.window.service.requests),count)
        self.assertEqual(self.window.overlay.rows,[])

    def test_auto_area_toggle_is_saved_without_restarting_capture(self):
        self.window.auto_area_check.setChecked(False)
        self.assertFalse(self.window.settings.values["auto-game-area"])
        self.assertFalse(self.window.reader.auto_active)
        self.assertEqual(self.window.reader.starts,0)

    def test_store_hover_never_draws_a_duplicate_inventory_label(self):
        self.window.on_reading(self.reading(shop_hover=True))
        self.assertIsNone(self.window.tooltip_result)
        self.assertEqual(len(self.window.overlay.rows), 1)

    def test_description_disappearance_restores_market_labels_without_waiting_for_ocr(self):
        self.window.on_reading(self.reading(shop_hover=True))
        self.window.rows=[{**r,'covered':True,'reference_only':True,'price':None} for r in self.window.rows]
        self.window.shop_tooltip_rect=QRect(300,200,220,200)
        self.window.reader.image.fill(QColor('#171c25'))
        count=len(self.window.service.requests)
        self.window.on_image(self.window.reader.image)
        self.assertNotIn('obscured',self.window.overlay.rows[0])
        self.assertIsNone(self.window.overlay.rows[0]['occlusion'])
        self.assertEqual(len(self.window.service.requests),count)

    def test_inventory_hover_outside_store_list_can_show_its_price(self):
        self.window.reader.pointer = (100, 100)
        self.window.on_reading(self.reading(shop_hover=False))
        self.assertEqual(self.window.tooltip_result["name"], "Example Hat")
        self.assertEqual(len(self.window.overlay.rows), 1)

    def test_linked_item_far_from_pointer_requires_a_visible_description_panel(self):
        from PySide6.QtGui import QPainter
        w=self.window;w.reader.pointer=(10,790)
        reading=self.reading(shop_hover=False)
        found=reading['tooltip']['found'];found['area']=dict(x=690,y=100,width=100,height=18);found['pinned']=True
        self.window.on_reading(reading);self.assertIsNone(w.tooltip_result)
        painter=QPainter(w.reader.image);painter.fillRect(675,80,125,260,QColor('#464b78'));painter.end()
        w.on_reading(reading)
        self.assertIsNotNone(w.tooltip_result)
        self.assertNotIn('follow_pointer',w.overlay.rows[-1])
        self.assertEqual(w.overlay.rows[-1]['name'],'Example Hat')

    def test_absent_tooltip_enums_do_not_interrupt_shop_close_or_next_inventory_read(self):
        reading = self.reading(shop_hover=True)
        reading['tooltip'] = 'not_found'
        reading['hover']['tooltip'] = 'not_found'
        self.window.on_reading(reading)
        self.assertTrue(self.window.shop_open)
        closed = self.reading(shop_hover=False)
        closed['tooltip'] = 'not_found'
        self.window.on_reading(closed)
        self.assertFalse(self.window.shop_open)
        self.window.reader.pointer = (100, 100)
        self.window.on_reading(self.reading(shop_hover=False))
        self.assertEqual(self.window.tooltip_result['name'], 'Example Hat')

    def test_disabling_setting_stops_tooltip_processing_and_clears_label(self):
        self.window.reader.pointer = (100, 100)
        self.window.on_reading(self.reading(shop_hover=False))
        self.window.set_hover(False)
        self.assertIsNone(self.window.tooltip_result)
        self.assertFalse(self.window.reader.tooltip_enabled)
        self.assertFalse(self.window.settings.values["tooltip-prices"])

    def test_empty_or_unknown_tooltip_candidates_never_draw_floating_prices(self):
        self.window.reader.pointer = (100, 100)
        for name in (None, "", "Random scenery OCR"):
            with self.subTest(name=name):
                reading = self.reading(shop_hover=False)
                reading["tooltip"]["found"]["name"] = name
                self.window.on_reading(reading)
                self.assertIsNone(self.window.tooltip_result)
                self.assertEqual(len(self.window.overlay.rows), 0)

    def test_tooltip_without_pointer_or_far_from_it_is_ignored(self):
        self.window.reader.pointer = None
        self.window.on_reading(self.reading(shop_hover=False))
        self.assertIsNone(self.window.tooltip_result)
        self.window.reader.pointer = (1500, 1500)
        self.window.on_reading(self.reading(shop_hover=False))
        self.assertIsNone(self.window.tooltip_result)

    def test_tall_tooltip_name_above_pointer_is_valid(self):
        self.window.reader.pointer = (100, 600)
        self.window.on_reading(self.reading(shop_hover=False))
        self.assertEqual(self.window.tooltip_result["name"], "Example Hat")
        self.assertEqual(len(self.window.overlay.rows), 1)

    def test_named_bandana_and_greater_scroll_use_the_actual_item_name(self):
        self.window.on_catalog(Catalog({"items": [{"id": 1002013, "name": "Blue Bandana", "category": "Equipment"}],
                                       "scrolls": [{"id": 2040002, "name": "Hat Accuracy Scroll: Greater", "tier": "Greater"}]}))
        self.window.reader.pointer = (100, 650)
        for name, expected in [("Blue Bandana", "Blue Bandana"),
                               ("Hat Accuracy Scroll:Greater", "Hat Accuracy Scroll: Greater")]:
            with self.subTest(name=name):
                reading = self.reading(shop_hover=False)
                reading["tooltip"]["found"]["name"] = name
                self.window.on_reading(reading)
                self.assertEqual(self.window.overlay.rows[-1]["name"], expected)

    def test_native_shop_stats_popup_keeps_shop_prices_visible(self):
        reading = self.reading(shop_hover=True)
        reading["hover"]["tooltip"] = {"found": reading["tooltip"]["found"]}
        self.window.on_reading(reading)
        self.assertTrue(self.window.shop_open)
        self.assertEqual(len(self.window.overlay.rows), 1)
        self.assertEqual(self.window.overlay.rows[0]["kind"],"shop")
        self.window.on_reading(self.reading(shop_hover=True))
        self.assertTrue(self.window.shop_open)
        self.assertEqual(len(self.window.overlay.rows), 1)

    def test_covered_shop_rows_do_not_draw_unreadable_price_badges(self):
        reading = self.reading(shop_hover=True)
        reading["shop"]["rows"][0].update(name=None, price=None, covered=True)
        self.window.on_reading(reading)
        self.assertEqual(self.window.overlay.rows, [])

    def test_small_cursor_moves_keep_the_identified_price_and_card(self):
        self.window.reader.pointer = (100, 100)
        self.window.on_reading(self.reading(shop_hover=False))
        card = self.window.cards_layout.itemAt(0).widget()
        key = self.window.card_key
        self.window.on_pointer(108, 105)
        self.assertIsNotNone(self.window.tooltip_result)
        self.window.render()
        self.assertIs(self.window.cards_layout.itemAt(0).widget(), card)
        self.assertEqual(self.window.card_key, key)
        hover = self.window.overlay.rows[-1]
        self.assertEqual(hover["follow_pointer"], [100, 100])

    def test_reading_for_a_pointer_that_has_moved_away_is_rejected(self):
        self.window.reader.pointer = (700, 700)
        reading = self.reading(shop_hover=False)
        reading["pointerAtRead"] = [100, 100]
        self.window.on_reading(reading)
        self.assertIsNone(self.window.tooltip_result)

    def test_error_for_a_previous_store_is_not_left_on_the_status_line(self):
        self.window.status_label.setText("Price lookup: old item: HTTP Error 400")
        self.window.errors[999] = "HTTP Error 400"
        self.window.on_reading(self.reading(shop_hover=True))
        self.assertNotIn("400", self.window.status_label.text())

    def test_one_button_covers_monitor_selection_start_pause_and_resume(self):
        fresh = LensWindow(Path.cwd(), Path("unused-cache"))
        try:
            self.assertIsNotNone(fresh.screen_index)
            self.assertTrue(fresh.share.isEnabled())
            self.assertEqual(fresh.monitor.count(), len(fresh.screens))
            self.assertFalse(fresh.crop_button.isEnabled())
            self.assertEqual(fresh.reader.starts, 0)
            fresh.monitor.setCurrentIndex(0)
            self.assertTrue(fresh.share.isEnabled())
            self.assertEqual(fresh.share.text(), "Start reading")
            fresh.share.click()
            self.assertEqual(fresh.reader.starts, 1)
            self.assertFalse(fresh.share.isEnabled())
            self.assertEqual(fresh.share.text(), "Starting reading…")
            fresh.reader.image = QImage(800, 800, QImage.Format.Format_RGBA8888)
            fresh.on_image(fresh.reader.image)
            self.assertTrue(fresh.share.isEnabled())
            self.assertEqual(fresh.share.text(), "Pause reading")
            fresh.share.click()
            self.assertEqual(fresh.mode, "paused")
            self.assertEqual(fresh.share.text(), "Resume reading")
            self.assertEqual(fresh.reader.pauses, [True])
            self.assertEqual(fresh.overlay.rows, [])
            fresh.share.click()
            self.assertEqual(fresh.reader.starts, 2)
        finally:
            fresh.close()
            fresh.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_price_hotkey_is_independent_of_screen_reading_and_exp(self):
        self.window.hotkeys.activated.emit()
        self.assertEqual(self.window.mode,'live')
        self.assertFalse(self.window.prices_enabled)
        self.assertFalse(self.window.reader.prices_enabled)
        self.window.hotkeys.activated.emit()
        self.assertTrue(self.window.prices_enabled)
        self.window.share.click()
        self.assertEqual(self.window.mode,'paused')


    def test_pause_ignores_pending_readings_and_does_not_refresh_prices(self):
        self.window.on_reading(self.reading(shop_hover=True))
        count = len(self.window.service.requests)
        self.window.pause()
        self.window.on_reading(self.reading(shop_hover=False))
        self.window.tick()
        self.assertIsNone(self.window.tooltip_result)
        self.assertEqual(len(self.window.service.requests), count)
        self.assertFalse(self.window.overlay.rows)

    def test_key_combination_is_configurable_and_saved(self):
        def edit():
            dialog = self.window.findChild(QDialog, "hotkeyDialog")
            editor = dialog.findChild(QKeySequenceEdit, "shortcut-prices")
            editor.setKeySequence(QKeySequence("Ctrl+Shift+F10"))
            dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Apply).click()
        QTimer.singleShot(0, edit)
        self.window.configure_shortcuts()
        self.assertEqual(self.window.settings.values["hotkey-sequence"], "Ctrl+Shift+F10")
        self.assertTrue(self.window.settings.values["hotkey-enabled"])

    def test_first_run_display_selection_waits_for_explicit_start(self):
        fresh = LensWindow(Path.cwd(), Path("unused-cache"), auto_capture=True)
        try:
            fresh.monitor.setCurrentIndex(0)
            self.app.processEvents()
            self.assertEqual(fresh.reader.starts, 0)
            self.assertEqual(fresh.mode, "idle")
            self.assertEqual(fresh.status_badge.text(), "Ready to start")
            self.assertIn("Click Start reading", fresh.capture_info.text())
            self.assertFalse(fresh.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        finally:
            fresh.close()
            fresh.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_sharing_setup_can_be_canceled_and_late_readings_are_ignored(self):
        self.window.mode = "idle"
        self.window.start_capture()
        from price_lens.capture_platform import uses_system_picker
        self.assertEqual(self.window.status_badge.text(), "Waiting for screen sharing" if uses_system_picker() else "Starting screen reading")
        self.assertFalse(self.window.cancel_setup.isHidden())
        self.window.cancel_setup.click()
        self.window.on_reading(self.reading(shop_hover=True))
        self.assertEqual(self.window.mode, "idle")
        self.assertEqual(self.window.rows, [])
        self.assertEqual(self.window.reader.pauses[-1], False)
        self.assertIn("canceled", self.window.capture_info.text())

    def test_lost_sharing_waits_for_explicit_reconnect(self):
        self.window.show_status("OS capture: user stopped sharing")
        self.assertEqual(self.window.reader.starts, 0)
        self.assertEqual(self.window.status_badge.text(), "Screen reading needs attention")
        self.assertFalse(self.window.recovery_button.isHidden())
        self.window.recovery_button.click()
        self.assertEqual(self.window.reader.starts, 1)

    def test_changing_display_stops_the_old_source_without_opening_another_picker(self):
        from types import SimpleNamespace
        self.window.screens.append(SimpleNamespace(name=lambda:'Other',geometry=lambda:QRect(800,0,800,800),devicePixelRatio=lambda:1))
        self.window.monitor.addItem('Other display',1)
        self.window.monitor.setCurrentIndex(1)
        self.assertEqual(self.window.mode, "idle")
        self.assertEqual(self.window.reader.starts, 0)
        self.assertEqual(self.window.reader.pauses, [False])

    def test_catalog_retry_is_bounded_while_a_request_is_in_progress(self):
        self.window.catalog = None
        self.window.on_error(0, "HTTP Error 503")
        self.assertTrue(self.window.catalog_error)
        for _ in range(500):
            self.window.retry_catalog()
        self.assertEqual(self.window.service.catalog_starts, 2)
        self.assertTrue(self.window.catalog_loading)


    def test_recognised_item_without_reports_is_not_called_unreadable(self):
        self.window.on_reading(self.reading(shop_hover=True))
        now = time.time()
        self.window.on_quote(1, Quote(1, None, now, None, 0, "Test", "", "24h"))
        content = "\n".join(widget.text() for widget in self.window.cards.findChildren(QLabel))
        self.assertIn("Item name recognised", content)
        self.assertIn("No price in the market snapshot", content)
        self.assertNotIn("unreadable", content.lower())

    def test_empty_hover_reference_is_not_left_checking_forever(self):
        self.window.reader.pointer = (100, 100)
        self.window.on_reading(self.reading(shop_hover=False))
        self.window.on_quote(1, Quote(1, None, time.time(), None, 0, "Test", "", "24h"))
        self.assertEqual(len(self.window.overlay.rows), 1)
        self.assertEqual(self.window.overlay.rows[-1]["text"], "FM • source has no market data")

    def test_saved_screenshot_is_labeled_even_without_a_display_selected(self):
        self.window.monitor.setCurrentIndex(-1)
        self.window.mode = "screenshot"
        self.window.render()
        self.assertEqual(self.window.status_badge.text(), "Saved screenshot")
        self.assertFalse(self.window.share.isEnabled())
        self.assertIn("saved image", self.window.capture_info.text())
        self.assertEqual(self.window.overlay.rows, [])


    def test_price_cards_have_no_details_toggle_and_show_observed_sale_time(self):
        self.window.on_reading(self.reading(shop_hover=True))
        now=time.time()
        self.window.on_quote(1,Quote(1,1000,now,now-120,20,'MesoWatch','','24h',basis='observed shop sales'))
        card=next(iter(self.window.card_views.values()))
        self.assertFalse(hasattr(card,'toggle'))
        self.assertIn('Most recent observed sale',card.fields['recent'].text())

    def test_expiration_removes_comparison_inside_the_same_age_bucket(self):
        with patch("price_lens.ui.time.time", return_value=1001):
            self.window.last_screen = 1001
            self.window.on_reading(self.reading(shop_hover=True))
            self.window.on_quote(1, Quote(1, 1000, 101.2, 1000, 20, "Test", "", "24h"))
            previous = self.window.card_key
            self.assertTrue(any("below reference" in widget.text() for widget in self.window.cards.findChildren(QLabel)))
        with patch("price_lens.ui.time.time", return_value=1001.3):
            self.window.render()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            self.assertNotEqual(previous, self.window.card_key)
            content = "\n".join(widget.text() for widget in self.window.cards.findChildren(QLabel))
            self.assertIn("Older reference", content)
            self.assertNotIn("below reference", content)
            self.assertTrue(any("refresh needed" in row["text"] for row in self.window.overlay.rows))

    def test_inventory_hover_outside_open_shop_keeps_both_references_visible(self):
        self.window.on_catalog(Catalog({"items": [{"id": 1, "name": "Example Hat"},
                                                  {"id": 2, "name": "Other Hat"}], "scrolls": []}))
        self.window.reader.pointer = (100, 100)
        reading = self.reading(shop_hover=False,store=True)
        reading["tooltip"]["found"]["name"] = "Other Hat"
        self.window.on_reading(reading)
        self.assertEqual(self.window.tooltip_result['name'], 'Other Hat')
        self.assertEqual(set(self.window.service.visible), {1,2})
        self.assertEqual(len(self.window.overlay.rows), 2)
        self.window.on_pointer(340, 240)
        self.assertIsNone(self.window.tooltip_result)
        self.assertEqual(self.window.service.visible, [1])

    def test_refresh_progress_updates_cards_and_both_overlay_contexts(self):
        for shop in (True,False):
            with self.subTest(shop=shop):
                self.window.reader.pointer = (340,240) if shop else (100,100)
                self.window.on_reading(self.reading(shop_hover=shop))
                now=time.time()
                self.window.on_quote(1,Quote(1,1000,now-1080,now,20,"Test","","24h"))
                self.window.service.states[1]="refreshing"
                self.window.service.state_changed.emit();self.app.processEvents()
                content="\n".join(widget.text() for widget in self.window.cards.findChildren(QLabel))
                self.assertIn("Refreshing market reference",content)
                self.assertEqual(len(self.window.overlay.rows),1)
                row=self.window.overlay.rows[0]
                self.assertIn("18m old",row["text"])
                self.assertIn("refreshing",row["text"])
                self.assertNotEqual(row["color"],"#86ceac")
        self.window.pause()
        self.assertEqual(self.window.service.visible,[])

    def test_recent_lookup_with_old_reports_explains_the_market_data_age(self):
        self.window.on_reading(self.reading(shop_hover=True))
        now = time.time()
        self.window.on_quote(1, Quote(1, 1000, now, now - 90000, 20, "Test", "", "24h"))
        self.assertIn("old market reports", self.window.overlay.rows[0]["text"])
        self.assertNotIn("EXPIRED", self.window.overlay.rows[0]["text"])

    def test_hidden_labels_can_be_restored_without_reconnecting(self):
        self.window.on_reading(self.reading(shop_hover=True))
        self.window.labels_check.setChecked(False)
        self.window.on_pointer(100, 100)
        self.assertFalse(self.window.reader.tooltip_enabled)
        self.assertIsNone(self.window.reader.pointer)
        self.assertEqual(self.window.overlay.rows, [])
        self.assertEqual(self.window.recovery_button.text(), "Show price labels")
        self.window.recovery_button.click()
        self.assertTrue(self.window.labels_enabled)
        self.assertTrue(self.window.reader.tooltip_enabled)
        self.assertEqual(self.window.reader.starts, 0)

    def test_mismatched_references_never_reach_overlay_or_success_message(self):
        self.window.on_reading(self.reading(shop_hover=True))
        now = time.time()
        valid = Quote(1, 987654, now, now, 20, "Test", "", "24h")
        for change in ({"world": "Other World"}, {"game_id": 2}, {"condition": "scrolled"}, {"per_set": True}):
            with self.subTest(change=change):
                self.window.on_quote(1, replace(valid, **change))
                self.assertFalse(self.window.first_price_seen)
                self.assertNotIn("987,654", "\n".join(row["text"] for row in self.window.overlay.rows))
                self.assertIn("0 market references ready", self.window.summary.text())

    def test_single_display_dropdown_and_three_feature_tabs(self):
        self.assertFalse(hasattr(self.window,'display_map'))
        self.window.monitor.setCurrentIndex(0)
        self.assertIsNotNone(self.window.screen_index)
        self.assertEqual([self.window.tabs.tabText(i) for i in range(3)],['Prices','EXP/Meso Tracking','Translation'])
        self.assertEqual(self.window.search_panel.parentWidget(),self.window.prices_page)
        self.assertFalse(self.window.exp_enabled)
        for i in range(3):
            self.window.tabs.setCurrentIndex(i);self.app.processEvents()
            self.assertFalse(self.window.shortcuts_button.isHidden())
