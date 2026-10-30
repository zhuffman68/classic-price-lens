"""Pixel proofs binding a native description to its inventory source cell."""
from dataclasses import dataclass
import hashlib

from PySide6.QtCore import QPoint,QRect
from PySide6.QtGui import QImage


def association_state(value):
    if value is None:return 'normal'
    if not isinstance(value,dict):return 'rejected'
    state=value.get('state')
    return state if state in ('normal','inventory-primary') else 'rejected'


def _rect(value,image):
    if not isinstance(value,dict):return None
    parts=[value.get(k) for k in ('x','y','width','height')]
    if any(type(v) is not int for v in parts) or parts[2]<=0 or parts[3]<=0:return None
    if any(abs(v)>32768 for v in parts):return None
    rect=QRect(*parts)
    return rect if image.rect().contains(rect) else None


def _fingerprint(image,rect):
    pixels=image.copy(rect).convertToFormat(QImage.Format.Format_RGBA8888)
    return hashlib.blake2b(pixels.constBits(),digest_size=12).digest()


@dataclass(frozen=True)
class TooltipAssociation:
    token: str
    source: QRect
    slot: QRect
    regions: tuple
    fingerprints: tuple

    @classmethod
    def read(cls,value,found,image):
        if association_state(value)!='inventory-primary' or not isinstance(found,dict) or image.isNull():return None
        token=value.get('token')
        if not isinstance(token,str) or not 1<=len(token)<=512:return None
        source=_rect(value.get('source'),image);slot=_rect(value.get('slot'),image)
        panel=_rect(value.get('panel'),image);name=_rect(found.get('area'),image)
        if source is None or slot is None or panel is None or name is None:return None
        if not source.contains(slot) or not panel.contains(name):return None
        guards=value.get('guards')
        if not isinstance(guards,list) or not 1<=len(guards)<=12:return None
        regions=[name]
        for guard in guards:
            rect=_rect(guard,image)
            if rect is None:return None
            if rect not in regions:regions.append(rect)
        if sum(rect.width()*rect.height() for rect in regions)>131072:return None
        return cls(token,source,slot,tuple(regions),tuple(_fingerprint(image,r) for r in regions))

    def contains_pointer(self,pointer):
        if not isinstance(pointer,(tuple,list)) or len(pointer)!=2 or any(type(v) is not int for v in pointer):return False
        point=QPoint(*pointer)
        return self.source.contains(point) and self.slot.contains(point)

    def matches(self,image,pointer):
        if not self.contains_pointer(pointer) or image.isNull():return False
        return all(image.rect().contains(rect) and _fingerprint(image,rect)==proof
                   for rect,proof in zip(self.regions,self.fingerprints))
