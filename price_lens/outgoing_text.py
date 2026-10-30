"""English game-chat expansion and protected Korean drafts. No OS or network access."""
from dataclasses import dataclass
from decimal import Decimal
import re
import unicodedata

from .chat_text import HANGUL, numbers_preserved

LIMIT=300
NUMERAL=re.compile(r'(?<![0-9A-Za-z_.])([-+]?\d+(?:,\d{3})*(?:\.\d+)?)(?:\s*([kKmMbB](?![A-Za-z])|만|억))?(?:\s*(%|퍼센트|프로))?(?!\d|\.\d)')
ITEM_ALIASES={'wg':'Work Gloves'}
ALIASES={**ITEM_ALIASES,'kpq':'Kerning City party quest','pq':'party quest','fm':'Free Market',
         'gfa':'Glove ATT scroll','gma':'Glove Magic ATT scroll'}
# Language only, not modern-world rules or guessed regional item identities.
# Nexon: /Guide/GameInformation/SpecialContents/PartyQuest,
# /Guide/GameInformation/Terms/Tips_TravelContinent1, /News/Notice/All/120758,
# /news/update/630 and archive.maplestory.nexon.com/news/ProbabilityResult/MonthData.
GAME_TERMS={'Free Market':'자유시장','Kerning City':'커닝시티','Henesys':'헤네시스',
            'Ellinia':'엘리니아','Perion':'페리온','Glove ATT scroll':'장갑 공격력 주문서',
            'Glove Magic ATT scroll':'장갑 마력 주문서'}
CONTEXT_TERMS={'MapleStory':'메이플스토리','party quest':'파티퀘스트'}
STATS=('att','matt','str','dex','int','luk','hp','mp')
TIERS=('Lesser','Intermediate','Greater','Chaos')
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


def literal_spans(text,names=()):
    spans=[];folded=text.casefold()
    for name in sorted({name for name in names if len(name)>=3 and name.casefold() in folded},key=len,reverse=True):
        for match in re.finditer(r'(?<![A-Za-z0-9_])'+re.escape(name)+r'(?![A-Za-z0-9_])',text,re.I):
            if not any(match.start()<b and match.end()>a for a,b in spans):spans.append(match.span())
    for match in re.finditer(r'@[A-Za-z0-9_]{1,24}',text):
        if not any(match.start()<b and match.end()>a for a,b in spans):spans.append(match.span())
    return spans


