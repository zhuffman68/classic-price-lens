"""Find the native item's description panel around a recognized name line.

Only captured colours are inspected. A known tooltip anchor is required; this
never searches desktop windows or treats arbitrary purple scenery as a tooltip.
"""
from PySide6.QtCore import QRect
from PySide6.QtGui import QRegion
from PySide6.QtGui import QImage
import time


def _visible_region(rect,exclude):
    visible=QRegion(rect)
    for covered in exclude:
        if rect.intersects(covered):visible=visible.subtracted(QRegion(covered.adjusted(-1,-1,1,1)))
    return visible


def _description_body(image,rect,exclude=()):
    """A bright shop/chat pane is not a dark native item description.

    Never use our own dark price cards as evidence for a description behind
    them: that creates a dim/bright feedback loop on otherwise light shops.
    """
    if rect is None or not image.rect().contains(rect):return False
    interior=rect.adjusted(6,6,-6,-6)
    if interior.isEmpty():return False
    dark=total=0.0
    for part in _visible_region(interior,exclude):
        weight=part.width()*part.height();matches=0
        for fy in (.1,.3,.5,.7,.9):
            for fx in (.1,.3,.5,.7,.9):
                color=image.pixelColor(part.x()+round((part.width()-1)*fx),part.y()+round((part.height()-1)*fy))
                matches+=max(color.red(),color.green(),color.blue())<185
        dark+=weight*matches/25;total+=weight
    return total>=24 and dark/total>=.60


def _rim_pixels(image):
    """Paired dark strokes around Classic's translucent one-pixel frame gap."""
    rgba=image.convertToFormat(QImage.Format.Format_RGBA8888)
    pixels=rgba.constBits();stride=rgba.bytesPerLine();width=rgba.width();height=rgba.height()
    def rim(x,y,horizontal=False,_keep=rgba):
        if not (0<=x<width-(0 if horizontal else 2) and 0<=y<height-(2 if horizontal else 0)):return False
        at=y*stride+x*4
        step=stride if horizontal else 4
        a=pixels[at:at+3];b=pixels[at+step:at+step+3];c=pixels[at+step*2:at+step*2+3]
        if max(a)>=180 or max(c)>=180 or any(abs(a[i]-c[i])>=65 for i in range(3)):return False
        light=lambda p:p[0]*.30+p[1]*.59+p[2]*.11
        return light(b)>max(light(a),light(c))*1.45+15
    return rim


def _framed_bounds(image,name):
    # Require the recognized name plus two independently repeated frame edges.
    # Warm chat behind the panel can erase its purple hue, but not its geometry.
    rim=_rim_pixels(image)
    ys=range(max(0,name.top()-1),min(image.height(),name.top()+123),6)
    if len(ys)<5:return None
    score=lambda x:sum(rim(x,y) for y in ys)/len(ys)
    left=max(((score(x),x) for x in range(max(0,name.left()-28),max(0,name.left()-3))),default=(0,0))
    if left[0]<.55:return None
    left=left[1]
    right=next((x for x in range(left+70,min(image.width()-2,left+740)) if score(x)>=.45),None)
    if right is None or name.right()>right+2:return None
    seed=name.center().y();edges=[]
    for direction,limit in ((-1,max(-1,name.top()-96)),(1,min(image.height(),name.top()+900))):
        last=seed;gap=0
        for y in range(seed,limit,direction):
            if rim(left,y) or rim(right,y):last=y;gap=0
            else:gap+=1
            if gap>10:break
        edges.append(last)
    top,bottom=edges
    columns=range(left+8,right-6,6)
    cap=next((y for y in range(max(0,name.top()-80),min(image.height()-2,name.top()))
              if sum(rim(x,y,True) for x in columns)>=len(columns)*.55),None)
    if cap is None and score(right)<.55:return None
    if cap is not None:top=cap
    if bottom-top<max(40,name.height()+8):return None
    return QRect(left,top-1,right-left+3,bottom-top+3).intersected(image.rect())


def description_bounds(image,area,exclude=()):
    if image is None or image.isNull() or not area:return None
    name=QRect(*(int(area[k]) for k in ('x','y','width','height')))
    # A tooltip can extend past a cropped fixture or the shared display edge.
    # Its recognized name line is allowed to be clipped there as well.
    name=name.intersected(image.rect())
    if name.width()<12 or name.height()<8:return None
    visible=_visible_region(name,exclude)
    if sum(part.width()*part.height() for part in visible)<name.width()*name.height()*.25:return None
    framed=_framed_bounds(image,name)
    if framed is not None:return framed if _description_body(image,framed,exclude) else None
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
    rect=QRect(left-3,top-3,right-left+7,bottom-top+7).intersected(image.rect())
    return rect if _description_body(image,rect,exclude) else None


def still_present(image,rect,exclude=()):
    if not _description_body(image,rect,exclude):return False
    matches=0
    for fraction in (.2,.5,.8):
        c=image.pixelColor(min(rect.right(),rect.left()+6),round(rect.top()+rect.height()*fraction))
        if c.red()<=155 and c.green()<=160 and c.blue()>max(c.red(),c.green())+18:matches+=1
    if matches>=2:return True
    rim=_rim_pixels(image)
    ys=[round(rect.top()+rect.height()*fraction) for fraction in (.12,.3,.5,.7,.88)]
    return all(sum(rim(x,y) for y in ys)>=2 for x in (rect.left(),rect.right()-2))


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
