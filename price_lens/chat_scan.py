"""Incremental full-window scans with a small cache of verified text pixels."""
from collections import OrderedDict
import hashlib
import re
import time

from PySide6.QtCore import QRect

from .chat_text import HANGUL, normalize, supported_ocr_alternative
from .chat_tracking import stamp, locate_offset, move_source


class ScanMemory:
    def __init__(self):
        self.reads=OrderedDict();self.sources=[];self.geometry=None

    def prepare(self,image):
        geometry=(image.width(),image.height())
        if geometry!=self.geometry:self.sources=[];self.geometry=geometry
        now=time.monotonic()
        self.sources=[source for source in self.sources if now-source['seen']<=12][-12:]

    def priority(self,image,exclude,contexts,role_for):
        self.prepare(image);rows=[]
        for source in self.sources[-4:]:
            offset=locate_offset(image,source)
            if offset is None:continue
            dx,dy=offset;move_source(source,dx,dy)
            area=QRect(*source['box'])
            if not image.rect().contains(area) or any(area.intersects(QRect(*r)) for r in exclude):continue
            row=dict(source['row'])
            role,verified=role_for(source['box'],f"{row['speaker']}: {row['original']}",
                row['source_role']=='bubble',contexts,(image.width(),image.height()))
            if (role,verified)!=(row['source_role'],row['role_verified']):continue
            for key in ('box','track_box','speaker_box'):
                if source.get(key):row[key]=list(source[key])
            source['seen']=time.monotonic();rows.append(row)
        return rows

    def remember(self,row,image):
        track=row.get('track_box') or row['box']
        if track[2]*track[3]>100000:return
        reference=stamp(image,track)
        if not reference or max(reference)-min(reference)<45:return
        before=next((source for source in self.sources if source['row']['speaker']==row['speaker']
                     and source['row']['original']==row['original']
                     and source['row']['source_role']==row['source_role']
                     and QRect(*source['box']).intersects(QRect(*row['box']))),None)
        if before:self.sources.remove(before)
        source=dict(box=list(row['box']),track_box=list(track),track_stamp=reference,
            stamp=stamp(image,row['box']),track_pixels=image.copy(QRect(*track)),row=dict(row),seen=time.monotonic(),
            source_role=row['source_role'])
        if row.get('speaker_box'):
            source.update(speaker_box=list(row['speaker_box']),speaker_stamp=stamp(image,row['speaker_box']))
        self.sources.append(source);self.sources=self.sources[-12:]

    def read(self,crop,is_bubble,recognizer,cancelled,deadline):
        from .chat_ocr import lines, pixels, contrast_line
        key=(is_bubble,crop.width(),crop.height(),hashlib.blake2s(pixels(crop).tobytes(),digest_size=16).digest())
        if key in self.reads:
            self.reads.move_to_end(key);return self.reads[key]
        result=[]
        for line,height in (lines(crop) if is_bubble else [(crop,crop.height())]):
            if cancelled():return []
            text,confidence=recognizer.read(line)
            detail=recognizer.detail(line) if hasattr(recognizer,'detail') else {}
            if not is_bubble and confidence<.92 and time.perf_counter()<deadline:
                alternate=contrast_line(line);other=recognizer.read(alternate)
                if other[1]>confidence:
                    text,confidence=other
                    detail=recognizer.detail(alternate) if hasattr(recognizer,'detail') else {}
            if confidence<(.80 if is_bubble else .90):continue
            result.append(dict(text=text,confidence=confidence,rect=[line.offset().x(),line.offset().y(),line.width(),line.height()],
                alternatives=detail.get('alternatives',()),content_right=detail.get('content_right',line.width()),
                meaningful=detail.get('meaningful',bool(re.search(r'[A-Za-z0-9가-힣ㄱ-ㅣ]',text)))))
        self.reads[key]=result
        while len(self.reads)>128:self.reads.popitem(last=False)
        return result


