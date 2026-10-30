"""Stable shop slots and conservative retention across native tooltip occlusion."""
from copy import deepcopy
import time
from PySide6.QtCore import QRect
from PySide6.QtGui import QImage,QRegion
from .domain import glyph_key,item_words,unclipped_name


class ShopRows:
    PRESENTATION_SECONDS=30
    ROW_LIMIT=24

    def __init__(self,identity=None):self.resolve_identity=identity;self.reset()

    def reset(self):
        self.page_revision=getattr(self,'page_revision',-1)+1
        self.area=None;self.guards=[];self.rows={};self.row_pixels={};self.active=False;self.last_verified=0
        self.quote_proofs={}
        self._page_proven=False

    @staticmethod
    def slot(row):
        a=row.get('area') or {}
        return tuple(a.get(k) for k in ('x','y','width','height'))

    def identity(self,row):
        if self.resolve_identity:
            resolved=self.resolve_identity(row)
            if resolved is not None:return resolved
        return (glyph_key(item_words(unclipped_name(row.get('name') or ''))).rstrip(': '),row.get('tier'))

    def relative_slot(self,row):
        """A list-local slot survives shop dragging and OCR order changes."""
        x,y,w,h=self.slot(row)
        if self.area is None or any(value is None for value in (x,y,w,h)):return None
        return (x-self.area['x'],y-self.area['y'],w,h)

    def presentation_for(self,row,now=None,quote_key=None):
        """Last confirmed display amount; never promotes it to a current offer."""
        if row.get('shop_page',self.page_revision)!=self.page_revision:return None
        slot=self.slot(row)
        if row.get('price'):
            if quote_key is not None:
                self.quote_proofs[slot]=(self.page_revision,self.identity(row),quote_key)
            return deepcopy(row['price'])
        if not self._page_proven or row.get('shop_slot')!=self.relative_slot(row):return None
        saved=self.rows.get(slot)
        if saved is None or self.identity(saved[0])!=self.identity(row):return None
        if quote_key is not None and self.quote_proofs.get(slot)!=(self.page_revision,self.identity(row),quote_key):return None
        now=time.monotonic() if now is None else now
        age=now-saved[1]
        if not 0<=age<=self.PRESENTATION_SECONDS:return None
        return deepcopy(saved[0].get('price'))

    def decorate(self,row,now):
        row['shop_page']=self.page_revision;row['shop_slot']=self.relative_slot(row)
        row['presentation_price']=self.presentation_for(row,now)
        row['presentation_held']=bool(row['presentation_price'] and not row.get('price'))
        return row

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

    def tooltip_guards_match(self,image,tooltip,exclude=()):
        """A tooltip excuses only its own pixels, with another visible proof."""
        if tooltip is None or not self.guards:return False
        verified=False
        for rect,reference in self.guards:
            visible=QRegion(rect)
            for hidden in (*reference[1],*exclude,tooltip):
                visible=visible.subtracted(QRegion(hidden))
            if visible.isEmpty():continue
            if not self.guard_matches(image,rect,reference,(*exclude,tooltip)):return False
            verified=True
        return verified

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
        # elsewhere still invalidates the page. Hidden rows carry a bounded
        # last-confirmed presentation, independently of current listing proof.
        guard_safe=self.tooltip_guards_match(image,tooltip,exclude)
        self.active=bool(area)
        if not area:
            if self.area and self.rows and (guard_ok or guard_safe):
                area=dict(self.area);self.active=True
                raw=[{'area':dict(row['area']),'covered':True} for row,_ in self.rows.values()]
            else:
                # Keep an invisible recovery cache briefly; it must not draw labels
                # or block inventory pricing after an unverified shop disappears.
                self._page_proven=False
                if self.area and now-self.last_verified>6:self.reset()
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
            # Compare proven listing identities/prices, never tooltip pixels or
            # absolute coordinates: moving the same shop is not a new page.
            previous=[(self.identity(row),row.get('price')) for row,_ in sorted(self.rows.values(),key=lambda saved:self.slot(saved[0])[1])]
            current=[(self.identity(row),row.get('price')) for row in sorted(clean,key=lambda row:self.slot(row)[1])]
            if contradiction or (previous and (not clean or len(clean)!=len(raw) or previous!=current)):
                self.page_revision+=1
            self.rows={};self.row_pixels={};self.quote_proofs={};self.area=dict(area);self.set_guards(area,image,exclude)
        elif all_verified:
            self.set_guards(area,image,exclude);same=True
        for row in clean:
            slot=self.slot(row);self.rows[slot]=(deepcopy(row),now)
            rect=QRect(*slot)
            if image is not None and image.rect().contains(rect):
                self.row_pixels[slot]=image.copy(rect).convertToFormat(QImage.Format.Format_RGBA8888)
        if len(self.rows)>self.ROW_LIMIT:
            for slot in sorted(self.rows,key=lambda key:self.rows[key][1])[:-self.ROW_LIMIT]:
                self.rows.pop(slot,None);self.row_pixels.pop(slot,None);self.quote_proofs.pop(slot,None)
        if clean or same:self.last_verified=now
        references=bool(close and not contradiction and (guard_ok or guard_safe))
        self._page_proven=bool(references or (clean and len(clean)==len(raw)))
        if references:
            present={self.slot(row) for row in raw}
            for saved,_ in self.rows.values():
                if self.slot(saved) not in present and tooltip and QRect(*self.slot(saved)).intersects(tooltip):
                    raw.append({'area':dict(saved['area']),'covered':True})
            raw.sort(key=lambda row:row['area']['y'])
        result=[]
        for row in raw:
            saved=self.rows.get(self.slot(row))
            if references and (row.get('covered') or not row.get('name')) and saved:
                covered=bool(row.get('covered'))
                row=deepcopy(saved[0]);row.update(retained=True,covered=covered,reference_only=True,listing_old=True,price=None)
            elif row.get('covered'):
                # Identity remains unknown when the page cannot be verified.
                row['price']=None
            result.append(self.decorate(row,now))
        return result

    def restore_visible(self,image,rows,now=None):
        """Restore a listing only when its exact, previously read pixels return."""
        if not self.guards or not all(self.guard_matches(image,r,v) for r,v in self.guards):return rows
        now=time.monotonic() if now is None else now
        result=[]
        for row in rows:
            slot=self.slot(row);pixels=self.row_pixels.get(slot);saved=self.rows.get(slot)
            if (saved and pixels is not None and (row.get('covered') or row.get('listing_old'))
                    and image.rect().contains(QRect(*slot))
                    and image.copy(QRect(*slot)).convertToFormat(QImage.Format.Format_RGBA8888)==pixels):
                row=deepcopy(saved[0]);self.rows[slot]=(deepcopy(row),now)
                row=self.decorate(row,now)
            result.append(row)
        return result
