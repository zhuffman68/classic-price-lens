"""Stable shop slots and conservative retention across native tooltip occlusion."""
from copy import deepcopy
import time
from PySide6.QtCore import QRect
from PySide6.QtGui import QImage,QRegion
from .domain import glyph_key,item_words,unclipped_name


class ShopRows:
    def __init__(self,identity=None):self.resolve_identity=identity;self.reset()

    def reset(self):
        self.area=None;self.guards=[];self.rows={};self.active=False;self.last_verified=0

    @staticmethod
    def slot(row):
        a=row.get('area') or {}
        return tuple(a.get(k) for k in ('x','y','width','height'))

    def identity(self,row):
        if self.resolve_identity:
            resolved=self.resolve_identity(row)
            if resolved is not None:return resolved
        return (glyph_key(item_words(unclipped_name(row.get('name') or ''))).rstrip(': '),row.get('tier'))

    @staticmethod
    def guard_matches(image,rect,reference,exclude=()):
        if reference is None or image is None or not image.rect().contains(rect):return False
        previous,old_exclusions=reference
        visible=QRegion(rect)
        for covered in (*old_exclusions,*exclude):
            if rect.intersects(covered):visible=visible.subtracted(QRegion(covered))
        if visible.isEmpty():return False
        current=image.copy(rect).convertToFormat(QImage.Format.Format_RGBA8888)
        return all(current.copy(part.translated(-rect.x(),-rect.y()))==previous.copy(part.translated(-rect.x(),-rect.y())) for part in visible)

    def stable_slots(self,raw):
        for row in raw:
            slot=self.slot(row)
            for previous,_ in self.rows.values():
                old=self.slot(previous)
                if all(a is not None and b is not None and abs(a-b)<=3 for a,b in zip(slot,old)):
                    row['area']=dict(previous['area']);break

    def set_guards(self,area,image,exclude=()):
        x,y,w,h=(area[k] for k in ('x','y','width','height'))
        # The owner portrait above the list animates; the table rim does not.
        rects=[QRect(x,y-6,w,4),QRect(x+w+2,y-4,16,h+8)]
        self.guards=[(r,(image.copy(r).convertToFormat(QImage.Format.Format_RGBA8888),tuple(QRect(e) for e in exclude)))
                     for r in rects if image is not None and image.rect().contains(r)]
        if len(self.guards)!=len(rects):self.guards=[]

    def observe(self,shop,image,now=None,tooltip=None,exclude=()):
        now=time.monotonic() if now is None else now
        raw=deepcopy((shop or {}).get('rows') or []);area=(shop or {}).get('area')
        guard_ok=bool(self.guards and all(self.guard_matches(image,r,v,exclude) for r,v in self.guards))
        # A recognized native tooltip may cover a guard, but a changed guard
        # elsewhere still invalidates the page. Hidden rows carry references
        # only, never an assumed current listing or deal rating.
        guard_safe=bool(tooltip and self.guards and all(
            self.guard_matches(image,r,v,exclude) or r.intersects(tooltip) for r,v in self.guards))
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
                if previous and (previous[0].get('price')!=row.get('price') or self.identity(previous[0])!=self.identity(row)):
                    contradiction=True;break
        same=close and guard_ok and not contradiction
        # A tooltip may hide a guard. Retain recovery data without inheriting an
        # unverified covered listing; restore it when the same page is visible.
        all_verified=bool(clean and len(clean)==len(raw) and close and not contradiction)
        if not close or contradiction:
            self.rows={};self.area=dict(area);self.set_guards(area,image,exclude)
        elif all_verified:
            self.set_guards(area,image,exclude);same=True
        for row in clean:self.rows[self.slot(row)]=(deepcopy(row),now)
        if clean or same:self.last_verified=now
        references=bool(close and not contradiction and (guard_ok or guard_safe))
        if references:
            present={self.slot(row) for row in raw}
            for saved,_ in self.rows.values():
                if self.slot(saved) not in present and tooltip and QRect(*self.slot(saved)).intersects(tooltip):
                    raw.append({'area':dict(saved['area']),'covered':True})
            raw.sort(key=lambda row:row['area']['y'])
        result=[]
        for row in raw:
            saved=self.rows.get(self.slot(row))
            if references and row.get('covered') and saved:
                row=deepcopy(saved[0]);row.update(retained=True,covered=True,reference_only=True,listing_old=True,price=None)
            elif row.get('covered'):
                # Identity remains unknown when the page cannot be verified.
                row['price']=None
            result.append(row)
        return result
