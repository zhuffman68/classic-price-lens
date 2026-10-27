"""English game-chat expansion and protected Korean drafts. No OS or network access."""
from dataclasses import dataclass
from decimal import Decimal
import re
import unicodedata

from .chat_text import HANGUL, numbers_preserved

LIMIT=300
NUMERAL=re.compile(r'(?<![0-9A-Za-z_.])([-+]?\d+(?:,\d{3})*(?:\.\d+)?)(?:\s*([kKmMbB](?![A-Za-z])|만|억))?(?:\s*(%|퍼센트|프로))?(?!\d|\.\d)')
ALIASES={'wg':'Work Gloves','kpq':'Kerning PQ','pq':'party quest','fm':'Free Market',
         'gfa':'Glove ATT scroll','gma':'Glove Magic ATT scroll'}
EXPANSIONS=(
    (r'\bty\s*(?:4|for)\s*pt\b','thank you for the party'),
    (r'\bno\s+nego\b','fixed price'),(r'\bpmo\b','please whisper me your offer'),
    (r'\bc\s*/\s*o\b','current offer'),(r'\bs\s*/\s*b\b','starting bid'),
    (r'\ba\s*/\s*w\b','buyout price'),(r'\bobo\b','or best offer'),
    (r'\bLF(\d+)M\b',lambda m:'looking for '+m[1]+' more party members'),
    (r'\bLFM\b','looking for party members'),(r'\bLFG\b','looking for a party'),
    (r'\bWTB\b|^\s*B\s*>\s*','buying '),(r'\bWTS\b|^\s*S\s*>\s*','selling '),
    (r'^\s*R\s*>\s*','recruiting '),(r'^\s*J\s*>\s*','joining '),
    (r'\bLF\b','looking for'),(r'\bea\b','each'),(r'\bfirm\b','fixed price'),
    (r'\bnego\b','negotiable'),(r'\b(?:pm|dm)\s+me\b','whisper me'),
    (r'\b(?:pls|plz)\b','please'),(r'\b(?:ty|thx|tyvm)\b','thank you'),
    (r'\binv\s+me\b','please invite me'),(r'\br\s+u\b','are you'),
    (r'\bu\b','you'),(r'\bur\b','your'),(r'\blmk\b','let me know'),
    (r'\brn\b','right now'),(r'\bomw\b','I am on my way'),
    (r'\bnp\b','no problem'),(r'\bbrb\b','I will be right back'),
    (r'\bafk\b','away from keyboard'),(r'\bnvm\b','never mind'),
    (r'\bidk\b','I do not know'),(r'\b(?:grats|gz|gratz)\b','congratulations'),
    (r'\bgg\b','good game'),(r'\bcc\s*(\d+)\b',r'change to channel \1'),
    (r'\bcc\b','change channel'),(r'\bch\s*(\d+)\b',r'channel \1'),
    (r'\blv(?:l)?\.?\s*(\d+)\b',r'level \1'),
    (r'(\d+)\s*(att|matt|str|dex|int|luk)\b',r'\1 \2'),
    (r'\bPC(?=\s+(?:on|for)\b)','price check'),
)
SOCIAL={
    'hi':'안녕하세요.','hello':'안녕하세요.','hey':'안녕하세요.',
    'thank you':'감사합니다.','thank you for the party':'파티 감사해요.',
    'no problem':'괜찮아요.','sorry':'죄송해요.','okay':'알겠어요.',
    'how much is it':'얼마인가요?','is it still available':'아직 판매 중인가요?',
    'can you lower the price':'조금 깎아 주실 수 있나요?',
    'can i join your party':'파티에 참여해도 될까요?',
    'please invite me':'초대해 주세요.','i am on my way':'지금 가고 있어요.',
    'looking for a party':'파티 구합니다.',
    'i will be right back':'잠시 후에 돌아올게요.','away from keyboard':'잠시 자리 비웁니다.',
    'never mind':'신경 쓰지 마세요.','i do not know':'모르겠어요.',
    'congratulations':'축하해요!','good game':'수고하셨어요.',
    'lol':'ㅋㅋㅋ','haha':'ㅎㅎ','lmao':'ㅋㅋㅋ',
    'i do not speak korean':'한국어를 못해요.',
    'whisper me':'귓말 주세요.','please whisper me your offer':'가격 제안은 귓말 주세요.',
}
TRADE_WORDS=(
    ('please whisper me your offer','가격 제안은 귓말 주세요'),
    ('or best offer','좋은 가격 제안 받아요'),('current offer','현재 제시가'),
    ('starting bid','시작가'),('buyout price','즉구가'),('fixed price','흥정 불가'),
    ('negotiable','흥정 가능'),('whisper me','귓말 주세요'),('each','개당'),('mesos','메소'),('meso','메소'),
)


def clean(text):
    text=unicodedata.normalize('NFC',str(text))
    text=''.join(c for c in text if c in '\n\r\t' or not unicodedata.category(c).startswith('C'))
    return re.sub(r'\s+',' ',text).strip()


def expand(text):
    text=clean(text)
    for pattern,value in EXPANSIONS:text=re.sub(pattern,value,text,flags=re.I)
    text=re.sub(r'\b(?:'+ '|'.join(map(re.escape,ALIASES)) +r')\b',lambda m:ALIASES[m[0].casefold()],text,flags=re.I)
    return re.sub(r'\s+',' ',text).strip()


