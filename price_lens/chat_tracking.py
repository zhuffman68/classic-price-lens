"""Small pixel templates for visible text, independent of bubble decoration."""
import math

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QImage


def stamp(image, box):
    rect = QRect(*box)
    if not image.rect().contains(rect) or rect.isEmpty():
        return b''
    sample = image.copy(rect).scaled(24, 24, Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.FastTransformation).convertToFormat(QImage.Format.Format_Grayscale8)
    return bytes(sample.constBits())


def difference(first, second):
    if not first or len(first) != len(second):
        return 1.0
    ink = [(a, b) for a, b in zip(first, second) if min(a, b) < 210]
    values = ink or list(zip(first, second))
    return sum(abs(a-b) > 30 for a, b in values) / len(values)


def shifted(box, dx, dy):
    return [box[0]+dx, box[1]+dy, box[2], box[3]]


def visible(image, source, dx=0, dy=0):
    area = source.get('track_box') or source['box']
    reference = source.get('track_stamp') or source['stamp']
    if difference(stamp(image, shifted(area, dx, dy)), reference) > .035:
        return False
    header = source.get('speaker_box')
    return not header or difference(stamp(image, shifted(header, dx, dy)), source['speaker_stamp']) <= .06


def locate_offset(image, source, *, radius=112):
    """Reacquire nearby text only when both its body and speaker still match.

    A coarse, bounded array search proposes locations. Native-size fingerprints
    confirm them. Uniform backgrounds and ambiguous repeated matches reject.
    """
    if visible(image, source):
        return 0, 0
    role = source.get('source_role')
    if role not in ('bubble', 'chat'):
        return None
    reference = source.get('track_stamp') or source['stamp']
    if not reference or max(reference)-min(reference) < 45:
        return None
    area = QRect(*(source.get('track_box') or source['box']))
    template = source.get('track_pixels')
    if template is None:
        # Old in-memory/test sources have no body template. Preserve the small
        # legacy search without adopting a large unverified scene region.
        offsets = [(0, d) for d in (-32,-24,-16,-8,8,16,24,32)]
        if role == 'bubble':
            offsets += [(d, 0) for d in (-32,-16,-8,8,16,32)]
        for dx, dy in offsets:
            if visible(image, source, dx, dy):
                return dx, dy
        return None
    search = area.adjusted(0 if role == 'chat' else -radius, -radius,
                           0 if role == 'chat' else radius, radius).intersected(image.rect())
    if search.width() < area.width() or search.height() < area.height():
        return None
    import numpy as np

    def gray(part, width, height):
        scaled = part.scaled(width, height, Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation).convertToFormat(QImage.Format.Format_Grayscale8)
        return np.frombuffer(bytes(scaled.constBits()), np.uint8).reshape(height, scaled.bytesPerLine())[:, :width]

    factor = max(1, math.ceil(max(area.width()/32, area.height()/16)))
    tw, th = max(1, area.width()//factor), max(1, area.height()//factor)
    sw, sh = search.width()//factor, search.height()//factor
    before = gray(template, tw, th)
    current = gray(image.copy(search), sw, sh)
    windows = np.lib.stride_tricks.sliding_window_view(current, (th, tw))
    step=max(1,math.ceil(math.sqrt(windows.size/1_500_000)))
    windows=windows[::step,::step]
    ink = (windows < 210) | (before < 210)
    wrong = (np.abs(windows.astype('int16')-before.astype('int16')) > 30) & ink
    score = wrong.sum(axis=(-2,-1)) / np.maximum(1, ink.sum(axis=(-2,-1)))
    candidates = []
    for flat in np.argsort(score, axis=None)[:16]:
        cy, cx = np.unravel_index(flat, score.shape)
        dx = search.x()+int(cx)*step*factor-area.x()
        dy = search.y()+int(cy)*step*factor-area.y()
        if any(abs(dx-x)+abs(dy-y) < 2*step*factor for x,y in candidates):
            continue
        candidates.append((dx,dy))
        if len(candidates) == 3:
            break
    matches = []
    reach = step*factor
    for dx, dy in candidates:
        best = (1.0, None)
        xs = (0,) if role == 'chat' else range(dx-reach, dx+reach+1, 2)
        for x in xs:
            for y in range(dy-reach, dy+reach+1, 2):
                if max(abs(x),abs(y)) > radius:
                    continue
                error = difference(stamp(image, shifted(area.getRect(),x,y)), reference)
                if error < best[0]:
                    best = error, (x,y)
        if best[1] is None:
            continue
        bx, by = best[1]
        for x in ((0,) if role == 'chat' else range(bx-1,bx+2)):
            for y in range(by-1,by+2):
                if max(abs(x),abs(y)) <= radius and visible(image,source,x,y):
                    if not any(abs(x-a)+abs(y-b) <= 3 for a,b in matches):
                        matches.append((x,y))
    if len(matches) != 1:
        return None
    return matches[0]


def move_source(source, dx, dy):
    for key in ('box', 'track_box', 'speaker_box'):
        if source.get(key):
            source[key] = shifted(source[key], dx, dy)
