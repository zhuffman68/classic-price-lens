"""Stable shop slots and conservative retention across native tooltip occlusion."""
from copy import deepcopy
import hashlib
import time
from PySide6.QtCore import QRect


class ShopRows:
    def __init__(self):self.reset()

    def reset(self):
        self.area=None;self.guards=[];self.rows={};self.active=False;self.last_verified=0

    @staticmethod
    def slot(row):
        a=row.get('area') or {}
        return tuple(a.get(k) for k in ('x','y','width','height'))

    @staticmethod
    def fingerprint(image,rect):
        if image is None or image.isNull() or not image.rect().contains(rect):return None
        patch=image.copy(rect)
        return hashlib.blake2b(patch.constBits(),digest_size=8).digest()

    def stable_slots(self,raw):
        for row in raw:
            slot=self.slot(row)
            for previous,_ in self.rows.values():
                old=self.slot(previous)
                if all(a is not None and b is not None and abs(a-b)<=3 for a,b in zip(slot,old)):
                    row['area']=dict(previous['area']);break

    def set_guards(self,area,image):
        x,y,w,h=(area[k] for k in ('x','y','width','height'))
        rects=[QRect(x,y-42,w,28),QRect(x+w+2,y-4,16,h+8)]
        guards=[(r,self.fingerprint(image,r)) for r in rects]
        self.guards=guards if all(v is not None for _,v in guards) else []

    def observe(self,shop,image,now=None,tooltip=None):
        now=time.monotonic() if now is None else now
        raw=deepcopy((shop or {}).get('rows') or []);area=(shop or {}).get('area')
        guard_ok=bool(self.guards and all(self.fingerprint(image,r)==v for r,v in self.guards))
        # A recognized native tooltip may cover a guard, but a changed guard
        # elsewhere still invalidates the page. Hidden rows carry references
        # only, never an assumed current listing or deal rating.
        guard_safe=bool(tooltip and self.guards and all(
            self.fingerprint(image,r)==v or r.intersects(tooltip) for r,v in self.guards))
        self.active=bool(area)
        if not area:
            if self.area and self.rows and (guard_ok or guard_safe):
                area=dict(self.area);self.active=True
                raw=[{'area':dict(row['area']),'covered':True} for row,_ in self.rows.values()]
            else:
                # Keep an invisible recovery cache briefly; it must not draw labels
                # or block inventory pricing after an unverified shop disappears.
                if now-self.last_verified>6:self.reset()
                return []
        contained=bool(self.area and QRect(*(self.area[k] for k in ('x','y','width','height'))).adjusted(-3,-3,3,3).contains(
            QRect(*(area[k] for k in ('x','y','width','height')))))
        close=bool(self.area and abs(area['x']-self.area['x'])<=3 and abs(area['width']-self.area['width'])<=3
                   and (abs(area['y']-self.area['y'])<=3 or contained))
        if close:
            self.stable_slots(raw)
            area=dict(self.area)
        clean=[r for r in raw if not r.get('covered') and r.get('name') and r.get('price')]
        contradiction=False
        if close:
            for row in clean:
                previous=self.rows.get(self.slot(row))
                if previous and any(previous[0].get(k)!=row.get(k) for k in ('name','price','tier')):
                    contradiction=True;break
        same=close and guard_ok and not contradiction
        # A tooltip may hide a guard. Retain recovery data without inheriting an
        # unverified covered listing; restore it when the same page is visible.
        all_verified=bool(clean and len(clean)==len(raw) and close and not contradiction)
        if not close or contradiction:
            self.rows={};self.area=dict(area);self.set_guards(area,image)
        elif all_verified:
            self.set_guards(area,image);same=True
        for row in clean:self.rows[self.slot(row)]=(deepcopy(row),now)
        if clean or same:self.last_verified=now
        references=bool(close and not contradiction and guard_safe)
        if references:
            present={self.slot(row) for row in raw}
            for saved,_ in self.rows.values():
                if self.slot(saved) not in present and QRect(*self.slot(saved)).intersects(tooltip):
                    raw.append({'area':dict(saved['area']),'covered':True})
            raw.sort(key=lambda row:row['area']['y'])
        result=[]
        for row in raw:
            saved=self.rows.get(self.slot(row))
            if references and row.get('covered') and saved and QRect(*self.slot(row)).intersects(tooltip):
                row=deepcopy(saved[0]);row.update(retained=True,covered=True,reference_only=True,listing_old=True,price=None)
            elif same and row.get('covered') and saved:
                previous,read_at=saved;row=deepcopy(previous);row['retained']=True
                row['listing_old']=now-read_at>3
                if row['listing_old']:row['price']=None
            result.append(row)
        return result
