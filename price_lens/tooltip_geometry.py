"""Find the native item's description panel around a recognized name line.

Only captured colours are inspected. A known tooltip anchor is required; this
never searches desktop windows or treats arbitrary purple scenery as a tooltip.
"""
from PySide6.QtCore import QRect
from PySide6.QtGui import QImage
import time


def description_bounds(image,area,exclude=()):
    if image is None or image.isNull() or not area:return None
    name=QRect(*(int(area[k]) for k in ('x','y','width','height')))
    # A tooltip can extend past a cropped fixture or the shared display edge.
    # Its recognized name line is allowed to be clipped there as well.
    name=name.intersected(image.rect())
    if name.width()<12 or name.height()<8:return None
    def fill(x,y):
        if not(0<=x<image.width() and 0<=y<image.height()):return False
        c=image.pixelColor(x,y);r,g,b=c.red(),c.green(),c.blue()
        return 0<=r<=155 and 0<=g<=160 and b>=max(r,g)+18 and b*100>=max(r,g)*116
    best=None
    for y in (name.top()-4,name.top()-8,name.top()+2,name.bottom()+4,name.bottom()+12):
        if not 0<=y<image.height():continue
        for seed in (name.left()-5,name.left()-9,name.left()-13,name.left()+2):
            if not fill(seed,y):continue
            left=seed
            while left>0 and fill(left-1,y):left-=1
            right=seed;last=seed;gap=0
            while right<min(image.width(),left+760):
                if fill(right,y):last=right;gap=0
                else:gap+=1
                if gap>12:break
                right+=1
            if last-left>=60 and (best is None or last-left>best[1]-best[0]):best=(left,last,y)
    if best is None:return None
    left,right,seed_y=best
    spans=[]
    # The cyan name bullet or item art can interrupt one gutter column.
    # Try both inner edges rather than treating that interruption as the end.
    for column in (left+1,min(right,left+3),min(right,left+5),max(left,right-2)):
        top=bottom=seed_y
        for direction in (-1,1):
            y=seed_y;last=y;gap=0
            while 0<=y<image.height():
                if fill(column,y):last=y;gap=0
                else:gap+=1
                if gap>4:break
                y+=direction
            if direction<0:top=last
            else:bottom=last
        spans.append((top,bottom))
    top,bottom=max(spans,key=lambda span:span[1]-span[0])
    if bottom-top<name.height()+8:return None
    # Our price cards may cover the name's right half. Inspect the visible gaps
    # between them, within the already anchored panel, to recover its full width.
    for covered in exclude:
        for y in (covered.top()-3,covered.bottom()+3):
            if not top+3<=y<=bottom-3 or not fill(left+3,y):continue
            end=left+3;last=end;gap=0
            while end<min(image.width(),left+760):
                if fill(end,y):last=end;gap=0
                else:gap+=1
                if gap>12:break
                end+=1
            right=max(right,last)
    return QRect(left-3,top-3,right-left+7,bottom-top+7).intersected(image.rect())


def still_present(image,rect):
    if rect is None or not image.rect().contains(rect):return False
    for fraction in (.2,.5,.8):
        c=image.pixelColor(min(rect.right(),rect.left()+6),round(rect.top()+rect.height()*fraction))
        if c.blue()>max(c.red(),c.green())+18:return True
    return False


class TooltipReference:
    """Bridge a brief OCR miss only while the same captured name/panel remains."""
    def __init__(self):self.clear()

    def clear(self):
        self.found=None;self.name=None;self.panel=None;self.pixels=b'';self.pointer=None;self.at=0

    @staticmethod
    def signature(image,rect):
        if rect is None or not image.rect().contains(rect):return b''
        patch=image.copy(rect).convertToFormat(QImage.Format.Format_Grayscale8)
        return bytes(patch.constBits())

    def observe(self,found,image,pointer,allow=True,now=None):
        now=time.monotonic() if now is None else now
        if not allow:self.clear();return None
        if found:
            area=found['area'];self.name=QRect(*(area[k] for k in ('x','y','width','height'))).intersected(image.rect())
            self.panel=description_bounds(image,area);self.pixels=self.signature(image,self.name)
            self.found=found;self.pointer=pointer;self.at=now
            return found
        if self.found and pointer and self.pointer and now-self.at<=.4 and max(abs(a-b) for a,b in zip(pointer,self.pointer))<=8 and still_present(image,self.panel):
            current=self.signature(image,self.name)
            if current and len(current)==len(self.pixels) and sum(abs(a-b)>22 for a,b in zip(current,self.pixels))/len(current)<.04:
                return self.found
        self.clear();return None