def make_row(image,box,is_bubble,read,translator,contexts,role_for,cancelled):
    if not read:return None
    words=[line['text'] for line in read]
    role,verified=role_for(box,' '.join(words),is_bubble,contexts,(image.width(),image.height()))
    sender=''
    pattern=r'^([^:]{1,24})\s*:\s*(.*)$' if role=='bubble' else r'^\[?([A-Za-z0-9_가-힣]{2,16})\]?\s*:\s*(.+)$' if role=='chat' else r'(?!)'
    prefix=re.match(pattern,words[0])
    if prefix:sender=prefix[1].strip();words[0]=prefix[2]
    original=normalize(' '.join(words))
    if not HANGUL.search(original):return None
    korean=len(HANGUL.findall(original))
    if korean<2 and not re.fullmatch(r'[ㄱ-ㅣ가-힣]{1,8}',original):return None
    if (not is_bubble and korean<4 and korean/max(1,len(re.findall(r'[A-Za-zㄱ-ㅣ가-힣]',original)))<.20
            and not re.search(r'팝니다|삽니다|구함|구해|판매|구매|주세요',original)):return None
    alternatives=[]
    for index,line in enumerate(read):
        if prefix and index==0:continue  # Never correct a speaker identity.
        for text,confidence in line['alternatives']:
            changed=words.copy();changed[index]=text
            alternatives.append((normalize(' '.join(changed)),confidence))
    corrected=supported_ocr_alternative(original,alternatives)
    if cancelled():return None
    english,note=translator.translate(corrected or original)
    if cancelled():return None
    row=dict(box=list(box),speaker=sender,original=corrected or original,text=english,note=note,
             source_role=role,role_verified=verified)
    if corrected:row.update(ocr_original=original,note=note+' · Possible OCR correction')
    # Track the meaningful lines, excluding repeated emphasis and blank padding.
    # The speaker is confirmed separately so equal phrases from nearby players
    # cannot exchange anchors.
    inset=1 if is_bubble else 0;body=[]
    for index,line in enumerate(read):
        x,y,w,h=line['rect'];area=QRect(box[0]+inset+x,box[1]+inset+y,min(w,line['content_right']),h)
        area=area.intersected(QRect(*box))
        if prefix and index==0 and not words[0]:
            if not area.isEmpty():row['speaker_box']=list(area.getRect())
        elif line['meaningful'] and not area.isEmpty():body.append(area)
    if body:
        bounds=body[0]
        for area in body[1:]:bounds=bounds.united(area)
        if bounds.width()*bounds.height()<=100000:row['track_box']=list(bounds.getRect())
    return row


def scan_frame(image,recognizer,translator,emit,role_for,*,budget=.75,cancelled=lambda:False,
               exclude=(),offset=0,contexts=(),memory=None):
    from .chat_ocr import bubbles, text_regions
    start=time.perf_counter();memory=memory or ScanMemory()
    count=readable=korean=processed=0;emitted=[];index=max(0,offset)
    def result(next_):
        return dict(count=count,bubbles=len(bubble_boxes),regions=region_count,next_offset=next_,
            readable=readable,korean=korean,elapsed_ms=round((time.perf_counter()-start)*1000,1))
    bubble_boxes=[];region_count=0
    if cancelled():return result(index)
    for row in memory.priority(image,exclude,contexts,role_for):
        if cancelled():return result(index)
        emit({**row,'elapsed_ms':round((time.perf_counter()-start)*1000,1)})
        emitted.append(row);count+=1
        if time.perf_counter()-start>budget:return result(index)
        if count>=2:break  # Reserve work for newly visible full-window text.
    if cancelled():return result(index)
    bubble_boxes=bubbles(image)
    bubble_candidates=[(box,True) for box in bubble_boxes
        if not any(QRect(*box).intersects(QRect(*r)) for r in exclude)]
    candidates=None
    while not cancelled():
        if count>=4 or processed and time.perf_counter()-start>budget:break
        # The first bubble may produce a result before the comparatively costly
        # full-window colored-text pass. After that, alternate the two queues.
        if index==0 and candidates is None and bubble_candidates:
            box,is_bubble=bubble_candidates[0]
        else:
            if candidates is None:
                generic=[(box,False) for box in text_regions(image,exclude=(*exclude,*bubble_boxes))
                    if not any(QRect(*box).intersects(QRect(*r)) for r in exclude)]
                candidates=[]
                for position in range(max(len(bubble_candidates),len(generic))):
                    if position<len(bubble_candidates):candidates.append(bubble_candidates[position])
                    if position<len(generic):candidates.append(generic[position])
                region_count=len(candidates)
                if index>=len(candidates):index=0
            if not candidates or index>=len(candidates):break
            box,is_bubble=candidates[index]
        index+=1;processed+=1
        if any(max(abs(a-b) for a,b in zip(box,row['box']))<=2 for row in emitted):continue
        x,y,w,h=box;crop=image.copy(x+1,y+1,w-2,h-2) if is_bubble else image.copy(x,y,w,h)
        read=memory.read(crop,is_bubble,recognizer,cancelled,start+budget);readable+=len(read)
        row=make_row(image,box,is_bubble,read,translator,contexts,role_for,cancelled)
        if row is not None:
            korean+=1;memory.remember(row,image)
            emit({**row,'elapsed_ms':round((time.perf_counter()-start)*1000,1)})
            emitted.append(row);count+=1
    return result(0 if candidates is not None and index>=len(candidates) else index)
