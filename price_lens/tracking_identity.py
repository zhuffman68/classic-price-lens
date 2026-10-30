"""Small visual name proofs from captured status-bar pixels, never game identity APIs."""
from dataclasses import dataclass,field
from collections import deque
import hashlib
import math

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QImage

WIDTH, HEIGHT = 128, 20


def glyph_masks(gray,ink,width,height):
    """Separate ink columns before normalization so kerning changes stay local."""
    glyphs=[];start=None
    for x in range(width+1):
        present=x<width and any(ink[y*width+x]>=128 for y in range(height))
        if present and start is None:start=x
        elif not present and start is not None:
            rows=[y for y in range(height) if any(ink[y*width+c]>=96 for c in range(start,x))]
            patch=gray.copy(QRect(start,min(rows),x-start,max(rows)-min(rows)+1)).scaled(
                12,16,Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.SmoothTransformation)
            raw=bytes(patch.constBits());stride=patch.bytesPerLine()
            glyphs.append(bytes(raw[y*stride+c] for y in range(16) for c in range(12)).hex())
            if len(glyphs)>16:return []
            start=None
    return glyphs


def name_proof(image, figures, origin):
    """Locate the name relative to the reader's independently found EXP figures.

    Both regions belong to the same fixed HUD layout. Work on the submitted
    image, not a newer frame that may already show another window or position.
    """
    if not isinstance(figures,dict):return None
    try:
        x,y,w,h=(figures[k] for k in ('x','y','width','height'))
        if any(type(v) is not int for v in (x,y,w,h)) or not 45<=w<=560 or not 6<=h<=80:return None
        sx,sy=w/224,h/32
        if not .9<=sx/sy<=1.1:return None
        area=QRect(round(x-origin.x()-545*sx),round(y-origin.y()+29*sy),round(196*sx),round(22*sy))
        if not image.rect().contains(area):return None
        patch=image.copy(area).convertToFormat(QImage.Format.Format_RGBA8888)
        pixels=bytes(patch.constBits());values=[]
        for i in range(0,len(pixels),4):
            r,g,b=pixels[i:i+3]
            values.append((r*3+g*6+b)//10 if max(r,g,b)-min(r,g,b)<=40 else 0)
        background=sorted(values)[len(values)//2];contrast=max(values)-background
        if contrast<24:return None
        ink=bytearray(max(0,min(255,round((v-background)*255/contrast))) for v in values)
        points=[(i%patch.width(),i//patch.width()) for i,v in enumerate(ink) if v>=96]
        if len(points)<8:return None
        left=min(x for x,_ in points);right=max(x for x,_ in points)
        top=min(y for _,y in points);bottom=max(y for _,y in points)
        if bottom-top<3 or right-left<2:return None
        gray=QImage(bytes(ink),patch.width(),patch.height(),patch.width(),QImage.Format.Format_Grayscale8).copy()
        word=gray.copy(QRect(left,top,right-left+1,bottom-top+1)).scaled(
            WIDTH-2,HEIGHT-2,Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.SmoothTransformation)
        # QImage scanlines can be padded. Keep one fixed, tightly packed proof.
        mask=bytearray(WIDTH*HEIGHT)
        raw=bytes(word.constBits());stride=word.bytesPerLine()
        for row in range(word.height()):
            start=(row+1)*WIDTH+1;mask[start:start+word.width()]=raw[row*stride:row*stride+word.width()]
        return {'version':1,'mask':bytes(mask).hex(),'scale':round(sx,4),
                'glyphs':glyph_masks(gray,ink,patch.width(),patch.height())}
    except (KeyError,TypeError,ValueError,OverflowError):return None


def proof_pixels(proof):
    if not isinstance(proof,dict) or proof.get('version')!=1:return None
    value=proof.get('mask')
    if not isinstance(value,str) or len(value)!=WIDTH*HEIGHT*2:return None
    try:mask=bytes.fromhex(value)
    except ValueError:return None
    return mask if len(mask)==WIDTH*HEIGHT and sum(mask)>=255*8 else None


def same_name_pixels(first,second):
    if first is None or second is None:return False
    if first==second:return True
    # Normalize contrast, then bound both total and local glyph differences.
    # A single changed glyph must not disappear into a long name's background.
    difference=sum(abs(a-b) for a,b in zip(first,second))
    if difference/max(sum(first),sum(second),1)>.12:return False
    for left in range(0,WIDTH-11,6):
        a=sum(first[y*WIDTH+x] for y in range(HEIGHT) for x in range(left,left+12))
        b=sum(second[y*WIDTH+x] for y in range(HEIGHT) for x in range(left,left+12))
        if max(a,b)<255*5:continue
        diff=sum(abs(first[y*WIDTH+x]-second[y*WIDTH+x]) for y in range(HEIGHT) for x in range(left,left+12))
        if diff/max(a,b)>.25:return False
    return True


def parse_glyphs(proof):
    values=proof.get('glyphs',[]) if isinstance(proof,dict) else []
    if not isinstance(values,list) or not 2<=len(values)<=16:return ()
    try:
        if any(not isinstance(v,str) or len(v)!=384 for v in values):return ()
        glyphs=tuple(bytes.fromhex(v) for v in values)
        return glyphs if all(len(g)==192 for g in glyphs) else ()
    except ValueError:return ()


def same_glyphs(first,second,*,minimum=.98,average=.985):
    if not first or len(first)!=len(second):return False
    scores=[]
    for a,b in zip(first,second):
        divisor=math.sqrt(sum(x*x for x in a)*sum(x*x for x in b))
        scores.append(sum(x*y for x,y in zip(a,b))/divisor if divisor else 0)
    return min(scores)>=minimum and sum(scores)/len(scores)>=average


@dataclass
class NameReference:
    name: str
    pixels: bytes
    key: str
    scale: float=0.0
    glyphs: tuple=()
    alternatives: list=field(default_factory=list)
    observations: deque=field(default_factory=lambda:deque(maxlen=8))

    @classmethod
    def create(cls,name,pixels,proof):
        scale=proof.get('scale',0)
        if type(scale) not in (int,float) or not 0<scale<3:scale=0.0
        return cls(name,pixels,hashlib.sha256(pixels).hexdigest()[:24],scale,parse_glyphs(proof))


class TrackingIdentity:
    """Veto text-only switches and keep real, visually different characters separate."""
    def __init__(self):
        self.reference=None
        self.candidate=None
        self.accepted_at=None

    @staticmethod
    def visual_match(reference,pixels,proof,name):
        if reference is None:return False,False
        glyphs=parse_glyphs(proof);scale=proof.get('scale',0)
        strict=(same_name_pixels(reference.pixels,pixels) or
                any(same_name_pixels(other,pixels) for other in reference.alternatives) or
                same_glyphs(reference.glyphs,glyphs))
        scaled=bool(not strict and name==reference.name and reference.scale
                    and type(scale) in (int,float) and 0<scale<3 and abs(scale-reference.scale)>.04
                    and same_glyphs(reference.glyphs,glyphs,minimum=.885,average=.915))
        return strict or scaled,scaled

    def prepare(self,payload):
        result=dict(payload);pixels=proof_pixels(payload.get('nameProof'))
        result.pop('identityKey',None);result.pop('_display_name_observation',None)
        reference=self.reference
        if pixels is None:
            if reference:result['character']=''
            return result
        proof=payload['nameProof'];name=str(payload.get('character') or '').strip()[:80]
        result['_display_name_observation']=name
        visual_match,_=self.visual_match(reference,pixels,proof,name)
        # A different raster scale needs corroborating text and every glyph.
        # Keep its template under the original key, with a bounded variant set.
        if visual_match:
            result.update(character=reference.name,identityKey=reference.key)
            self.candidate=None
            return result
        if not name:return result
        candidate=self.candidate
        if not candidate or not same_name_pixels(candidate.pixels,pixels):
            candidate=self.candidate=NameReference.create(name,pixels,proof)
        result.update(character=name,identityKey=candidate.key)
        return result

    def accept(self,payload,at=None):
        """Learn labels/templates only after the numerical reading is accepted.

        The visual key never changes when spelling changes. Six corroborating
        names, an 80 percent majority and four consecutive observations over at
        least two seconds can refine the provisional first OCR spelling.
        """
        if at is not None:
            if type(at) not in (int,float) or not math.isfinite(at):return None
            if self.accepted_at is not None and at<=self.accepted_at:return None
        pixels=proof_pixels(payload.get('nameProof'))
        if pixels is None:return None
        name=str(payload.get('_display_name_observation') or '').strip()[:80]
        candidate=self.candidate
        if candidate and candidate.key==payload.get('identityKey') and same_name_pixels(candidate.pixels,pixels):
            candidate.name=name or candidate.name
            self.reference=candidate;self.candidate=None
        reference=self.reference
        if reference is None or reference.key!=payload.get('identityKey'):return None
        matched,scaled=self.visual_match(reference,pixels,payload['nameProof'],name)
        if not matched:return None
        if at is not None:self.accepted_at=at
        # The native reader distinguishes reused status OCR from a fresh name
        # recognition. Repeated cached deliveries are not independent votes.
        if payload.get('cached') is True:return reference.name
        if scaled:reference.alternatives=(reference.alternatives+[pixels])[-3:]
        if at is None:return reference.name
        observations=reference.observations
        if observations and at-observations[-1][0]>5:observations.clear()
        # Sampling bounds repeated same-frame deliveries without depending on
        # reader frequency, and keeps enough elapsed evidence in eight votes.
        if not name or not name.isprintable() or observations and at-observations[-1][0]<.4:return reference.name
        observations.append((at,name))
        votes=[stamp for stamp,value in observations if value==name]
        if (name!=reference.name and len(votes)>=6 and len(votes)*5>=len(observations)*4
                and votes[-1]-votes[0]>=2 and all(value==name for _,value in list(observations)[-4:])):
            reference.name=name
        return reference.name
