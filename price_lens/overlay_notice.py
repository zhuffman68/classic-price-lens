"""Short application feedback in our independent, click-through overlay."""
import math
import time


class OverlayNotice:
    def __init__(self):
        self.message=None;self.until=0;self.identity=None;self.revision=0
        self.seconds=2.5;self.revealed=False

    def show(self,title,text='',*,seconds=2.5,warning=False,identity=None,pending=False):
        self.revision+=1;self.identity=identity;self.revealed=False
        self.seconds=max(.3,min(65,float(seconds))) if type(seconds) in (int,float) and math.isfinite(seconds) else 2.5
        self.message={'key':'writer-notice','kind':'notification','name':title,'text':text,
                      'color':'#e4bd7b' if warning else '#9ebde3' if pending else '#91d0b0',
                      'notice_icon':'warning' if warning else 'progress' if pending else 'copied','notice_revision':self.revision}
        self.until=time.monotonic()+self.seconds

    def clear(self):
        self.message=None;self.until=0;self.identity=None;self.revealed=False

    def row(self,bounds,*,bottom_offset=0,blocked=False,placement=None,origin=(0,0),now=None):
        now=time.monotonic() if now is None else now
        if self.message is None or now>=self.until or blocked:return None
        if not self.revealed:
            # The writer owns the corner until its exit completes. Start the
            # short result lifetime on first presentation, without extending it
            # on the capture/GUI's repeated updates.
            self.revealed=True;self.until=now+self.seconds
        x,y,w,h=bounds
        row=dict(self.message,x=x+w-5,y=y+h-5,anchor='bottom_right',bounds=bounds,bottom_offset=bottom_offset,
                 notification_width=min(280,max(1,w-8)),notification_height=48,notice_until=self.until)
        box=placement.get('box') if isinstance(placement,dict) and placement.get('bounds')==bounds else None
        if (isinstance(box,list) and len(box)==4 and all(type(n) is int for n in box)
                and isinstance(origin,(tuple,list)) and len(origin)==2 and all(type(n) is int for n in origin)):
            left,top,width,height=box;left-=origin[0];top-=origin[1]
            if 160<=width<=600 and height>=48 and x<=left and y<=top and left+width<=x+w and top+height<=y+h:
                end=min(top+height,y+h-max(0,int(bottom_offset)))
                row['notification_width']=width
                row['notification_box']=[left,max(y+4,end-48),width,48]
        return row
