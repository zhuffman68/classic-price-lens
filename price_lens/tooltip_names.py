"""Catalog validation of independent OCR readings, cached by actual name pixels."""
import hashlib
import re
from PySide6.QtCore import QRect
from PySide6.QtGui import QImage
from .domain import glyph_key,item_words


def name_key(found, image):
    try:
        area=found['area'];box=QRect(*(int(area[k]) for k in ('x','y','width','height')))
        if not image.rect().contains(box) or not 40<=box.width()<=720 or not 8<=box.height()<=32:return None
        patch=image.copy(box).convertToFormat(QImage.Format.Format_RGBA8888)
        pixels=bytes(patch.constBits());mask=bytearray()
        for r,g,b,a in zip(pixels[0::4],pixels[1::4],pixels[2::4],pixels[3::4]):
            neutral=r>=150 and abs(r-g)<55 and b-r<100
            coloured=max(r,g,b)>=150 and max(r,g,b)-min(r,g,b)>45
            mask.append(1 if neutral or coloured else 0)
        return (found.get('name'),found.get('tier'),box.width(),box.height(),hashlib.blake2b(mask,digest_size=12).digest())
    except (KeyError,TypeError,ValueError):return None


class TooltipNames:
    def __init__(self):self.proofs={}

    def resolve(self, found, image, catalog):
        if not found or not catalog:return found
        if catalog.candidates(found.get('name'),found.get('tier')):return found
        upgraded=re.fullmatch(r'(.+?)\s*\(\+\s*\d{1,2}\)\s*',found.get('name') or '')
        if upgraded:
            base=catalog.resolve(upgraded[1],found.get('tier'))
            if base and base.equipment:return {**found,'name':base.name,'raw_name':found['name']}
        key=name_key(found,image)
        if key is None:return found
        proof=self.proofs.get(key)
        if proof:
            item=catalog.resolve(proof[0],found.get('tier'))
            if item and item.game_id==proof[1]:return {**found,'name':proof[0]}
        matches={}
        for text in found.get('alternatives') or []:
            if not isinstance(text,str):continue
            item=catalog.resolve(text,found.get('tier'))
            if item is None:
                upgraded=re.fullmatch(r'(.+?)\s*\(\+\s*\d{1,2}\)\s*',text)
                base=catalog.resolve(upgraded[1],found.get('tier')) if upgraded else None
                if base and base.equipment:item=base
            if item:matches[item.game_id]=(text,item)
        # No closest-name guess. Competing valid versions remain unresolved.
        if len(matches)!=1:return found
        text,item=next(iter(matches.values()))
        if not roles_agree(found.get('name') or '',text,item):return found
        if len(self.proofs)>=64:self.proofs.clear()
        self.proofs[key]=(item.name,item.game_id)
        return {**found,'name':item.name,**({'raw_name':text} if text!=item.name else {})}


def roles_agree(original, alternative, item):
    """A second read cannot silently change clearly read stat/tier/color roles."""
    first_words=set(glyph_key(item_words(original)).split())
    second_words=set(glyph_key(item_words(alternative)).split())
    if not any(len(word)>=3 for word in first_words & second_words):return False
    for pattern in (r'\b(?:lesser|intermediate|greater|chaos)\b',r'\b(?:str|dex|int|luk)\b',r'\d+(?:\.\d+)?\s*%'):
        before=re.findall(pattern,original.casefold())
        if before and before!=re.findall(pattern,alternative.casefold()):return False
    colors={'red','blue','green','yellow','white','black','brown','purple','pink','orange'}
    first=original.casefold().split()[0] if original.split() else ''
    if first in colors and (not alternative.split() or alternative.casefold().split()[0]!=first):return False
    gender=re.search(r'\(([mf])\)\s*$',original.casefold())
    if gender and item.gender!=('male' if gender[1]=='m' else 'female'):return False
    return True
