"""Bounded local chat scans, short disappearance grace and in-memory history."""
import json
from pathlib import Path
import time

from PySide6.QtCore import QObject,QProcess,QProcessEnvironment,QRect,Signal,Qt,QTimer
from PySide6.QtGui import QImage

from .chat_tracking import stamp, difference, visible, locate_offset, move_source


class ChatTranslation(QObject):
    changed=Signal()
    status=Signal(str)
    frame_requested=Signal()

    def __init__(self,root,parent=None):
        super().__init__(parent)
        self.root=Path(root);self.process=None;self.ready=False;self.busy=False;self.identity=0
        self.buffer=b'';self.cards=[];self.history=[];self.frame=QImage();self.region=QRect();self.started=0
        self.enabled=False;self.scan_seconds=4.0;self.linger_seconds=1.5
        self.events=[];self.batch_identity=None
        self.watching=False;self.waiting=False;self.until=0;self.hits=0;self.serial=0
        self.notice='';self.notice_until=0;self.last_track=0;self.last_image=None
        self.cadence=QTimer(self);self.cadence.setSingleShot(True);self.cadence.setInterval(250);self.cadence.timeout.connect(self.want_frame)
        self.window_timer=QTimer(self);self.window_timer.setSingleShot(True);self.window_timer.timeout.connect(self.finish_scan)
        self.deadline=QTimer(self);self.deadline.setSingleShot(True);self.deadline.setInterval(4000);self.deadline.timeout.connect(self.timeout)
        self.notice_timer=QTimer(self);self.notice_timer.setSingleShot(True);self.notice_timer.timeout.connect(self.clear_notice)

    @property
    def active(self):return self.watching or self.waiting or self.busy and self.batch_identity==self.identity

    @property
    def phase(self):
        return 'loading' if self.waiting else 'scanning' if self.watching else 'finishing' if self.busy and self.batch_identity==self.identity else 'idle'

    def phase_message(self,now=None):
        now=time.monotonic() if now is None else now
        return ('Loading translator…' if self.waiting else
                f'Scanning Korean… {max(0,self.until-now):.0f}s' if self.watching else
                'Finishing translation…' if self.phase=='finishing' else self.notice if now<self.notice_until else '')

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
        self.identity+=1
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
        if not self.busy or self.batch_identity!=self.identity:
            if not self.hits:self.announce('No readable Korean found')
            else:self.status.emit('Scan complete · recent messages remain below');self.changed.emit()
        else:self.status.emit(self.phase_message());self.changed.emit()

    def abort_scan(self,message):
        self.identity+=1
        if self.busy and self.process is not None:self.process.write((json.dumps({'cancel_before':self.identity})+'\n').encode())
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
                if message.get('id') is not None and message.get('id')!=self.identity:
                    if message.get('id')==self.batch_identity:
                        self.busy=False;self.deadline.stop();self.frame=QImage()
                        if self.watching:self.cadence.start(0)
                    continue
                self.busy=False;self.deadline.stop();self.abort_scan(message['error']);continue
            if message.get('id')!=self.identity:
                if message.get('done'):
                    self.busy=False;self.deadline.stop();self.frame=QImage()
                    if self.watching:self.cadence.start(0)
                continue
            if message.get('row') and time.monotonic()-self.started<2.5:self.accept_row(message['row'])
            if message.get('done'):
                self.busy=False;self.deadline.stop();self.frame=QImage();self.hits+=message['done']['count']
                if self.watching:
                    self.status.emit('Scanning Korean…')
                    # A slow OCR pass has already used the cadence interval.
                    # Keep a small floor; cached passes still run at <=4 Hz.
                    self.cadence.start(max(50,round((.25-(time.monotonic()-self.started))*1000)))
                elif not self.hits:self.announce('No readable Korean found')
                else:self.status.emit('Scan complete · recent messages remain below')
                self.changed.emit()

    def accept_row(self,supplied):
        if not isinstance(supplied,dict):return
        box=supplied.get('box')
        if (not isinstance(box,(list,tuple)) or len(box)!=4 or any(type(v) is not int for v in box)
                or not self.frame.rect().contains(QRect(*box)) or QRect(*box).isEmpty()):return
        if any(not isinstance(supplied.get(key),str) for key in ('speaker','original','text','note')):return
        from .chat_text import message_key
        row={key:supplied[key][:limit] for key,limit in (('speaker',80),('original',500),('text',1000),('note',160))}
        row['source_role']=supplied.get('source_role') if supplied.get('source_role') in ('bubble','chat','store','banner','text') else 'text'
        row['role_verified']=supplied.get('role_verified') is True
        row['stamp']=stamp(self.frame,box)
        row['pixels']=self.frame.copy(QRect(*box)) if box[2]*box[3]<=100000 else None
        for key in ('track_box','speaker_box'):
            supplied_box=supplied.get(key)
            if (isinstance(supplied_box,(list,tuple)) and len(supplied_box)==4
                    and all(type(value) is int for value in supplied_box)
                    and not QRect(*supplied_box).isEmpty() and QRect(*box).contains(QRect(*supplied_box))):
                row[key]=[supplied_box[0]+self.region.x(),supplied_box[1]+self.region.y(),*supplied_box[2:]]
                row['track_stamp' if key=='track_box' else 'speaker_stamp']=stamp(self.frame,supplied_box)
                if key=='track_box' and supplied_box[2]*supplied_box[3]<=100000:
                    row['track_pixels']=self.frame.copy(QRect(*supplied_box))
        if isinstance(supplied.get('ocr_original'),str):row['ocr_original']=supplied['ocr_original'][:500]
        row['box']=[box[0]+self.region.x(),box[1]+self.region.y(),box[2],box[3]]
        now=time.monotonic();same=[]
        for event in self.events:
            exact=event['speaker']==row['speaker'] and message_key(event['original'])==message_key(row['original'])
            sources=event['sources'];roles={source['source_role'] for source in sources}
            local=any(source['source_role']==row['source_role'] and self.same_surface(source,row,now) for source in sources)
            fresh_role=row['source_role'] not in roles and now-event['created_at']<=3
            continuous_role=(row['source_role'] in roles and now-event.get('last_seen',now)<=2
                             and any(source['source_role']==row['source_role'] and self.overlap(QRect(*source['box']),QRect(*row['box']))>=.8
                                     for source in sources))
            cross=(exact and bool(row['speaker']) and row['role_verified'] and (fresh_role or continuous_role)
                   and {row['source_role'],*roles}<={'bubble','chat'} and 'bubble' in {row['source_role'],*roles}
                   and any(source['source_role']!=row['source_role'] and self.visible_source(source) for source in sources))
            fragment=(row['source_role']=='bubble' and row['role_verified'] and 'bubble' in roles
                      and self.fragment_of(event,row) and any(self.same_surface(source,row,now,fragment=True)
                                                             for source in sources if source['source_role']=='bubble' and source.get('role_verified')))
            if exact and local or cross or fragment:same.append((event,fragment))
        if len(same)==1:
            card,is_fragment=same[0]
            # A complete bubble upgrades its own fragment atomically. A later
            # clipped view may move the anchor, but cannot downgrade its words.
            complete=not is_fragment or len(message_key(row['original']))+len(row['speaker'])>=len(message_key(card['original']))+len(card['speaker'])
            if complete:
                for key in ('speaker','original','text','note'):card[key]=row[key]
                card['ocr_original']=row.get('ocr_original','')
        else:
            rect=QRect(*row['box'])
            self.cards=[card for card in self.cards if self.overlap(rect,QRect(*card['box']))<.8]
            self.serial+=1;card={key:row[key] for key in ('speaker','original','text','note')}
            card.update(id=self.serial,created_at=now,sources=[])
            self.events.append(card)
        if row.get('ocr_original'):card['ocr_original']=row['ocr_original']
        source={key:row[key] for key in ('source_role','role_verified','box','stamp','pixels',
                'track_box','track_stamp','track_pixels','speaker_box','speaker_stamp') if key in row}
        source.update(seen_at=now,batch=self.identity,gone_at=None)
        role=row['source_role'];card['sources']=[old for old in card['sources'] if old['source_role']!=role]+[source]
        card['sources']=card['sources'][-2:];card['last_seen']=now
        self.choose_anchor(card,now)
        if not any(old is card for old in self.cards):self.cards.append(card)
        self.cards=self.cards[-8:]
        summary={'id':card['id'],**{key:card[key] for key in ('speaker','original','text','note')}}
        if row.get('ocr_original'):summary['ocr_original']=row['ocr_original']
        index=next((i for i,old in enumerate(self.history) if old.get('id')==card['id']),None)
        if index is None:self.history.append(summary)
        else:self.history[index]=summary
        self.history=self.history[-30:]
        active={card['id'] for card in self.cards}
        self.events=[event for event in self.events if event['id'] in active or now-event['last_seen']<=8][-64:]
        for event in self.events:
            if event['id'] not in active:
                for source in event['sources']:source['pixels']=source['track_pixels']=None
        self.last_track=0;self.changed.emit()

    @staticmethod
    def overlap(first,second):
        hit=first.intersected(second)
        return max(0,hit.width())*max(0,hit.height())/max(1,min(first.width()*first.height(),second.width()*second.height()))

    def visible_source(self,source):
        if source.get('gone_at') is not None:return False
        return visible(self.frame,source,-self.region.x(),-self.region.y())

    def same_surface(self,source,row,now,fragment=False):
        old,new=QRect(*source['box']),QRect(*row['box'])
        if source.get('gone_at') is not None and now-source['gone_at']>.4:return False
        # Two separate equal chat lines in one frame are separate arrivals.
        if source.get('batch')==self.identity and self.overlap(old,new)<.8:return False
        if now-source.get('seen_at',now)>8:return False
        if not fragment:
            nearby=(old.x()-new.x())**2+(old.y()-new.y())**2<160**2
            same=difference(source.get('track_stamp') or source['stamp'],row.get('track_stamp') or row['stamp'])<=.035
            if source.get('speaker_stamp') and row.get('speaker_stamp'):
                same= same and difference(source['speaker_stamp'],row['speaker_stamp'])<=.06
            return nearby and bool(row['speaker'] or self.overlap(old,new)>.8) and same
        if self.overlap(old,new)<.8 or source.get('pixels') is None:return False
        hit=old.intersected(new)
        before=stamp(source['pixels'],hit.translated(-old.x(),-old.y()).getRect())
        after=stamp(self.frame,hit.translated(-self.region.x(),-self.region.y()).getRect())
        return bool(before) and difference(before,after)<=.06

    @staticmethod
    def fragment_of(event,row):
        import re
        from .chat_text import message_key,numbers_preserved,JOBS
        a,b=message_key(event['original']),message_key(row['original'])
        first,second=event['speaker'].casefold(),row['speaker'].casefold()
        related_speaker=first==second or not first or not second or (min(len(first),len(second))>=3 and (first.endswith(second) or second.endswith(first)))
        protected=(numbers_preserved(event['original'],row['original']) and ('?' in a)==('?' in b)
                   and set(re.findall(r'안|못|아니|없|않',a))==set(re.findall(r'안|못|아니|없|않',b))
                   and {job for job in JOBS if job in a}=={job for job in JOBS if job in b})
        return protected and related_speaker and min(len(a),len(b))>=3 and max(len(a),len(b))<=min(len(a),len(b))*3 and (a in b or b in a)

    def choose_anchor(self,card,now):
        sources=card.get('sources') or [card]
        visible=[source for source in sources if source.get('gone_at') is None]
        choices=visible or sources
        source=min(choices,key=lambda source:(source.get('source_role')!='bubble',-source.get('seen_at',0)))
        for key in ('box','stamp','source_role','role_verified'):card[key]=source.get(key)
        card['gone_at']=None if visible else min(source.get('gone_at',now) for source in sources)

    def request(self,image,region,exclude=(),*,contexts=()):
        if not self.ready or self.busy:return False
        region=region.intersected(image.rect())
        if region.width()<16 or region.height()<16:return False
        if region.width()*region.height()*3>32*1024*1024:self.abort_scan('Limit the translation reading area in Settings.');return False
        if not self.region.isEmpty() and self.region!=region:self.cards=[];self.events=[]
        self.frame=image.copy(region);self.region=QRect(region);crop=self.frame.convertToFormat(QImage.Format.Format_RGB888)
        data=bytes(crop.constBits());self.identity+=1
        request={'id':self.identity,'width':crop.width(),'height':crop.height(),'stride':crop.bytesPerLine(),
                 'exclude':[[r[0]-region.x(),r[1]-region.y(),r[2],r[3]] for r in exclude]}
        request['contexts']=[]
        for context in list(contexts)[:8]:
            if not isinstance(context,dict) or context.get('verified') is not True or context.get('role') not in ('store','chat','banner'):continue
            box=context.get('box')
            if not isinstance(box,(list,tuple)) or len(box)!=4 or any(type(v) is not int for v in box):continue
            rect=QRect(*box).intersected(region)
            if rect.isEmpty():continue
            request['contexts'].append({'role':context['role'],'verified':True,
                                       'box':[rect.x()-region.x(),rect.y()-region.y(),rect.width(),rect.height()]})
        self.started=time.monotonic();self.busy=True;self.batch_identity=self.identity
        self.process.write((json.dumps(request)+'\n').encode());self.process.write(data);self.deadline.start()
        self.status.emit(self.phase_message());self.changed.emit();return True

    def timeout(self):
        if self.busy:self.close();self.announce('Local scan timed out. Toggle translation off and on to retry.')

    def locate(self,image,card):
        offset=locate_offset(image,card)
        if offset is None:return None
        move_source(card,*offset)
        return card['box']

    def annotations(self,image,sx,sy,bounds,occupied=(),rectangles=()):
        rows=[];now=time.monotonic()
        if now-self.last_track>=.2 and image.cacheKey()!=self.last_image:
            self.last_track=now;self.last_image=image.cacheKey();keep=[]
            for card in self.cards:
                for source in card.get('sources') or [card]:
                    found=self.locate(image,source)
                    if found is not None:source['box']=found;source['gone_at']=None;source['seen_at']=now
                    elif source.get('gone_at') is None:source['gone_at']=now
                self.choose_anchor(card,now)
                if card.get('gone_at') is None or now-card['gone_at']<self.linger_seconds:keep.append(card)
            self.cards=keep
        self.cards=[c for c in self.cards if c.get('gone_at') is None or now-c['gone_at']<self.linger_seconds]
        for card in self.cards:
            box=card['box']
            rows.append({'kind':'translation','key':f"chat:{card['id']}",'x':round((box[0]+box[2])*sx)+8,'y':round(box[1]*sy),
                         'bounds':bounds,'source_box':[round(box[0]*sx),round(box[1]*sy),round(box[2]*sx),round(box[3]*sy)],
                         'source_boxes':[[round(source['box'][0]*sx),round(source['box'][1]*sy),round(source['box'][2]*sx),round(source['box'][3]*sy)]
                                         for source in card.get('sources',[]) if source.get('gone_at') is None],
                         'source_role':card.get('source_role') or 'text','role_verified':bool(card.get('role_verified')),
                         'source_verified':card.get('gone_at') is None,'anchor_visible':card.get('gone_at') is None,
                         'event_id':card['id'],'source_track_id':card['id'],
                         'animate_move':True,'name':card['speaker'] or 'Korean message',
                         'note':'Partial translation · check original' if 'Partial' in card['note'] else 'Numbers uncertain · original retained' if 'uncertain' in card['note'] else 'Possible OCR correction · check original' if 'OCR correction' in card['note'] else '',
                         'text':card['text'],'original':card['original'],'color':'#e3e9f2'})
        message=self.phase_message(now)
        if message:
            from .overlay_layout import corner_offset
            rows.append({'kind':'translation_status','key':'chat:status','name':'Korean translation','text':message,'color':'#b8d6f2',
                         'x':bounds[0]+bounds[2]-4,'y':bounds[1]+bounds[3]-4,
                         'anchor':'bottom_right','bottom_offset':corner_offset(bounds,occupied,rectangles),
                         'bounds':bounds})
        return rows

    def clear(self):
        self.identity+=1;self.cards=[];self.history=[];self.events=[];self.watching=self.waiting=False;self.batch_identity=None
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
