"""Digit-place transitions shared by widgets and the painted game overlay."""
import re
from PySide6.QtCore import QRectF, Qt


def columns(text):
    result=[];cursor=0
    for index,match in enumerate(re.finditer(r'\d[\d,]*(?:\.\d+)?',text)):
        result.extend((None,c) for c in text[cursor:match.start()])
        integer,_,fraction=match[0].partition('.')
        remaining=sum(c.isdigit() for c in integer)
        for char in integer:
            if char.isdigit():
                remaining-=1;result.append(((index,'integer',remaining),char))
            else:result.append((None,char))
        if fraction:
            result.append((None,'.'))
            result.extend(((index,'fraction',n),c) for n,c in enumerate(fraction))
        cursor=match.end()
    result.extend((None,c) for c in text[cursor:])
    return result


class NumberRoll:
    """An interrupted roll starts at the visible glyph positions, not its old target."""
    def __init__(self,text=''):
        self.text=text;self.columns=columns(text);self.before={};self.progress=1.0

    def layers(self,key,char):
        old=self.before.get(key,[])
        if self.progress>=.999 or old==[(char,0.0,1.0)]:return [(char,0.0,1.0)]
        p=self.progress
        return [(c,y-p,alpha*(1-p)) for c,y,alpha in old if alpha*(1-p)>.001]+[(char,1-p,p)]

    def set_text(self,text,animate=True):
        if text==self.text:return False
        self.before={key:self.layers(key,char) for key,char in self.columns if key is not None}
        self.text=text;self.columns=columns(text)
        self.progress=0.0 if animate and any(key is not None for key,_ in self.columns) else 1.0
        return self.progress==0.0

    def finish(self):
        self.progress=1.0;self.before={}

    def paint(self,painter,rect,alignment=Qt.AlignmentFlag.AlignLeft):
        painter.save()
        metrics=painter.fontMetrics();cell=metrics.horizontalAdvance('0');height=metrics.height()
        widths=[cell if key is not None else metrics.horizontalAdvance(c) for key,c in self.columns]
        width=sum(widths)
        if width>rect.width() and rect.width()>0:
            painter.translate(rect.x(),0);painter.scale(rect.width()/width,1)
            rect=QRectF(0,rect.y(),width,rect.height())
        left=rect.right()-width if alignment&Qt.AlignmentFlag.AlignRight else rect.x()+(rect.width()-width)/2 if alignment&Qt.AlignmentFlag.AlignHCenter else rect.x()
        top=rect.y()+(rect.height()-height)/2
        opacity=painter.opacity()
        painter.setClipRect(rect,Qt.ClipOperation.IntersectClip)
        for (key,char),w in zip(self.columns,widths):
            box=QRectF(left,top,w,height);left+=w
            if key is None:
                painter.drawText(box,Qt.AlignmentFlag.AlignCenter,char);continue
            painter.save();painter.setClipRect(box,Qt.ClipOperation.IntersectClip)
            for glyph,y,alpha in self.layers(key,char):
                painter.setOpacity(opacity*alpha)
                painter.drawText(box.translated(0,y*height),Qt.AlignmentFlag.AlignCenter,glyph)
            painter.restore()
        painter.restore()
