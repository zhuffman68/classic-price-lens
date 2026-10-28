"""Inline currency art for GUI text; game-overlay descriptions remain plain text."""
import html
import re
from functools import lru_cache
from pathlib import Path
from PySide6.QtCore import QRectF,Qt,QUrl
from PySide6.QtGui import QTextDocument,QTextOption
from PySide6.QtSvg import QSvgRenderer

PATTERN=re.compile(r'\bmesos?\b',re.IGNORECASE)
TOKEN='\ufffc'
ICON=Path(__file__).parent/'resources/meso.svg'


def visual_text(text):return PATTERN.sub(TOKEN,text)


def icon_size(metrics):return max(12,min(18,metrics.height()-2))


@lru_cache(maxsize=1)
def renderer():return QSvgRenderer(str(ICON))


def paint_icon(painter,box):
    side=min(box.width()-2,box.height())
    renderer().render(painter,QRectF(box.x()+1,box.y()+(box.height()-side)/2,side,side))


def line_width(text,metrics):
    return sum(icon_size(metrics)+2 if c==TOKEN else metrics.horizontalAdvance(c) for c in visual_text(text))


def document(widget):
    colour=widget.palette().color(widget.foregroundRole()).name()
    width=widget.contentsRect().width() if widget.wordWrap() else -1
    key=(widget.text(),widget.font().toString(),colour,width,int(widget.alignment()))
    if key==getattr(widget,'_currency_key',None):return widget._currency_doc
    doc=QTextDocument();doc.setDocumentMargin(0);doc.setDefaultFont(widget.font())
    option=QTextOption();option.setAlignment(widget.alignment() & (Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignHCenter|Qt.AlignmentFlag.AlignJustify))
    doc.setDefaultTextOption(option)
    size=icon_size(widget.fontMetrics())
    image=f'<img src="{QUrl.fromLocalFile(str(ICON)).toString()}" width="{size}" height="{size}" style="vertical-align:middle">'
    content=PATTERN.sub(lambda _:image,html.escape(widget.text())).replace('\n','<br>')
    doc.setHtml(f'<span style="color:{colour}">{content}</span>');doc.setTextWidth(width)
    widget._currency_key,widget._currency_doc=key,doc
    return doc


def paint_document(widget,painter,opacity):
    doc=document(widget);rect=widget.contentsRect();height=doc.size().height()
    top=rect.y() if widget.alignment()&Qt.AlignmentFlag.AlignTop else rect.bottom()-height if widget.alignment()&Qt.AlignmentFlag.AlignBottom else rect.y()+(rect.height()-height)/2
    painter.save();painter.setOpacity(opacity);painter.setClipRect(rect);painter.translate(rect.x(),top)
    doc.drawContents(painter);painter.restore()
