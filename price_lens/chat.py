"""Bounded local chat scans, short disappearance grace and in-memory history."""
import json
from pathlib import Path
import time

from PySide6.QtCore import QObject,QProcess,QProcessEnvironment,QRect,Signal,Qt,QTimer
from PySide6.QtGui import QImage


def stamp(image, box):
    rect=QRect(*box)
    if not image.rect().contains(rect):return b''
    sample=image.copy(rect).scaled(24,24,Qt.AspectRatioMode.IgnoreAspectRatio,
                 Qt.TransformationMode.FastTransformation).convertToFormat(QImage.Format.Format_Grayscale8)
    return bytes(sample.constBits())


def difference(a,b):
    if not a or len(a)!=len(b):return 1.0
    ink=[(x,y) for x,y in zip(a,b) if min(x,y)<210]
    values=ink if ink else list(zip(a,b))
    return sum(abs(x-y)>30 for x,y in values)/len(values)


class ChatTranslation(QObject):
    changed=Signal()
    status=Signal(str)
    frame_requested=Signal()

    def __init__(self,root,parent=None):
        super().__init__(parent)
        self.root=Path(root);self.process=None;self.ready=False;self.busy=False;self.identity=0
        self.buffer=b'';self.cards=[];self.history=[];self.frame=QImage();self.region=QRect();self.started=0
        self.enabled=False;self.scan_seconds=4.0;self.linger_seconds=1.5;self.generation=0
        self.watching=False;self.waiting=False;self.until=0;self.hits=0;self.serial=0
        self.notice='';self.notice_until=0;self.last_track=0;self.last_image=None
        self.cadence=QTimer(self);self.cadence.setSingleShot(True);self.cadence.setInterval(250);self.cadence.timeout.connect(self.want_frame)
        self.window_timer=QTimer(self);self.window_timer.setSingleShot(True);self.window_timer.timeout.connect(self.finish_scan)
        self.deadline=QTimer(self);self.deadline.setSingleShot(True);self.deadline.setInterval(4000);self.deadline.timeout.connect(self.timeout)
        self.notice_timer=QTimer(self);self.notice_timer.setSingleShot(True);self.notice_timer.timeout.connect(self.clear_notice)

    @property
    def active(self):return self.watching or self.waiting

    @property
    def has_overlay(self):return bool(self.cards or self.active or self.busy or time.monotonic()<self.notice_until)

    def configure(self,scan,linger):
        self.scan_seconds=max(1.0,min(10.0,float(scan)))
        self.linger_seconds=max(0.0,min(5.0,float(linger)))

    def enable(self,enabled):
        self.enabled=enabled
        if not enabled:self.close();return
        if self.process is not None:return
        models=self.root/'models/korean-chat'
        if not (models/'rec.onnx').is_file():
            self.announce('Local Korean models are missing. Reinstall Lupin.');return
        import sys
        process=QProcess(self);self.process=process;process.setWorkingDirectory(str(self.root))
        env=QProcessEnvironment.systemEnvironment()
        for name,value in (('OPENBLAS_NUM_THREADS','1'),('OMP_NUM_THREADS','2'),('OMP_WAIT_POLICY','PASSIVE')):env.insert(name,value)
        process.setProcessEnvironment(env);process.readyReadStandardOutput.connect(self.receive)
        process.readyReadStandardError.connect(lambda:process.readAllStandardError())
        process.errorOccurred.connect(lambda *_:self.abort_scan('The local Korean worker could not start.'))
        process.finished.connect(self.finished)
        self.status.emit('Loading local Korean translator…')
        process.start(sys.executable,['-B','-m','price_lens.chat_worker',str(models)])

    def start_scan(self):
        self.identity+=1;self.generation+=1
        if self.busy and self.process is not None:
            self.process.write((json.dumps({'cancel_before':self.identity})+'\n').encode())
        self.hits=0;self.notice='';self.notice_until=0;self.notice_timer.stop()
        if not self.ready:
            if self.process is None:
                self.announce('The local translator is unavailable. Enable translation to retry.');return
            self.waiting=True;self.status.emit('Loading translator…');self.changed.emit();return
        self.waiting=False;self.watching=True;self.until=time.monotonic()+self.scan_seconds
        self.status.emit('Scanning Korean…')
        self.window_timer.start(round(self.scan_seconds*1000));self.want_frame();self.changed.emit()

    def want_frame(self):
        if not self.enabled or not self.watching:return
        if time.monotonic()>=self.until:self.finish_scan();return
        if not self.busy:self.frame_requested.emit()
        if self.watching:self.cadence.start()

    def finish_scan(self):
        self.watching=self.waiting=False;self.cadence.stop();self.window_timer.stop()
        if not self.busy:
            if not self.hits:self.announce('No readable Korean found')
            else:self.status.emit('Scan complete · recent messages remain below');self.changed.emit()
        else:self.changed.emit()

    def abort_scan(self,message):
        self.watching=self.waiting=False;self.cadence.stop();self.window_timer.stop();self.announce(message)

    def announce(self,message):
        self.notice=message;self.notice_until=time.monotonic()+2.5;self.notice_timer.start(2500)
        self.status.emit(message);self.changed.emit()

    def clear_notice(self):
        self.notice='';self.notice_until=0
        self.status.emit('Ready · local Korean translation' if self.enabled and self.ready else 'Translation disabled')
        self.changed.emit()

    def finished(self,*_):
        self.ready=self.busy=False;self.deadline.stop()
        if self.enabled:self.abort_scan('Local translator stopped. Toggle translation off and on to restart.')

    def receive(self):
        if self.process is None:return
        self.buffer+=bytes(self.process.readAllStandardOutput())
        if len(self.buffer)>1024*1024:self.close();self.announce('Local translator response was too large.');return
        while b'\n' in self.buffer:
            line,self.buffer=self.buffer.split(b'\n',1)
            try:message=json.loads(line)
            except ValueError:continue
            if message.get('ready'):
                self.ready=True;self.status.emit('Ready · local Korean translation')
                if self.waiting:self.start_scan()
                continue
            if message.get('error'):
                self.busy=False;self.deadline.stop();self.abort_scan(message['error']);continue
            if message.get('id')!=self.identity:
                if message.get('done'):
                    self.busy=False;self.deadline.stop();self.frame=QImage()
                    if self.watching:self.cadence.start(0)
                continue
            if message.get('row') and time.monotonic()-self.started<2.5:self.accept_row(message['row'])
            if message.get('done'):
                self.busy=False;self.deadline.stop();self.frame=QImage();self.hits+=message['done']['count']
                if self.watching:self.status.emit('Scanning Korean…');self.cadence.start()
                elif not self.hits:self.announce('No readable Korean found')
                else:self.status.emit('Scan complete · recent messages remain below')
                self.changed.emit()

    def accept_row(self,supplied):
        row=dict(supplied);box=row['box'];row['stamp']=stamp(self.frame,box)
        row['box']=[box[0]+self.region.x(),box[1]+self.region.y(),box[2],box[3]]
        same=[c for c in self.cards if (c['speaker'],c['original'])==(row['speaker'],row['original']) and
              abs(c['box'][0]-row['box'][0])+abs(c['box'][1]-row['box'][1])<160]
        if len(same)==1:
            card=same[0];identity=card['id'];card.update(row);card['id']=identity;card['gone_at']=None
        else:
            # Replace changed text at the same bubble; preserve old text in history.
            rect=QRect(*row['box'])
            self.cards=[c for c in self.cards if rect.intersected(QRect(*c['box'])).width()*rect.intersected(QRect(*c['box'])).height()<rect.width()*rect.height()*.65]
            self.serial+=1;row.update(id=self.serial,gone_at=None);self.cards.append(row)
            self.history.append({k:row[k] for k in ('speaker','original','text','note')});self.history=self.history[-30:]
        self.cards=self.cards[-8:];self.last_track=0;self.changed.emit()

    def request(self,image,region,exclude=()):
        if not self.ready or self.busy:return False
        region=region.intersected(image.rect())
        if region.width()<16 or region.height()<16:return False
        if region.width()*region.height()*3>32*1024*1024:self.abort_scan('Limit the translation reading area in Settings.');return False
        self.frame=image.copy(region);self.region=QRect(region);crop=self.frame.convertToFormat(QImage.Format.Format_RGB888)
        data=bytes(crop.constBits());self.identity+=1
        request={'id':self.identity,'generation':self.generation,'width':crop.width(),'height':crop.height(),'stride':crop.bytesPerLine(),
                 'exclude':[[r[0]-region.x(),r[1]-region.y(),r[2],r[3]] for r in exclude]}
        self.started=time.monotonic();self.busy=True
        self.process.write((json.dumps(request)+'\n').encode());self.process.write(data);self.deadline.start()
        self.status.emit('Translating…');self.changed.emit();return True

    def timeout(self):
        if self.busy:self.close();self.announce('Local scan timed out. Toggle translation off and on to retry.')

    def locate(self,image,card):
        box=card['box'];old=card['stamp']
        if difference(stamp(image,box),old)<=.035:return box
        best=(1.0,None)
        # Bounded local matching of already translated pixels, never player/game objects.
        offsets=[(d,0) for d in (-32,-16,-8,8,16,32)]+[(0,d) for d in (-32,-16,-8,8,16,32)]+[(x,y) for x in (-16,16) for y in (-16,16)]
        for dx,dy in offsets:
            candidate=[box[0]+dx,box[1]+dy,box[2],box[3]];score=difference(stamp(image,candidate),old)
            if score<best[0]:best=(score,candidate)
        if best[1] is None:return None
        # Refine the best nearby position without a full-scene search.
        centre=best[1]
        for dx,dy in ((x,y) for x in (-4,-2,0,2,4) for y in (-4,-2,0,2,4)):
            candidate=[centre[0]+dx,centre[1]+dy,box[2],box[3]];score=difference(stamp(image,candidate),old)
            if score<best[0]:best=(score,candidate)
        return best[1] if best[0]<=.035 else None

    def annotations(self,image,sx,sy,bounds,occupied=()):
        rows=[];now=time.monotonic()
        if now-self.last_track>=.2 and image.cacheKey()!=self.last_image:
            self.last_track=now;self.last_image=image.cacheKey();keep=[]
            for card in self.cards:
                found=self.locate(image,card)
                if found is not None:card['box']=found;card['gone_at']=None
                elif card.get('gone_at') is None:card['gone_at']=now
                if card.get('gone_at') is None or now-card['gone_at']<self.linger_seconds:keep.append(card)
            self.cards=keep
        self.cards=[c for c in self.cards if c.get('gone_at') is None or now-c['gone_at']<self.linger_seconds]
        for card in self.cards:
            box=card['box']
            rows.append({'kind':'translation','key':f"chat:{card['id']}",'x':round((box[0]+box[2])*sx)+8,'y':round(box[1]*sy),
                         'bounds':bounds,'source_box':[round(box[0]*sx),round(box[1]*sy),round(box[2]*sx),round(box[3]*sy)],
                         'animate_move':True,'name':card['speaker'] or 'Korean message',
                         'note':'Partial translation · check original' if 'Partial' in card['note'] else 'Numbers uncertain · original retained' if 'uncertain' in card['note'] else '',
                         'text':card['text'],'original':card['original'],'color':'#e3e9f2'})
        message='Loading translator…' if self.waiting else 'Translating…' if self.busy else f'Scanning Korean… {max(0,self.until-now):.0f}s' if self.watching else self.notice if now<self.notice_until else ''
        if message:
            from .overlay_layout import corner_offset
            rows.append({'kind':'translation_status','key':'chat:status','name':'Korean translation','text':message,'color':'#b8d6f2',
                         'x':bounds[0]+bounds[2]-4,'y':bounds[1]+bounds[3]-4,
                         'anchor':'bottom_right','bottom_offset':corner_offset(bounds,occupied),
                         'bounds':bounds})
        return rows

    def clear(self):
        self.identity+=1;self.cards=[];self.history=[];self.watching=self.waiting=False
        if self.busy and self.process is not None:self.process.write((json.dumps({'cancel_before':self.identity})+'\n').encode())
        self.cadence.stop();self.window_timer.stop();self.notice_timer.stop();self.notice='';self.notice_until=0;self.changed.emit()

    def close(self):
        self.enabled=False;self.clear();self.ready=self.busy=False;self.deadline.stop();self.frame=QImage()
        if self.process is not None:
            process=self.process;self.process=None;process.blockSignals(True);process.closeWriteChannel()
            if not process.waitForFinished(200):process.kill();process.waitForFinished(1000)
            process.setParent(None)
            process.deleteLater()
        self.buffer=b''
