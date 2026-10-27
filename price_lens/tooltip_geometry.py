"""Find the native item's description panel around a recognized name line.

Only captured colours are inspected. A known tooltip anchor is required; this
never searches desktop windows or treats arbitrary purple scenery as a tooltip.
"""
from PySide6.QtCore import QRect


def description_bounds(image,area):
    if image is None or image.isNull() or not area:return None
    name=QRect(*(int(area[k]) for k in ('x','y','width','height')))
    # A tooltip can extend past a cropped fixture or the shared display edge.
    # Its recognized name line is allowed to be clipped there as well.
    name=name.intersected(image.rect())
    if name.width()<12 or name.height()<8:return None
    def fill(x,y):
        if not(0<=x<image.width() and 0<=y<image.height()):return False
        c=image.pixelColor(x,y);r,g,b=c.red(),c.green(),c.blue()
        return 25<=r<=155 and 25<=g<=160 and b>=max(r,g)+18 and b*100>=max(r,g)*116
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
    column=min(right,left+3);top=bottom=seed_y
    for direction in (-1,1):
        y=seed_y;last=y;gap=0
        while 0<=y<image.height():
            if fill(column,y):last=y;gap=0
            else:gap+=1
            if gap>4:break
            y+=direction
        if direction<0:top=last
        else:bottom=last
    if bottom-top<name.height()+8:return None
    return QRect(left-3,top-3,right-left+7,bottom-top+7).intersected(image.rect())


def still_present(image,rect):
    if rect is None or not image.rect().contains(rect):return False
    for fraction in (.2,.5,.8):
        c=image.pixelColor(min(rect.right(),rect.left()+6),round(rect.top()+rect.height()*fraction))
        if c.blue()>max(c.red(),c.green())+18:return True
    return False