def expand(text,names=()):
    text=clean(text)
    # Catalog names and explicit player handles are literal, even when they
    # contain a word that also happens to be chat shorthand or a game term.
    pieces={}
    for index,(start,end) in enumerate(sorted(literal_spans(text,names),reverse=True)):
        token='ZXE'+chr(65+index//26)+chr(65+index%26)+'EXZ'
        pieces[token]=text[start:end];text=text[:start]+token+text[end:]
    for pattern,value in EXPANSIONS:text=re.sub(pattern,value,text,flags=re.I)
    text=re.sub(r'\b(gfa|gma)\s+scrolls?\b',lambda m:ALIASES[m[1].casefold()],text,flags=re.I)
    text=re.sub(r'\b(?:'+ '|'.join(map(re.escape,ALIASES)) +r')\b',lambda m:ALIASES[m[0].casefold()],text,flags=re.I)
    text=re.sub(r'\bKerning\s+(?:City\s+)?(?:PQ|party\s+quests?)\b','Kerning City party quest',text,flags=re.I)
    text=re.sub(r'\bMaple\s+Story\b','MapleStory',text,flags=re.I)
    for token,value in pieces.items():text=text.replace(token,value)
    return re.sub(r'\s+',' ',text).strip()


def warnings(text):
    result=[]
    # These have multiple meanings and no sufficiently specific expansion here.
    if re.search(r'\b(?:pt|pc|ma|rmt)\b',text,re.I):result.append('Ambiguous shorthand kept as written; check the preview.')
    if re.search(r'\bin\s+\d+(?:\.\d+)?m\b',text,re.I):result.append('For time, write “minutes” explicitly; m can also mean million.')
    return result


def template(text,names=()):
    phrase=text.casefold().strip(' .!?')
    if phrase in SOCIAL and ('?' not in text or SOCIAL[phrase].endswith('?')):return SOCIAL[phrase]
    if HANGUL.search(text) and not re.search('[A-Za-z]',text):return text
    change=re.fullmatch(r'change (?:to )?channel\s+(\d+)[.!]?',text,re.I)
    if change:return change[1]+'채널로 이동해 주세요.'
    # Exact trading fragments preserve names/stats in English, as used on this
    # server. Grammar-bearing sentences continue to the local model instead.
    direct=game_phrase(text)
    if direct is not None:return direct
    direct=item_phrase(text,names)
    if direct is not None:return direct
    trade=re.match(r'^(buying|selling)\s+(.+)$',text,re.I)
    if trade and trade_fragment(trade[2],names):
        protected=protect(trade[2],names);body=protected.masked
        for source,target in TRADE_WORDS:body=re.sub(r'\b'+re.escape(source)+r'\b',target,body,flags=re.I)
        return ('구매: ' if trade[1].lower()=='buying' else '판매: ')+protected.restore(body)
    party=re.fullmatch(r'looking for\s*(?:(\d+)\s*(?:more\s*)?)?party members?(?:\s+(\d+))?(?:\s+(?:for\s+)?(Kerning City party quest|party quest))?(?:\s+(bonus|rush))?[.!]?',text,re.I)
    if party:
        amount=party[1] or party[2]
        place='커닝 파퀘 ' if (party[3] or '').casefold()=='kerning city party quest' else '파퀘 ' if party[3] else ''
        kind={'bonus':'보너스 ','rush':'러시 '}.get((party[4] or '').lower(),'')
        return place+kind+'파티원'+(' '+amount+'명' if amount else '')+' 구합니다.'
    return None


def game_phrase(text):
    """Complete, bounded grammar; unknown tails/negation stay with the model."""
    value=text.strip().rstrip('.!?').strip()
    activities={'MapleStory':'메이플스토리','a party quest':'파티퀘스트','the party quest':'파티퀘스트',
                'party quests':'파티퀘스트','party quest':'파티퀘스트',
                'Kerning City party quest':'커닝시티 파티퀘스트','the Kerning City party quest':'커닝시티 파티퀘스트'}
    for english,korean in activities.items():
        activity=re.escape(english)
        if re.fullmatch(r'do you play '+activity,value,re.I):return korean+'를 하시나요?'
        if re.fullmatch(r'are you (?:playing|doing) '+activity,value,re.I):return korean+'를 하고 계신가요?'
        if re.fullmatch(r'do you not play '+activity,value,re.I):return korean+'를 안 하시나요?'
        if re.fullmatch(r'are you not (?:playing|doing) '+activity,value,re.I):return korean+'를 안 하고 계신가요?'
        if '?' not in text:
            if re.fullmatch(r'I play '+activity,value,re.I):return korean+'를 해요.'
            if re.fullmatch(r'I am (?:playing|doing) '+activity,value,re.I):return korean+'를 하고 있어요.'
            if re.fullmatch(r'I do not play '+activity,value,re.I):return korean+'를 하지 않아요.'
            if re.fullmatch(r'I am not (?:playing|doing) '+activity,value,re.I):return korean+'를 하고 있지 않아요.'
            if re.fullmatch(r'I do not want to do '+activity,value,re.I):return korean+'를 하고 싶지 않아요.'
            if re.fullmatch(r'I want to (?:play|do) '+activity,value,re.I):return korean+'를 하고 싶어요.'
        if re.fullmatch(r'(?:can|may) I join (?:your )?'+activity,value,re.I):return korean+'에 참여해도 될까요?'
        if re.fullmatch(r'I (?:cannot|can[\'’]t) join (?:your )?'+activity,value,re.I):return korean+'에 참여할 수 없어요.'
        if re.fullmatch(r'(?:can|could|would) you explain (?:this|the) '+activity,value,re.I):return '이 '+korean+'를 설명해 주실 수 있나요?'
    return None


def trade_fragment(body,names):
    known=(*names,*ITEM_ALIASES.values(),'Glove ATT scroll','Glove Magic ATT scroll')
    literal=literal_spans(body,known)
    # A price/stat string alone is not an identified item, nor is arbitrary
    # English prose after a selling/buying prefix a translated listing.
    if not any(not body[a:b].startswith('@') for a,b in literal):return False
    remaining=body
    for start,end in sorted(literal,reverse=True):remaining=remaining[:start]+' '+remaining[end:]
    if '?' in remaining:return False
    remaining=NUMERAL.sub(' ',remaining)
    for word in (*STATS,*TIERS,'clean','unscrolled','scrolled',*(word for word,_ in TRADE_WORDS)):
        remaining=re.sub(r'(?<!\w)'+re.escape(word)+r'(?!\w)',' ',remaining,flags=re.I)
    return not re.search(r'[\w]',remaining)


def item_phrase(text,names):
    """Unambiguous full listing sentences with an exact known item identity."""
    if text.rstrip().endswith('?'):return None
    value=text.strip().rstrip('.!').strip()
    known={name.casefold():name for name in (*names,*ITEM_ALIASES.values())}
    amount=r'[-+]?\d+(?:,\d{3})*(?:\.\d+)?(?:\s*(?:[kKmMbB](?![A-Za-z])|만|억))?(?:\s+mesos?)?'
    quantity=re.fullmatch(r'I (?P<action>want to buy|would like to buy|am selling|have) (?P<count>\d+) (?P<item>.+?) for (?P<price>'+amount+r') (?:each|apiece|per item)',value,re.I)
    if quantity and quantity['item'].casefold() in known:
        item=known[quantity['item'].casefold()];count=quantity['count'];price=quantity['price']
        action=quantity['action'].casefold()
        if action=='have':return f'{item} {count}개가 있어요. 가격은 개당 {price}입니다.'
        return f'{item} {count}개를 개당 {price}에 '+('판매하고 있어요.' if action=='am selling' else '구매하고 싶어요.')
    negative=re.fullmatch(r'I (?:am not selling|do not sell|don[\'’]t sell) (?P<item>.+?) for (?P<price>'+amount+r')',value,re.I)
    if negative and negative['item'].casefold() in known:
        return f"{known[negative['item'].casefold()]} 아이템을 {negative['price']}에 판매하지 않아요."
    return None


def term_particles(text,korean):
    """Fix only an adjacent, complete postposition after a verified Korean noun."""
    final=ord(korean[-1])-ord('가')
    if not 0<=final<11172:return text
    consonant=final%28
    pairs={'을':'을' if consonant else '를','를':'을' if consonant else '를',
           '은':'은' if consonant else '는','는':'은' if consonant else '는',
           '이':'이' if consonant else '가','가':'이' if consonant else '가',
           '과':'과' if consonant else '와','와':'과' if consonant else '와',
           '으로':'으로' if consonant not in (0,8) else '로','로':'으로' if consonant not in (0,8) else '로',
           '을(를)':'을' if consonant else '를','이(가)':'이' if consonant else '가',
           '은(는)':'은' if consonant else '는'}
    forms='|'.join(re.escape(value) for value in sorted(pairs,key=len,reverse=True))
    return re.sub(re.escape(korean)+'('+forms+r')(?=\s|[.!?,]|$)',lambda m:korean+pairs[m[1]],text)


@dataclass
class Protected:
    source:str
    masked:str
    replacements:dict
    required_terms:tuple=()

    def restore(self,translated):
        text=translated
        # Keep these familiar English nouns visible during inference so “do a
        # party quest” is not interpreted as making an unknown object. Item
        # names are still opaque here, so normalization cannot touch them.
        for english,korean in self.required_terms:
            text=re.sub(r'(?<![A-Za-z0-9_])'+re.escape(english)+r's?(?![A-Za-z0-9_])',korean,text,flags=re.I)
            text=re.sub('\\s*'.join(map(re.escape,korean)),korean,text)
            if korean not in text:raise ValueError('A game term could not be preserved. Try rephrasing the message.')
            text=term_particles(text,korean)
        for token,value in self.replacements.items():
            pattern=r'\s*'.join(map(re.escape,token))
            if len(re.findall(pattern,text,flags=re.I))!=1:raise ValueError('A protected name or number could not be preserved. Try a shorter message.')
            text=re.sub(pattern,lambda _:value,text,flags=re.I)
            if value in GAME_TERMS.values():text=term_particles(text,value)
        return clean(text)


def protect(text,names=()):
    spans=literal_spans(text,(*names,*ITEM_ALIASES.values()));overrides={};required=[]
    for name,korean in sorted(GAME_TERMS.items(),key=lambda pair:-len(pair[0])):
        for match in re.finditer(r'(?<!\w)'+re.escape(name)+r'(?!\w)',text,re.I):
            if not any(match.start()<b and match.end()>a for a,b in spans):
                spans.append(match.span());overrides[match.span()]=korean
    for english,korean in CONTEXT_TERMS.items():
        if any(not any(match.start()<b and match.end()>a for a,b in spans)
               for match in re.finditer(r'(?<!\w)'+re.escape(english)+r's?(?!\w)',text,re.I)):
            required.append((english,korean))
    stat=r'\b\d+(?:\.\d+)?\s*(?:'+ '|'.join(STATS) +r')\b(?!\s+(?:potions?|pots?)\b)'
    for match in re.finditer(stat,text,re.I):
        if not any(match.start()<b and match.end()>a for a,b in spans):spans.append(match.span())
    for match in re.finditer(r'\b(?:'+ '|'.join(STATS) +r')\b',text,re.I):
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
    return Protected(text,masked,replacements,tuple(required))


def validate(source,output,names=()):
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
    semantic=source
    for start,end in sorted(literal_spans(semantic,(*names,*ITEM_ALIASES.values())),reverse=True):semantic=semantic[:start]+' '+semantic[end:]
    if semantic.rstrip().endswith('?') and not re.search(r'[?？]|(?:나요|니까|까요|는지)[.!]?$',output):
        raise ValueError('The translation lost the question. Try rephrasing; it was not copied.')
    negative=r"\b(?:no|not|never|cannot|can['’]t|don['’]t|doesn['’]t|didn['’]t|won['’]t|wouldn['’]t|couldn['’]t|shouldn['’]t)\b"
    known_social=SOCIAL.get(semantic.casefold().strip(' .!?'))==output
    if not known_social and re.search(negative,semantic,re.I) and not re.search(r'않|못|아니|아닌|아닙|아님|아닐|아냐|없|안\s|마(?:세요|십시오|라|요)|말아|모르|몰라|불가|금지',output):
        raise ValueError('The translation may have lost a negation. Try rephrasing; it was not copied.')
    if re.search(r'(?:\beach|\bapiece|\bper item)[.!]?$',semantic,re.I) and any(NUMERAL.finditer(semantic)):
        if not re.search(r'개당|각각|하나당|한\s*개(?:당|에)|씩',output):
            raise ValueError('The translation lost the per-item price or count. Try rephrasing; it was not copied.')
    remaining=output
    for start,end in sorted(literal_spans(remaining,(*names,*ITEM_ALIASES.values())),reverse=True):remaining=remaining[:start]+' '+remaining[end:]
    remaining=NUMERAL.sub(' ',remaining)
    for word in (*STATS,*(TIERS if re.search(r'\b(?:scroll|tier)\b',source,re.I) else ()), 'NX'):
        if re.search(r'(?<![A-Za-z0-9_])'+re.escape(word)+r'(?![A-Za-z0-9_])',source,re.I):
            remaining=re.sub(r'(?<![A-Za-z0-9_])'+re.escape(word)+r'(?![A-Za-z0-9_])',' ',remaining,flags=re.I)
    if re.search(r'[A-Za-z]',remaining):
        raise ValueError('Some words were not translated or identified. Rephrase them, or use @ before a player name; it was not copied.')
    if len(output)>600:raise ValueError('The translated draft is too long. Try a shorter message.')
    return output
