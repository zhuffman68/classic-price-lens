"""Briefly retain occluded shop rows only while independent page pixels still agree."""
from copy import deepcopy
import hashlib
import time

from PySide6.QtCore import QRect


class ShopRows:
    def __init__(self):
        self.reset()

    def reset(self):
        self.area=None
        self.guards=[]
        self.rows={}
        self.active=False

    @staticmethod
    def slot(row):
        a=row.get("area") or {}
        return (a.get("x"),a.get("y"),a.get("width"),a.get("height"))

    @staticmethod
    def fingerprint(image,rect):
        if image is None or image.isNull() or not image.rect().contains(rect):return None
        patch=image.copy(rect)
        return hashlib.blake2b(patch.constBits(),digest_size=8).digest()

    def observe(self,shop,image,now=None):
        now=time.monotonic() if now is None else now
        raw=deepcopy((shop or {}).get("rows") or [])
        area=(shop or {}).get("area")
        self.active=bool(area)
        if not area:
            if self.area and self.rows and self.guards and all(self.fingerprint(image,r)==value for r,value in self.guards):
                # The list can be entirely behind the native tooltip while its
                # independent header and scrollbar still establish an open shop.
                area=dict(self.area)
                raw=[{"area":dict(row["area"]),"covered":True} for row,_ in self.rows.values()]
                self.active=True
            else:
                self.reset();return raw
        # The name/header above the list and its scrollbar identify the page.
        # If either is hidden, moving or changed, no covered row is inherited.
        same=bool(self.area and abs(area["x"]-self.area["x"])<=2 and area["width"]==self.area["width"]
                  and self.guards and all(self.fingerprint(image,r)==value for r,value in self.guards))
        clean=[r for r in raw if not r.get("covered") and r.get("name") and r.get("price")]
        if same:
            for row in clean:
                before=self.rows.get(self.slot(row))
                if before and (before[0].get("name"),before[0].get("price"),before[0].get("tier")) != (row.get("name"),row.get("price"),row.get("tier")):
                    same=False;break
        if not same:
            self.rows={}
            self.area=dict(area)
            x,y,w,h=(area[k] for k in ("x","y","width","height"))
            guards=[QRect(x,y-42,w,28),QRect(x+w+2,y-4,16,h+8)]
            values=[(r,self.fingerprint(image,r)) for r in guards]
            self.guards=values if all(value is not None for _,value in values) else []
        for row in clean:self.rows[self.slot(row)]=(deepcopy(row),now)
        result=[]
        for row in raw:
            saved=self.rows.get(self.slot(row))
            if same and row.get("covered") and saved:
                previous,read_at=saved
                row=deepcopy(previous)
                row["retained"]=True
                row["listing_old"]=now-read_at>3
                if row["listing_old"]:row["price"]=None
            result.append(row)
        return result
