"""Short application feedback in our independent, click-through overlay."""
import time


class OverlayNotice:
    def __init__(self):self.message=None;self.until=0

    def show(self,title,text='',*,seconds=2.5,warning=False):
        self.message={'key':'writer-notice','kind':'notification','name':title,'text':text,
                      'color':'#e4bd7b' if warning else '#91d0b0'}
        self.until=time.monotonic()+seconds

    def row(self,bounds,*,bottom_offset=0,now=None):
        now=time.monotonic() if now is None else now
        if self.message is None or now>=self.until:return None
        x,y,w,h=bounds
        return dict(self.message,x=x+w-5,y=y+h-5,anchor='bottom_right',bounds=bounds,bottom_offset=bottom_offset)
