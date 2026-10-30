"""Independent, input-transparent OS window. Only receives our own drawing commands."""
import json
import math
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Qt, QRect, QPoint, QPointF, QTimer, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QCursor, QRegion,QFontDatabase,QPolygonF,QLinearGradient,QPainterPath
from PySide6.QtWidgets import QApplication, QWidget
from .number_motion import NumberRoll
from . import gui_currency
from .fonts import interface_font,interface_family
from .overlay_layout import TRACKING_HEIGHT


class CommandPipe(QObject):
    command = Signal(bytes)
    closed = Signal()

    def listen(self):
        for line in sys.stdin.buffer:
            self.command.emit(line)
        self.closed.emit()


class AnnotationWindow(QWidget):
    korean_family=None
    OCCLUSION_RELEASE_MS=200

    def __init__(self, start_listener=True):
        flags = (Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                 | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowTransparentForInput
                 | Qt.WindowType.WindowDoesNotAcceptFocus)
        if sys.platform.startswith("linux"):
            # Keep the compositor from shifting a full-screen tool window below
            # KDE's top panel. This flag applies only to our own XWayland window.
            flags |= Qt.WindowType.X11BypassWindowManagerHint
        super().__init__(None, flags)
        self.setWindowTitle("Lupin — screen labels")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.rows = []
        self.retiring = []
        self.last_command = 0
        self.last_pointer = None
        self.reduce_motion = False
        self.watch_events = {}
        self.watch_star = QPolygonF([QPointF(math.cos(-math.pi/2+i*math.pi/5)*(5 if i%2==0 else 2.3),
                                            math.sin(-math.pi/2+i*math.pi/5)*(5 if i%2==0 else 2.3)) for i in range(10)])
        self.price_font = interface_font(12,QFont.Weight.DemiBold)
        self.name_font = interface_font(10)
        self.tracking_gain_font = interface_font(24,QFont.Weight.DemiBold)
        self.translation_font=QFont(self.price_font);self.translation_font.setPixelSize(13)
        self.original_font=QFont(self.name_font);self.original_font.setPixelSize(11)
        if self.korean_family is None:
            identity=QFontDatabase.addApplicationFont(str(Path(__file__).parent/"resources/fonts/Maplestory-Bold.ttf"))
            families=QFontDatabase.applicationFontFamilies(identity)
            type(self).korean_family=families[0] if families else ""
        if self.korean_family:
            for font in (self.name_font,self.price_font,self.tracking_gain_font,self.original_font,self.translation_font):
                font.setFamilies([interface_family(),self.korean_family])
        self.tracking_label_font=QFont(self.name_font)
        self.tracking_label_font.setWeight(QFont.Weight.Bold)
        self.pointer_timer = QTimer(self)
        self.pointer_timer.setInterval(100)
        self.pointer_timer.timeout.connect(self.report_pointer)
        self.pipe = CommandPipe(self)
        self.pipe.command.connect(self.read_command)
        self.pipe.closed.connect(QApplication.quit)
        if start_listener:
            self.listener = threading.Thread(target=self.pipe.listen, name="drawing-commands", daemon=True)
            self.listener.start()
        self.watchdog = QTimer(self)
        self.watchdog.setInterval(2000)
        self.watchdog.timeout.connect(self.expire)
        self.watchdog.start()

    def read_command(self, line):
        import time
        try:
            state = json.loads(line)
            if state.get("quit"):
                QApplication.quit()
                return
            self.last_command = time.monotonic()
            self.reduce_motion = bool(state.get("reduce_motion"))
            if state.get("hover_enabled") and not self.pointer_timer.isActive():
                self.last_pointer = None
                self.pointer_timer.start()
            elif not state.get("hover_enabled"):
                self.pointer_timer.stop()
            previous = {self.row_key(row): row for row in self.rows + self.retiring}
            previous_boxes = {key: self.label_rect(row, QCursor.pos()) for key, row in previous.items()}
            geometry = state.get("geometry")
            if geometry:
                self.setGeometry(*geometry)
            incoming = state.get("rows", [])[:24]
            self.rows = []
            self.retiring = []
            metrics = QFontMetrics(self.price_font)
            for supplied in incoming:
                key = self.row_key(supplied)
                old = previous.pop(key, None)
                old_target = (old["x"], old["y"]) if old else None
                old_text = old.get("text") if old else None
                old_content=old.get('content_id',old_text) if old else None
                old_alpha_target=old.get('_target_alpha',1.0) if old else None
                row = old if old is not None else supplied
                row['occlusion']=supplied.get('occlusion')
                row['secondary']=supplied.get('secondary','')
                if 'follow_pointer' not in supplied:
                    for field in ('follow_pointer','pointer_region','_cursor_offset'):row.pop(field,None)
                row.update(supplied)
                row["watched"] = bool(supplied.get("watched"))
                row.pop("_retired_rect", None)
                row["_width"] = min(350, max(230,metrics.horizontalAdvance(row["text"])+20,
                                             max((metrics.horizontalAdvance(line) for line in row.get('extra','').splitlines()),default=0)+20,
                                             metrics.horizontalAdvance(row.get("name",""))+20))
                if row.get('kind')=='tracking':
                    row['_width']=max(180,min(350,int(row.get('tracking_width',296))))
                    row['_height']=max(TRACKING_HEIGHT,min(160,int(row.get('tracking_height',TRACKING_HEIGHT))))
                if row.get("kind")=="translation":
                    row["_width"]=min(360,max(180,row.get("bounds",[0,0,360,0])[2]-8))
                    wrap=Qt.TextFlag.TextWordWrap|Qt.AlignmentFlag.AlignLeft
                    inner=QRect(0,0,row["_width"]-20,2000)
                    row["_english_height"]=min(120,QFontMetrics(self.translation_font).boundingRect(inner,int(wrap),row["text"]).height())
                    row["_original_height"]=min(84,QFontMetrics(self.original_font).boundingRect(inner,int(wrap),row.get("original","")).height())
                    row["_height"]=row["_english_height"]+row["_original_height"]+46+(16 if row.get('note') else 0)
                    if row.get('source_box'):
                        source=QRect(*row['source_box']);bounds=QRect(*row['bounds'])
                        width=min(row['_width'],bounds.width()-4);height=min(row['_height'],bounds.height()-4)
                        positions=[(source.right()+8,source.top()),(source.left()-width-8,source.top()),
                                   (source.left(),source.bottom()+8),(source.left(),source.top()-height-8)]
                        choices=[QRect(max(bounds.left()+2,min(x,bounds.right()-width-2)),
                                       max(bounds.top()+2,min(y,bounds.bottom()-height-2)),width,height) for x,y in positions]
                        def overlap(rect):
                            total=0
                            for supplied in incoming:
                                if supplied.get('source_box'):
                                    hit=rect.intersected(QRect(*supplied['source_box']));total+=hit.width()*hit.height()
                            return total
                        target=min(choices,key=overlap);row['x'],row['y']=target.x(),target.y()
                if self.reduce_motion:
                    self.dispose_row(row)
                    row["_text_alpha"] = 1.0
                    row.pop("_draw_pos",None)
                if row.get("follow_pointer") is not None:
                    point = row["follow_pointer"]
                    offset = (row["x"] - (point[0] - self.x()), row["y"] - (point[1] - self.y()))
                    row["_cursor_offset"] = row.get("_cursor_offset", offset)
                elif row.get("animate_move") and old_target != (row["x"], row["y"]):
                    target = QPointF(row["x"], row["y"])
                    start = row.get("_draw_pos", QPointF(*old_target)) if old_target else target
                    self.animate_position(row, start, target)
                self.rows.append(row)
                box=self.label_rect(row,QCursor.pos())
                occlusion=row.get('occlusion')
                covered=bool(occlusion and box and box.intersects(QRect(*occlusion)))
                target=self.occlusion_alpha(row,covered)
                row['_target_alpha']=target
                if self.reduce_motion:row['_alpha']=target
                if old_text is not None and old_text != row["text"] and old_content!=row.get('content_id',row['text']) and not self.reduce_motion and not any(c.isdigit() for c in row['text']):
                    self.fade_text(row)
                self.update_numbers(row)
                self.update_watch(row)
                if old is None and not self.reduce_motion:
                    row["_alpha"] = 0.0
                if row.get("_fading_out") or old is None or old_alpha_target!=target:
                    self.fade(row, target)
            current_hover = any(row.get("follow_pointer") is not None for row in self.rows)
            current_shops=[row for row in self.rows if row.get('kind')=='shop']
            for key, row in previous.items():
                box = previous_boxes.get(key)
                # Never trail an old item's reference behind a newly identified one.
                replaced_hover = current_hover and row.get("follow_pointer") is not None
                replaced_shop=row.get('kind')=='shop' and any(
                    (new.get('shop_page') is not None and row.get('shop_page') is not None
                     and new['shop_page']!=row['shop_page']) or
                    (new.get('shop_slot') is not None and new.get('shop_slot')==row.get('shop_slot')
                     and self.row_key(new)!=key) for new in current_shops)
                if not self.reduce_motion and state.get("hover_enabled") and box is not None and not replaced_hover and not replaced_shop:
                    row["_retired_rect"] = box
                    self.retiring.append(row)
                    if not row.get("_fading_out"):
                        self.fade(row, 0.0)
                else:
                    self.dispose_row(row)
            self.pointer_timer.setInterval(16 if any(row.get("follow_pointer") is not None for row in self.rows) else 100)
            if self.rows or self.retiring:
                self.show()
                self.raise_()
            else:
                self.hide()
            self.update()
            if hasattr(self,'listener'):
                boxes=[]
                for row in self.rows+self.retiring:
                    rect=self.label_rect(row,QCursor.pos())
                    if rect is None:continue
                    if row.get('_draw_pos') is not None:
                        target=dict(row);target.pop('_draw_pos',None)
                        endpoint=self.label_rect(target,QCursor.pos())
                        if endpoint is not None:rect=rect.united(endpoint)
                    boxes.append(rect.adjusted(-2,-2,2,2).getRect())
                sys.stdout.buffer.write((json.dumps({'layout':boxes})+'\n').encode());sys.stdout.buffer.flush()
        except (ValueError, TypeError):
            self.rows = []
            self.hide()

    @staticmethod
    def row_key(row):
        return row.get("key", (row.get("name"), row.get("x"), row.get("y")))

    def occlusion_alpha(self,row,covered):
        """Dim immediately; absorb one brief clear sample before reversing."""
        row['_occlusion_requested']=covered
        timer=row.get('_occlusion_release')
        if covered or self.reduce_motion or row.get('kind')!='shop':
            if timer is not None:
                timer.stop();timer.deleteLater();row['_occlusion_release']=None
            return .25 if row.get('kind')=='shop' and covered else 1.0
        if row.get('_target_alpha')!=.25:return 1.0
        if timer is None:
            timer=QTimer(self);timer.setSingleShot(True);timer.setInterval(self.OCCLUSION_RELEASE_MS)
            row['_occlusion_release']=timer
            def release():
                timer.stop()
                if row.get('_occlusion_release') is timer:
                    row['_occlusion_release']=None
                    if row in self.rows and not row.get('_occlusion_requested'):
                        row['_target_alpha']=1.0
                        self.fade(row,1.0)
                timer.deleteLater()
            timer.timeout.connect(release);timer.start()
        return .25

    def update_numbers(self, row):
        rolls=row.setdefault('_rolls',{});animations=row.setdefault('_roll_animations',{})
        values={'text':row['text'],'deal_delta':row.get('deal_delta','')}
        if row.get('kind')=='experience':values['name']=row.get('name','')
        values.update({f'extra:{i}':line for i,line in enumerate(row.get('extra','').splitlines())})
        if row.get('kind')=='tracking':
            values={key:value for key,value in self.tracking_values(row).items() if key not in ('unit','basis')}
        for key in set(rolls)-set(values):
            roll=rolls.pop(key);animation=animations.pop(key,None)
            if animation:animation.stop();animation.deleteLater()
        for key,text in values.items():
            roll=rolls.setdefault(key,NumberRoll())
            if self.reduce_motion:
                animation=animations.pop(key,None)
                if animation:animation.stop();animation.deleteLater()
                roll.set_text(text,False);roll.finish();continue
            if not roll.set_text(text):continue
            previous=animations.pop(key,None)
            if previous:previous.stop();previous.deleteLater()
            animation=QVariantAnimation(self);animations[key]=animation
            animation.setDuration(160);animation.setStartValue(0.0);animation.setEndValue(1.0)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            def advance(value,roll=roll,row=row):
                roll.progress=float(value);self.invalidate_row(row)
            def finish(key=key,animation=animation):
                if animations.get(key) is animation:animations.pop(key,None)
                animation.deleteLater()
            animation.valueChanged.connect(advance);animation.finished.connect(finish);animation.start()

    @staticmethod
    def paint_number(painter,row,key,rect,text,alignment=Qt.AlignmentFlag.AlignVCenter):
        roll=row.get('_rolls',{}).get(key)
        if roll and roll.text==text:roll.paint(painter,rect,alignment)
        else:painter.drawText(rect,alignment,text)

    def invalidate_row(self, row, previous=None):
        box = self.label_rect(row, QCursor.pos())
        dirty = QRegion()
        for rectangle in (previous, box):
            if rectangle is not None:
                dirty |= QRegion(rectangle.adjusted(-4, -4, 4, 4))
        if not dirty.isEmpty():
            self.update(dirty)

    def update_watch(self, row):
        if not row.get("watched") or self.reduce_motion:
            animation = row.pop("_watch_pulse", None)
            if animation:animation.stop();animation.deleteLater()
            row["_watch_level"] = 0.0
            row['_watch_progress'] = 1.0
        if not row.get("watched"):
            return
        token = (self.row_key(row), row.get("watch_event"))
        consumed = token in self.watch_events
        self.watch_events[token] = True
        while len(self.watch_events) > 512:
            self.watch_events.pop(next(iter(self.watch_events)))
        if self.reduce_motion or consumed:
            return
        previous = row.pop("_watch_pulse", None)
        if previous:previous.stop();previous.deleteLater()
        animation = QVariantAnimation(self)
        row["_watch_pulse"] = animation
        animation.setDuration(1600)
        animation.setStartValue(0.0);animation.setEndValue(1.0)
        def changed(value):
            row["_watch_level"] = (1-math.cos(4*math.pi*value))/2
            row['_watch_progress'] = value
            self.invalidate_row(row)
        def finished():
            if row.get("_watch_pulse") is animation:row["_watch_pulse"] = None
            row["_watch_level"] = 0.0
            row['_watch_progress'] = 1.0
            self.invalidate_row(row)
            animation.deleteLater()
        animation.valueChanged.connect(changed)
        animation.finished.connect(finished)
        animation.start()

    def fade(self, row, target):
        if self.reduce_motion:
            row["_alpha"] = target
            row["_fading_out"] = target == 0
            return
        old = row.get("_fade")
        if old is not None:
            old.stop()
            old.deleteLater()
        row["_fading_out"] = target == 0
        animation = QVariantAnimation(self)
        row["_fade"] = animation
        animation.setDuration(90 if target == 0 else 110)
        animation.setStartValue(float(row.get("_alpha", 1.0)))
        animation.setEndValue(target)
        animation.setEasingCurve(QEasingCurve.Type.OutQuad)

        def changed(value):
            row["_alpha"] = value
            self.invalidate_row(row)

        def finished():
            if row.get("_fade") is animation:
                row["_fade"] = None
            if target == 0 and row in self.retiring:
                self.retiring.remove(row)
                self.invalidate_row(row)
                if not self.rows and not self.retiring:
                    self.hide()
            animation.deleteLater()

        animation.valueChanged.connect(changed)
        animation.finished.connect(finished)
        animation.start()

    def fade_text(self,row):
        old=row.get("_text_fade")
        if old:old.stop();old.deleteLater()
        animation=QVariantAnimation(self)
        row["_text_fade"]=animation
        animation.setDuration(100);animation.setStartValue(.6);animation.setEndValue(1.0)
        def changed(value):
            row["_text_alpha"]=value;self.invalidate_row(row)
        animation.valueChanged.connect(changed)
        animation.finished.connect(animation.deleteLater)
        animation.finished.connect(lambda:row.update(_text_fade=None))
        animation.start()

    def animate_position(self, row, start, target):
        old = row.get("_move")
        if old is not None:
            old.stop()
            old.deleteLater()
        row["_draw_pos"] = start
        if start == target:
            row["_move"] = None
            return
        animation = QVariantAnimation(self)
        row["_move"] = animation
        animation.setDuration(95)
        animation.setStartValue(start)
        animation.setEndValue(target)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        def changed(value):
            before = self.label_rect(row, QCursor.pos())
            row["_draw_pos"] = value
            self.invalidate_row(row, before)

        def finished():
            if row.get("_move") is animation:
                row["_move"] = None
            animation.deleteLater()

        animation.valueChanged.connect(changed)
        animation.finished.connect(finished)
        animation.start()

    @staticmethod
    def dispose_row(row):
        timer=row.pop('_occlusion_release',None)
        if timer is not None:timer.stop();timer.deleteLater()
        for key in ("_move", "_fade", "_text_fade", "_watch_pulse"):
            animation = row.get(key)
            if animation is not None:
                animation.stop()
                animation.deleteLater()
                row[key] = None
        for animation in row.get('_roll_animations',{}).values():
            animation.stop();animation.deleteLater()
        row['_roll_animations']={}
        for roll in row.get('_rolls',{}).values():roll.finish()

    def expire(self):
        import time
        if time.monotonic() - self.last_command > 5:
            self.hide()

    def report_pointer(self):
        point = QCursor.pos()  # OS position only; no event hook or input injection.
        coordinates = (point.x(), point.y())
        if coordinates != self.last_pointer:
            old_point = QPoint(*self.last_pointer) if self.last_pointer is not None else point
            self.last_pointer = coordinates
            dirty = QRegion()
            for row in self.rows:
                if row.get("follow_pointer") is not None:
                    for position in (old_point, point):
                        rectangle = self.label_rect(row, position)
                        if rectangle is not None:
                            dirty |= QRegion(rectangle.adjusted(-2, -2, 2, 2))
            if not dirty.isEmpty():
                self.update(dirty)
            try:
                print(json.dumps({"pointer": coordinates}), flush=True)
            except BrokenPipeError:
                QApplication.quit()

    def label_rect(self, row, point):
        if row.get("_retired_rect") is not None:
            return row["_retired_rect"]
        x, y = int(row["x"]), int(row["y"])
        if row.get("follow_pointer") is not None:
            origin = row["follow_pointer"]
            region = row.get("pointer_region")
            if ((region and not QRect(*region).contains(point)) or
                    max(abs(point.x() - origin[0]), abs(point.y() - origin[1])) > 64):
                return None
            dx, dy = row["_cursor_offset"]
            x, y = point.x() - self.x() + dx, point.y() - self.y() + dy
        elif row.get("_draw_pos") is not None:
            position = row["_draw_pos"]
            x, y = round(position.x()), round(position.y())
        width = row["_width"]
        height = 36+17*len(row.get('extra','').splitlines())
        if row.get('kind')=='tracking':height=row['_height']
        if row.get("kind")=="translation":
            height=row["_height"]
            bounds=QRect(*row.get("bounds",[0,0,self.width(),self.height()])).intersected(self.rect())
            width=min(width,max(1,bounds.width()-4));height=min(height,max(1,bounds.height()-4))
            return QRect(max(bounds.x()+2,min(x,bounds.right()-width-2)),
                         max(bounds.y()+2,min(y,bounds.bottom()-height-2)),width,height)
        if row.get("anchor") in ('bottom_left','bottom_right') and row.get("bounds"):
            bounds=QRect(*row["bounds"])
            width=min(width,max(1,bounds.width()-8))
            height=min(height,max(1,bounds.height()-8))
            left=bounds.left()+4+int(row.get('left_offset',0)) if row['anchor']=='bottom_left' else bounds.right()-width-3
            top=max(bounds.top()+4,bounds.bottom()-height-3-int(row.get('bottom_offset',0)))
            return QRect(left,top,width,height)
        if row.get('kind')=='item' and row.get('bounds'):
            bounds=QRect(*row['bounds']).intersected(self.rect())
            width=min(width,max(1,bounds.width()-4))
            return QRect(max(bounds.left()+2,min(x,bounds.right()-width-2)),
                         max(bounds.top()+2,min(y-5,bounds.bottom()-height-2)),width,height)
        x = min(max(2, x), max(2, self.width() - width - 2))
        y = min(max(7, y), max(7, self.height() - 33))
        return QRect(x, y - 5, width, height)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(event.rect(), Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pointer = QCursor.pos()
        for row in self.rows + self.retiring:
            box = self.label_rect(row, pointer)
            if box is None or not box.intersects(event.rect()):
                continue
            painter.setOpacity(float(row.get("_alpha", 1.0)))
            x, y, width = box.x(), box.y() + 5, box.width()
            painter.setFont(self.price_font)
            watched = bool(row.get("watched"))
            if watched:
                painter.setPen(QPen(QColor('#352519'),3.5));painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(box,5,5)
            border = QColor('#aa783d') if watched else QColor(92, 103, 119, 160)
            painter.setPen(QPen(border,1.3 if watched else 1))
            painter.setBrush(QColor(22, 28, 38, 247))
            painter.drawRoundedRect(box, 5, 5)
            if row.get('kind')=='tracking':
                self.paint_tracking(painter,row,box)
                continue
            progress=float(row.get('_watch_progress',1))
            if watched and not self.reduce_motion and 0<progress<1:
                phase=(progress*2)%1
                band=min(76,max(40,box.width()*.26))
                center=box.left()-band+(box.width()+2*band)*phase
                gradient=QLinearGradient(QPointF(center-band/2,box.top()),QPointF(center+band/2,box.bottom()))
                for stop,colour in ((0,QColor(228,178,92,0)),(.3,QColor(225,172,80,38)),
                                    (.5,QColor(245,211,145,100)),(.7,QColor(225,172,80,38)),(1,QColor(228,178,92,0))):
                    gradient.setColorAt(stop,colour)
                painter.save();clip=QPainterPath();clip.addRoundedRect(box.adjusted(2,2,-2,-2),4,4)
                painter.setClipPath(clip,Qt.ClipOperation.IntersectClip);painter.fillRect(box,gradient);painter.restore()
            if row.get("kind")=="translation":
                painter.save();painter.setClipRect(box.adjusted(6,4,-6,-4))
                painter.setFont(self.name_font);painter.setPen(QColor("#b5c9e4"))
                name=painter.fontMetrics().elidedText(row.get("name","Korean chat"),Qt.TextElideMode.ElideRight,width-20)
                painter.drawText(QRect(x+10,box.y()+5,width-20,15),Qt.AlignmentFlag.AlignVCenter,name)
                painter.setFont(self.translation_font);painter.setPen(QColor("#edf1f7"))
                painter.drawText(QRect(x+10,box.y()+24,width-20,row["_english_height"]),int(Qt.TextFlag.TextWordWrap),row["text"])
                line_y=box.y()+29+row['_english_height']
                painter.setPen(QColor('#3b4655'));painter.drawLine(x+10,line_y,x+width-10,line_y)
                painter.setFont(self.original_font);painter.setPen(QColor("#b2bccb"))
                painter.drawText(QRect(x+10,line_y+7,width-20,row["_original_height"]),int(Qt.TextFlag.TextWordWrap),row.get("original",""))
                if row.get('note'):
                    painter.setFont(self.name_font);painter.setPen(QColor('#e4bd7b'))
                    painter.drawText(QRect(x+10,box.bottom()-18,width-20,14),Qt.AlignmentFlag.AlignVCenter,row['note'])
                painter.restore();continue
            if row.get("kind")=="shop":
                color=QColor(row.get("color","#98a3b1"))
                painter.fillRect(QRect(x+2,box.y()+5,3,box.height()-10),color)
                if row.get("deal_delta"):
                    chip=QRect(box.right()-64,box.y()+2,58,14)
                    tint=QColor(color);tint.setAlpha(40)
                    painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(tint);painter.drawRoundedRect(chip,4,4)
                    painter.setPen(color);painter.setFont(self.price_font)
                    self.paint_number(painter,row,'deal_delta',chip,row['deal_delta'],Qt.AlignmentFlag.AlignCenter)
            painter.setFont(self.name_font)
            if row.get("kind")=="experience":painter.setFont(self.price_font)
            painter.setPen(QColor("#c4cbd6"))
            name_inset = 14 if watched else 0
            if watched:
                painter.save();painter.translate(x+14,box.y()+10)
                painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor("#f1c66f"));painter.drawPolygon(self.watch_star)
                painter.restore()
            name_width=width-18-(64 if row.get("deal_delta") else 0)-name_inset
            name = painter.fontMetrics().elidedText(row.get("name", "Unresolved item"), Qt.TextElideMode.ElideRight, name_width)
            self.paint_number(painter,row,'name',QRect(x+9+name_inset,y-3,name_width,14),name)
            painter.setFont(self.price_font)
            painter.setOpacity(float(row.get("_alpha",1.0))*float(row.get("_text_alpha",1.0)))
            painter.setPen(QColor(row.get("color", "#dce1e8")))
            text=painter.fontMetrics().elidedText(row["text"],Qt.TextElideMode.ElideRight,width-18)
            text_rect=QRect(x+9,box.y()+17,width-18,17) if row.get('kind')=='shop' else QRect(x+9,y+10,width-18,18)
            self.paint_number(painter,row,'text',text_rect,text)
            if row.get("extra"):
                painter.setFont(self.name_font);painter.setPen(QColor("#aab5c4"))
                for i,line in enumerate(row['extra'].splitlines()):
                    self.paint_number(painter,row,f'extra:{i}',QRect(x+9,y+28+i*17,width-18,15),line)

    @staticmethod
    def tracking_values(row):
        metrics=[value.removesuffix(' EXP') for _,value in row.get('metrics',[])[:3]]
        metrics+=['—']*(3-len(metrics))
        experience=row.get('key')=='experience'
        unit='%' if experience and metrics[0].endswith('%') else 'EXP' if experience else gui_currency.TOKEN
        if not any(char.isdigit() for char in metrics[0]):unit=''
        gain=metrics[0].removesuffix('%')
        raw=row.get('secondary','').split(' · ',1)[0]
        detail=row.get('footer','')
        if experience and raw:detail+=' · '+raw
        return dict(gain=gain,unit=unit,minute=metrics[1]+'/min',hour=metrics[2]+'/hr',detail=detail,
                    basis=row.get('compact_note') or row.get('basis',''),
                    context=row.get('clock',''))

    def tracking_gain_style(self,box):
        """Scale exceptional totals together while keeping both unit columns fixed."""
        font=QFont(self.tracking_gain_font)
        unit_width=28
        rate_width=90 if box.width()>=240 else 76
        available=max(1,box.width()-12-rate_width-unit_width-4)
        for size in range(self.tracking_gain_font.pixelSize(),9,-1):
            font.setPixelSize(size);metrics=QFontMetrics(font);cell=metrics.horizontalAdvance('0')
            lengths=[]
            for row in self.rows:
                if row.get('kind')!='tracking':continue
                values=self.tracking_values(row);roll=row.get('_rolls',{}).get('gain') or NumberRoll(values['gain'])
                lengths.append(sum(cell if key is not None else metrics.horizontalAdvance(char) for key,char in roll.columns))
            if max(lengths,default=0)<=available:break
        return font,unit_width

    def tracking_columns(self,row,box):
        """Keep totals beside one fixed unit column, below the separate timer."""
        _,unit_width=self.tracking_gain_style(box)
        x,y,w=box.x()+6,box.y(),box.width()-12
        left=x+(90 if box.width()>=240 else 76);unit_x=x+w-unit_width
        title='EXP' if row.get('key')=='experience' else 'MESO'
        heading_x=x+QFontMetrics(self.name_font).horizontalAdvance('+')+2
        heading_width=QFontMetrics(self.tracking_label_font).horizontalAdvance(title)+7
        return dict(gain=QRect(left,y+14,max(1,unit_x-left-4),29),
                    unit=QRect(unit_x,y+14,unit_width,29),
                    heading=QRect(heading_x,y+1,heading_width,13),
                    context=QRect(x+w-54,y+1,54,13))

    def paint_tracking(self,painter,row,box):
        painter.save();painter.setClipRect(box.adjusted(5,1,-5,-1))
        x,y,w=box.x()+6,box.y(),box.width()-12
        values=self.tracking_values(row)
        columns=self.tracking_columns(row,box)
        painter.setFont(self.tracking_label_font);painter.setPen(QColor('#d8dee7'))
        title='EXP' if row.get('key')=='experience' else 'MESO'
        heading=columns['heading']
        painter.drawText(heading,Qt.AlignmentFlag.AlignVCenter,title)
        painter.setFont(self.name_font)
        basis=values['basis'].replace('EXP unreadable','Unreadable')
        basis_left=heading.right()+1
        basis_width=max(0,columns['context'].left()-basis_left-6)
        basis=painter.fontMetrics().elidedText(basis,Qt.TextElideMode.ElideRight,basis_width)
        painter.setPen(QColor('#a5b3c7'));painter.drawText(QRect(basis_left,y+1,basis_width,13),Qt.AlignmentFlag.AlignVCenter,basis)
        gain_font,_=self.tracking_gain_style(box)
        painter.setFont(gain_font);painter.setPen(QColor(row.get('color','#e4bd7b')))
        self.paint_number(painter,row,'gain',columns['gain'],values['gain'],Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
        if values['unit']==gui_currency.TOKEN:
            unit=columns['unit'];gui_currency.paint_icon(painter,QRect(unit.center().x()-8,unit.center().y()-8,16,16))
        else:
            unit_font=QFont(self.price_font)
            if values['unit']=='%':unit_font.setPixelSize(min(22,max(16,gain_font.pixelSize())))
            painter.setFont(unit_font)
            painter.drawText(columns['unit'],Qt.AlignmentFlag.AlignCenter,values['unit'])
        painter.setFont(self.name_font);painter.setPen(QColor('#a5b3c7'))
        self.paint_number(painter,row,'context',columns['context'],values['context'],Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
        rate_width=86 if box.width()>=240 else 72
        for key,top in (('minute',15),('hour',29)):
            self.paint_number(painter,row,key,QRect(x,y+top,rate_width,13),values[key])
        detail=painter.fontMetrics().elidedText(values['detail'],Qt.TextElideMode.ElideRight,w)
        self.paint_number(painter,row,'detail',QRect(x,y+43,w,12),detail)
        painter.restore()


def main():
    from .qt_runtime import configure_qt
    configure_qt()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Lupin labels")
    window = AnnotationWindow()
    app._annotation_window = window
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
