"""Bounded, source-local translation placement. Geometry only; no capture or Qt."""
from dataclasses import dataclass
import math
import time


@dataclass(frozen=True)
class Box:
    x:int
    y:int
    width:int
    height:int

    @property
    def right(self):return self.x+self.width
    @property
    def bottom(self):return self.y+self.height
    @property
    def centre(self):return self.x+self.width/2,self.y+self.height/2
    def tuple(self):return self.x,self.y,self.width,self.height
    def overlap(self,other):
        return max(0,min(self.right,other.right)-max(self.x,other.x))*max(0,min(self.bottom,other.bottom)-max(self.y,other.y))
    def padded(self,amount):return Box(self.x-amount,self.y-amount,self.width+2*amount,self.height+2*amount)
    def inside(self,bounds):
        return (self.x>=bounds.x and self.y>=bounds.y and self.right<=bounds.right and self.bottom<=bounds.bottom)


def box(value):
    if isinstance(value,Box):return value
    return Box(*(int(part) for part in value))


def fitted(rect,bounds):
    width=min(rect.width,max(1,bounds.width-4));height=min(rect.height,max(1,bounds.height-4))
    return Box(max(bounds.x+2,min(rect.x,bounds.right-width-2)),
               max(bounds.y+2,min(rect.y,bounds.bottom-height-2)),width,height)


def distance(first,second):
    return math.hypot(max(first.x-second.right,second.x-first.right,0),
                      max(first.y-second.bottom,second.y-first.bottom,0))


@dataclass(frozen=True)
class Placement:
    rect:Box
    source:Box
    side:str
    seen:float


class TranslationLayout:
    GAP=5
    HYSTERESIS=18
    KEEP_SECONDS=3

    def __init__(self):self.states={};self.last_signature=None;self.last_result={}

    @staticmethod
    def projected(previous,source,width,height):
        old,anchor=previous.rect,previous.source
        x=old.x+source.x-anchor.x;y=old.y+source.y-anchor.y
        if previous.side=='right':x=source.right+old.x-anchor.right
        elif previous.side=='left':x=source.x-(anchor.x-old.right)-width
        elif previous.side=='below':y=source.bottom+old.y-anchor.bottom
        elif previous.side=='above':y=source.y-(anchor.y-old.bottom)-height
        return Box(x,y,width,height)

    def candidates(self,source,width,height,bounds,obstacles,previous):
        gap=self.GAP
        xs={source.x,round(source.centre[0]-width/2),bounds.x+2,bounds.right-width-2}
        ys={source.y,round(source.centre[1]-height/2),bounds.y+2,bounds.bottom-height-2}
        for other in obstacles:
            xs.update((other.x-width-gap,other.right+gap))
            ys.update((other.y-height-gap,other.bottom+gap))
        # Only nearby edge alignments are useful. Bound work even in a crowded
        # frame; do not turn placement into an unbounded screen packing search.
        xs=sorted(xs,key=lambda x:(abs(x-source.x),x))[:16]
        ys=sorted(ys,key=lambda y:(abs(y-source.y),y))[:16]
        candidates=[]
        if previous:candidates.append((self.projected(previous,source,width,height),previous.side))
        for side,x in (('right',source.right+gap),('left',source.x-width-gap)):
            candidates.extend((Box(x,y,width,height),side) for y in ys)
        for side,y in (('below',source.bottom+gap),('above',source.y-height-gap)):
            candidates.extend((Box(x,y,width,height),side) for x in xs)
        # Crossed obstacle edges give a nearby diagonal escape when all four
        # immediate sides are occupied. Keep the closest combinations only.
        diagonal=sorted(((x,y) for x in xs for y in ys),key=lambda p:abs(p[0]-source.x)+abs(p[1]-source.y))[:32]
        candidates.extend((Box(x,y,width,height),'offset') for x,y in diagonal)
        result={}
        for rect,side in candidates:
            rect=fitted(rect,bounds);result.setdefault(rect,side)
        return list(result.items())

    def place(self,messages,occupied=(),*,now=None):
        now=time.monotonic() if now is None else now
        self.states={key:value for key,value in self.states.items() if 0<=now-value.seen<=self.KEEP_SECONDS}
        messages=list(messages)[:24]
        sources=[box(source).padded(4) for message in messages for source in (message.get('sources') or (message['source'],))]
        occupied=[box(rect) for rect in occupied]
        signature=(tuple(sorted(((row['key'],tuple(row['source']),tuple(row['bounds']),tuple(row['size']),row.get('visible',True),
                    tuple(tuple(source) for source in (row.get('sources') or (row['source'],)))) for row in messages),key=lambda row:str(row[0]))),tuple(occupied))
        if signature==self.last_signature and all(key in self.states for key in self.last_result):
            result={key:Placement(value.rect,value.source,value.side,now) for key,value in self.last_result.items()}
            self.states.update(result);self.last_result=result;return result
        placed=[];result={}
        # Preserve existing cards' priority even if OCR changes output order.
        ordered=sorted(messages,key=lambda row:(0 if not row.get('visible',True) and row['key'] in self.states else 1,
                                               row['key'] not in self.states,str(row['key'])))
        for message in ordered:
            key=message['key'];bounds=box(message['bounds']);width,height=message['size']
            source=box(message['source']);previous=self.states.get(key)
            visible=message.get('visible',True)
            if not visible and previous:
                rect=fitted(Box(previous.rect.x,previous.rect.y,width,height),bounds)
                placement=Placement(rect,previous.source,previous.side,now)
            else:
                def score(rect,side):
                    card_overlap=sum(rect.overlap(other.padded(2)) for other in placed)
                    source_overlap=sum(rect.overlap(other) for other in sources)
                    occupied_overlap=sum(rect.overlap(other) for other in occupied)
                    centre=rect.centre;anchor=source.centre
                    near=distance(rect,source)+.04*(abs(centre[0]-anchor[0])+abs(centre[1]-anchor[1]))
                    near+=dict(right=0,left=2,below=12,above=14,offset=16)[side]
                    near+=.06*abs(rect.y-source.y) if side in ('right','left') else .06*abs(rect.x-source.x)
                    return bool(card_overlap),card_overlap*4+source_overlap*2+occupied_overlap,near
                retained=fitted(self.projected(previous,source,width,height),bounds) if previous else None
                old_score=score(retained,previous.side) if retained else None
                if retained and old_score[:2]==(False,0) and distance(retained,source)<=self.GAP+self.HYSTERESIS:
                    # The common tracking/unchanged-frame path is already close
                    # and clear. Do not rerun packing for every IPC heartbeat.
                    rect,side=retained,previous.side
                else:
                    choices=self.candidates(source,width,height,bounds,(*sources,*occupied,*placed),previous)
                    rect,side=min(choices,key=lambda entry:score(*entry))
                    best_score=score(rect,side)
                    if retained and old_score[:2]==best_score[:2] and old_score[2]<=best_score[2]+self.HYSTERESIS:
                        rect,side=retained,previous.side
                placement=Placement(rect,source,side,now)
            result[key]=placement;placed.append(placement.rect);self.states[key]=placement
        if len(self.states)>64:
            self.states=dict(sorted(self.states.items(),key=lambda row:row[1].seen,reverse=True)[:64])
        self.last_signature=signature;self.last_result=result
        return result
