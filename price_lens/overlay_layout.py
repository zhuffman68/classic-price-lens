"""Shared corner layout for independent, screen-pixel annotations."""
from PySide6.QtCore import QRect

TRACKING_HEIGHT = 56
MIN_TRACKING_WIDTH = 200


def writer_placement(bounds,footer=None,guards=(),*,scale_x=1.0,scale_y=1.0):
    """Reserve an expanding writer beside the measured HUD, or above it.

    Bounds are display-local logical pixels. Footer/guards are captured pixels;
    the returned expansion box has the same coordinate system as bounds. The
    bridge adds the monitor origin only when positioning its independent window.
    """
    game=QRect(*bounds)
    if game.width()<220 or game.height()<240:return None
    if footer is not None:
        hud=QRect(round(footer.x()*scale_x),round(footer.y()*scale_y),
                  round(footer.width()*scale_x),round(footer.height()*scale_y)).intersected(game)
    elif guards:
        # Compatibility with readers predating the measured-footer field. The
        # independent LV proof supplies the scale and the known HUD origin.
        lv=max(guards,key=lambda rect:rect.height())
        ui_scale=lv.width()/36
        left=round((lv.x()-ui_scale)*scale_x)
        top=round((lv.y()-7*ui_scale)*scale_y)
        hud=QRect(left,top,round(798*ui_scale*scale_x),game.bottom()+1-top).intersected(game)
    else:
        hud=QRect(game.x(),game.bottom()-89,game.width(),90)
    if hud.isEmpty():return None
    lane=game.right()-hud.right()-12
    width=min(280,lane) if lane>=240 else min(280,game.width()-12)
    bottom=game.bottom()-6 if lane>=240 else hud.top()-max(10,round(hud.height()*.4))
    maximum=min(240,bottom-game.top()-8)
    if maximum<200:return None
    return dict(box=[game.right()+1-width-6,bottom-maximum,width,maximum],bounds=list(bounds))


def tracking_rows(rows,bounds,guards=(),*,scale_x=None,scale_y=1.0):
    """Use the empty HUD corner, or stack above the HUD if it is too narrow.

    Guard rectangles are capture pixels; bounds and annotations are logical
    display coordinates. Never paint over a guard to then exempt it from checks.
    """
    game=QRect(*bounds);bottom=game.bottom()+1
    scale_x=scale_y if scale_x is None else scale_x
    lane=min(round(rect.left()*scale_x) for rect in guards)-game.left()-12 if guards else 0
    width=min(316,lane) if lane>=MIN_TRACKING_WIDTH else min(316,game.width()-8)
    reserve=44 if guards else 90
    if guards:
        top=min(round(rect.top()*scale_y) for rect in guards)
        # One measured status-row height also clears the chat/input strip.
        rim=max(8,max(rect.height() for rect in guards))
        reserve=max(reserve,bottom-top+round(rim*scale_y))
    offset=0 if lane>=MIN_TRACKING_WIDTH else reserve;placed=[]
    for row in reversed(rows):
        height=TRACKING_HEIGHT
        card=dict(row,x=game.left()+4,y=game.bottom()-4,anchor='bottom_left',bounds=bounds,
                  left_offset=0,bottom_offset=offset,tracking_width=width,tracking_height=height)
        placed.append(card);offset+=height+2
    return list(reversed(placed))


def corner_offset(bounds, occupied, rectangles=()):
    """Stack a status above other cards that occupy the game's right corner."""
    offset = 0
    game = QRect(*bounds)
    for row in occupied:
        if row.get('bounds') == bounds and (row.get('anchor') == 'bottom_right' or
                row.get('anchor') == 'bottom_left' and game.width()<720):
            height = row.get('tracking_height',36+17*len(row.get('extra','').splitlines()))
            offset = max(offset, int(row.get('bottom_offset', 0)) + height + 6)
    for rect in rectangles:
        rect=QRect(*rect) if not isinstance(rect,QRect) else rect
        if rect.intersects(game) and rect.right()>=game.right()-350:
            offset=max(offset,game.bottom()+1-rect.top()+6)
    return min(offset, max(0, game.height()-48))
