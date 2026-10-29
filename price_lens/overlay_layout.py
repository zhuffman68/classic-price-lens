"""Shared corner layout for independent, screen-pixel annotations."""
from PySide6.QtCore import QRect

TRACKING_HEIGHT = 56


def tracking_rows(rows,bounds,guards=(),*,scale_x=None,scale_y=1.0):
    """Use the empty HUD corner, or stack above the HUD if it is too narrow.

    Guard rectangles are capture pixels; bounds and annotations are logical
    display coordinates. Never paint over a guard to then exempt it from checks.
    """
    game=QRect(*bounds);bottom=game.bottom()+1
    scale_x=scale_y if scale_x is None else scale_x
    lane=min(round(rect.left()*scale_x) for rect in guards)-game.left()-12 if guards else 0
    width=min(316,lane) if lane>=240 else min(316,game.width()-8)
    reserve=round((44 if guards else 90)*scale_y)
    if guards:
        top=min(round(rect.top()*scale_y) for rect in guards)
        rim=max(8,max(rect.height() for rect in guards)/4)
        reserve=max(reserve,bottom-top+round(rim*scale_y))
    offset=0 if lane>=240 else reserve;placed=[]
    for row in reversed(rows):
        height=TRACKING_HEIGHT
        card=dict(row,x=game.left()+4,y=game.bottom()-4,anchor='bottom_left',bounds=bounds,
                  left_offset=0,bottom_offset=offset,tracking_width=width,tracking_height=height)
        placed.append(card);offset+=height+2
    return list(reversed(placed))


def corner_offset(bounds, occupied):
    """Stack a status above other cards that occupy the game's right corner."""
    offset = 0
    game = QRect(*bounds)
    for row in occupied:
        if row.get('bounds') == bounds and (row.get('anchor') == 'bottom_right' or
                row.get('anchor') == 'bottom_left' and game.width()<720):
            height = row.get('tracking_height',36+17*len(row.get('extra','').splitlines()))
            offset = max(offset, int(row.get('bottom_offset', 0)) + height + 6)
    return min(offset, max(0, game.height()-48))
