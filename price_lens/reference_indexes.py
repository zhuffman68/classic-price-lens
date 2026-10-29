"""Read public release indexes; canonical IDs and names must independently agree."""
from html.parser import HTMLParser
import re
from .domain import key


class ReleaseIndex(HTMLParser):
    def __init__(self,kind):
        super().__init__();self.kind=kind;self.tag=None;self.identity=None;self.words=[];self.rows={};self.ambiguous=set()

    def handle_starttag(self,tag,attrs):
        if self.tag:return
        attrs=dict(attrs)
        match=(re.fullmatch(r'/msclassic/(?:en/)?maps/(\d{1,10})',attrs.get('href','')) if self.kind=='maps' and tag=='a'
            else re.fullmatch(r'quest-(\d{1,10})',attrs.get('aria-controls','')) if self.kind=='quests' and tag=='button' else None)
        if match:self.tag=tag;self.identity=int(match[1]);self.words=[]

    def handle_data(self,value):
        if self.tag:self.words.append(value)

    def handle_endtag(self,tag):
        if tag!=self.tag:return
        text=''.join(self.words).strip();identity=self.identity;self.tag=None
        if identity in self.rows and self.rows[identity]!=text:self.rows.pop(identity);self.ambiguous.add(identity)
        if identity not in self.ambiguous:self.rows[identity]=text


def release_name(kind,row,label):
    name=key(row['name']);label=key(label).removeprefix('+ ').removesuffix(' (town)').strip()
    if name==label:return True
    chain=row.get('chain')
    region=row.get('region')
    suffix=r'(?: \('+re.escape(key(region))+r'\))?' if region in ('Warrior','Magician','Bowman','Thief') else ''
    return bool(kind=='quests' and chain and re.fullmatch(re.escape(key(chain))+r'\s+\(\d+[a-z]?\)\s*'+re.escape(name)+suffix,label))