def warnings(text):
    result=[]
    # These have multiple meanings and no sufficiently specific expansion here.
    if re.search(r'\b(?:pt|pc|ma|rmt)\b',text,re.I):result.append('Ambiguous shorthand kept as written; check the preview.')
    if re.search(r'\bin\s+\d+(?:\.\d+)?m\b',text,re.I):result.append('For time, write “minutes” explicitly; m can also mean million.')
    return result


def template(text,names=()):
    phrase=text.casefold().strip(' .!?')
    if phrase in SOCIAL:return SOCIAL[phrase]
    if HANGUL.search(text) and not re.search('[A-Za-z]',text):return text
    change=re.fullmatch(r'change (?:to )?channel\s+(\d+)[.!]?',text,re.I)
    if change:return change[1]+'채널로 이동해 주세요.'
    # Exact trading fragments preserve names/stats in English, as used on this
    # server. Grammar-bearing sentences continue to the local model instead.
    trade=re.match(r'^(buying|selling)\s+(.+)$',text,re.I)
    if trade and not re.search(r'\b(?:because|when|where|would|could|my|this|that|have|need)\b',trade[2],re.I):
        protected=protect(trade[2],names);body=protected.masked
        for source,target in TRADE_WORDS:body=re.sub(r'\b'+re.escape(source)+r'\b',target,body,flags=re.I)
        return ('구매: ' if trade[1].lower()=='buying' else '판매: ')+protected.restore(body)
    party=re.fullmatch(r'looking for\s*(?:(\d+)\s*(?:more\s*)?)?party members?(?:\s+(\d+))?(?:\s+(?:for\s+)?(Kerning PQ|party quest))?(?:\s+(bonus|rush))?[.!]?',text,re.I)
    if party:
        amount=party[1] or party[2]
        place='커닝 파퀘 ' if (party[3] or '').casefold()=='kerning pq' else '파퀘 ' if party[3] else ''
        kind={'bonus':'보너스 ','rush':'러시 '}.get((party[4] or '').lower(),'')
        return place+kind+'파티원'+(' '+amount+'명' if amount else '')+' 구합니다.'
    return None


@dataclass
class Protected:
    source:str
    masked:str
    replacements:dict

    def restore(self,translated):
        text=translated
        for token,value in self.replacements.items():
            pattern=r'\s*'.join(map(re.escape,token))
            if len(re.findall(pattern,text,flags=re.I))!=1:raise ValueError('A protected name or number could not be preserved. Try a shorter message.')
            text=re.sub(pattern,lambda _:value,text,flags=re.I)
        return clean(text)


def protect(text,names=()):
    spans=[];overrides={}
    names=(*names,*ALIASES.values(),'Kerning City','Henesys','Ellinia','Perion')
    folded=text.casefold()
    for name in sorted({name for name in names if name.casefold() in folded},key=len,reverse=True):
        if len(name)<3:continue
        for match in re.finditer(r'(?<!\w)'+re.escape(name)+r'(?!\w)',text,re.I):
            if not any(match.start()<b and match.end()>a for a,b in spans):spans.append(match.span())
    for match in re.finditer(r'\blevel\s+(\d+)\b',text,re.I):
        if not any(match.start()<b and match.end()>a for a,b in spans):
            spans.append(match.span());overrides[match.span()]='레벨 '+match[1]
    # Keep numeric literals visible to the model for normal Korean word order;
    # validate their exact value/unit/percent after inference, before copying.
    for pattern in (re.compile(r'@[A-Za-z0-9_]{1,24}'),):
        for match in pattern.finditer(text):
            if not any(match.start()<b and match.end()>a for a,b in spans):spans.append(match.span())
    replacements={};masked=text
    alphabet='ABCDEFGHIJKLMNOPRSTUVWY'
    if len(spans)>len(alphabet):raise ValueError('There are too many protected values. Split this into shorter messages.')
    for index,(start,end) in enumerate(sorted(spans,reverse=True)):
        token='ZXQ'+alphabet[index]+'QXZ'
        replacements[token]=overrides.get((start,end),text[start:end]);masked=masked[:start]+token+masked[end:]
    return Protected(text,masked,replacements)


def validate(source,output):
    if not output or '\ufffd' in output or '⁇' in output or not HANGUL.search(output):
        raise ValueError('The local model could not produce a readable Korean draft. Try rephrasing.')
    currency_text=lambda value:re.sub(r'(?<![A-Za-z])mesos?(?![A-Za-z])','메소',value,flags=re.I)
    if not numbers_preserved(currency_text(source),currency_text(output)):
        raise ValueError('The translation changed a number, unit or percentage. It was not copied.')
    def identity(match):
        value=Decimal(match[1].replace(',',''))*{'k':1000,'m':1000000,'b':1000000000,'만':10000,'억':100000000}.get((match[2] or '').lower(),1)
        return value,bool(match[3])
    originals=list(NUMERAL.finditer(source));translated=list(NUMERAL.finditer(output))
    available=list(originals);replacements=[]
    for match in translated:
        original=next((m for m in available if identity(m)==identity(match)),None)
        if original is None:raise ValueError('The translation changed a number, unit or percentage. It was not copied.')
        available.remove(original);replacements.append((match.span(),original[0]))
    if available:raise ValueError('The translation changed a number, unit or percentage. It was not copied.')
    for (start,end),literal in reversed(replacements):output=output[:start]+literal+output[end:]
    if re.search(r'ZXQ[A-Z\s]+QXZ',output,re.I):raise ValueError('A protected item name was not restored.')
    if len(output)>600:raise ValueError('The translated draft is too long. Try a shorter message.')
    return output
