"""Conservative Korean game-chat glosses and exact, explicit price units.

No inferred scale for a bare number. This glossary describes language, not
mechanics imported from another MapleStory world.
"""
from decimal import Decimal
import re
import unicodedata

HANGUL = re.compile(r"[\u1100-\u11ff\u3130-\u318f\uac00-\ud7a3]")
NUMBER = re.compile(r"(?<![0-9a-zA-Z_.])([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)(?:\s*(억|만|[kKmM](?![a-zA-Z])))?")


def compact(value):
    value = Decimal(value)
    for scale, suffix in ((Decimal(1000000), "m"), (Decimal(1000), "k")):
        if value >= scale:
            return format(value / scale, "f").rstrip("0").rstrip(".") + suffix if value % scale else str(int(value/scale)) + suffix
    return format(value, "f").rstrip("0").rstrip(".") if value % 1 else str(int(value))


def amounts(text):
    """Return raw numerals separately from amounts with an explicitly stated unit."""
    out = []
    for match in NUMBER.finditer(text):
        value = Decimal(match[1].replace(",", ""))
        unit = match[2]
        scale = {"억": 100000000, "만": 10000, "k": 1000, "m": 1000000}.get((unit or "").lower())
        out.append({"raw": match[0].strip(), "number": str(value), "amount": str(value*scale) if scale else None,
                    "display": compact(value*scale) if scale else match[1]})
    return out


def normalize(text):
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"[@#%]{2,}", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:500]


# Match phrases before their shorter components. Do not replace 심 inside 심심해,
# 공 inside 공팟, or 삼 (three) as a buying verb.
NOUN_GLOSSES = (
    (r"국산\s*팟(?:으로)?", "Korean-speaking party"),
    (r"(?:커파|커닝\s*파퀘|커닝\s*파티퀘스트)", "Kerning PQ"),
    (r"(?:러시|러쉬)\s*(?:팟|파티|짜)", "rush party"),
    (r"(?:보너스|보너쓰)\s*(?:팟|파티|짜)", "bonus party"),
    (r"(?:노가다\s*목장갑|노목)", "Work Gloves"),
    (r"장갑\s*공격력\s*주문서|장공", "Glove ATT scroll"),
    (r"홀리\s*심볼", "Holy Symbol"),
    (r"헤이스트", "Haste"), (r"하이퍼\s*바디", "Hyper Body"),
    (r"킹\s*슬라임", "King Slime"),
)
GLOSSES = NOUN_GLOSSES + (
    (r"심심해(?:요)?", "I'm bored"),
    (r"초대\s*(?:점여|좀요|좀|점|해주세요|해줘요)", "please invite me"),
    (r"가실\s*분", "looking for people to join"),
    (r"(?:아무\s*(?:파티|팟)(?:나|든|도)?|암데나|아무데나|어디든)", "any party"),
    (r"갑니다|갈게요|가요", "I'd like to join"),
    (r"파티\s*구해요|파티\s*구함|파티\s*구합니다", "looking for a party"),
    (r"귓속말\s*주세요|귓말\s*주세요|귓\s*주세요", "whisper me"),
    (r"팝니다|팔아요|판매(?:합니다)?", "for sale"),
    (r"삽니다|사요|구매(?:합니다)?", "buying"),
    (r"감사합니다|고마워요", "thank you"), (r"죄송합니다|미안해요", "sorry"),
    (r"안녕하세요|안녕", "hello"), (r"자리요", "this spot is taken"),
    (r"공격력", "ATT"), (r"보너스", "bonus"),
    (r"표도", "throwing-star thief"), (r"클레(?:릭)?", "Cleric"),
    (r"전사", "Warrior"), (r"법사", "Mage"), (r"궁수", "Archer"),
    (r"러시나|러쉬나", "rush or"), (r"메소(?:에)?", "mesos"),
    (r"주세요", "please"), (r"구함|구해요", "looking for"),
)
SOCIAL = {"ㅎㅇ":"hi", "ㅇㅇ":"yes", "ㄴㄴ":"no", "ㄱㄱ":"let's go", "ㄱㅅ":"thanks", "ㄳ":"thanks", "ㅈㅅ":"sorry", "ㅇㅋ":"okay"}
PEOPLE={"한":"one","두":"two","세":"three","네":"four","다섯":"five","여섯":"six","일곱":"seven","여덟":"eight","아홉":"nine","열":"ten"}
JOBS={"전사":"Warrior","법사":"Mage","궁수":"Archer","도적":"Thief","표도":"throwing-star thief","클레":"Cleric","클레릭":"Cleric"}
PARTIES={"보너스":"bonus","보너스팟":"bonus party","보너스파티":"bonus party","러시팟":"rush party","러쉬팟":"rush party","커파":"Kerning PQ"}


def message_key(text):
    """Spacing/repeated emphasis only; preserve questions, negation and units."""
    return re.sub(r'([!?])\1+',r'\1',re.sub(r'\s+','',normalize(text))).casefold()


def recruiting_phrase(text):
    """Complete, explicit party/count or job/join structures, never a substring."""
    value=re.sub(r'\s+','',normalize(text))
    # Complete requests only: source options, a joining verb and any-party
    # language must all be explicit. Unknown tails/negation never match.
    activity=r'(?:보너스|보너쓰|러시|러쉬)(?:팟|파티)?'
    match=re.fullmatch(rf'({activity})(?:(?:이나|나|또는|혹은|/|,|랑|와)?({activity}))?아무(?:파티|팟)(?:나|든|도)?(?:다)?(?:감|가요|갑니다|갈게요|갈께요)([!.]*)',value)
    if match:
        first,second,punctuation=match.groups();options=[]
        for word in (first,second):
            if word:
                name='bonus' if word.startswith(('보너스','보너쓰')) else 'rush'
                if name not in options:options.append(name)
        return "I'll join any "+' or '.join(options)+' party'+punctuation
    match=re.fullmatch(r'(?:(커파|커닝파퀘|커닝파티퀘스트))?킹슬라임(?:을|를)?(?:딱)?(한번|1번)(만)?(?:같이)?(?:잡으실|잡을|잡을수있는)분(?:구함|구해요|모집)?([0-9]{1,2}/[0-9]{1,2})?([!.]*)',value)
    if match:
        context,times,only,occupancy,punctuation=match.groups()
        count='once' if times=='한번' else '1 time'
        return ('Kerning PQ · ' if context else '')+'Looking for someone to defeat King Slime '+('just ' if only else '')+count+(f' · {occupancy}' if occupancy else '')+punctuation
    parties='|'.join(sorted(PARTIES,key=len,reverse=True));counts='|'.join(PEOPLE)
    invite=r'(?:팟|파티)(?:점여|점요|좀여|좀요|주세요|부탁해요)|초대(?:점여|점요|좀여|좀요|좀|해주세요|부탁해요)'
    match=re.fullmatch(rf'({parties})?({invite})([!?!.]*)',value)
    if match:
        party,request,punctuation=match.groups()
        if not party and request.startswith('초대'):return 'Please invite me'+punctuation
        name=PARTIES.get(party,'')
        if name and not name.endswith('party'):name+=' party'
        return f"Please invite me to {'the '+name if party else 'a party'}{punctuation}"
    match=re.fullmatch(rf'({parties})({counts}|[0-9]{{1,3}})(?:명|분)(?:구함|구해요|구합니다|모집합니다|모집)([!.]*)',value)
    if match:
        party,count,punctuation=match.groups();number=PEOPLE.get(count,count)
        return f"Looking for {number} {'person' if count in ('한','1') else 'people'} for {PARTIES[party]}{punctuation}"
    match=re.fullmatch(rf'({parties})({'|'.join(JOBS)})(?:도)?(?:껴주시나요|끼워주시나요|받아주시나요|참여가능한가요|참여가능할까요)([?!.]*)',value)
    if match:
        party,job,punctuation=match.groups()
        article='an' if JOBS[job][0].casefold() in 'aeiou' else 'a'
        return f"Are you taking {article} {JOBS[job]} for the {PARTIES[party]}{punctuation or '?'}"
    return None


def supported_ocr_alternative(original,candidates):
    """One uncertain model-emitted syllable may complete an explicit phrase.

    This is not spelling search: the OCR model must supply the alternative,
    numbers/non-Korean characters stay exact, and the complete phrase must parse.
    Ambiguous equally supported phrases remain uncorrected.
    """
    first=normalize(original)
    if recruiting_phrase(first) is not None:return None
    supported=[]
    for text,confidence in list(candidates)[:8]:
        other=normalize(text)
        if len(other)!=len(first) or not numbers_preserved(first,other):continue
        changes=[(a,b) for a,b in zip(first,other) if a!=b]
        if len(changes)!=1 or not all('가'<=a<='힣' and '가'<=b<='힣' for a,b in changes):continue
        if not isinstance(confidence,(int,float)) or not .35<=confidence<=1:continue
        if recruiting_phrase(other) is not None:supported.append((other,confidence))
    if not supported:return None
    supported.sort(key=lambda row:-row[1])
    if len({text for text,_ in supported})>1:return None
    return supported[0][0]


def model_source(text):
    """Expand established game nouns; ordinary sentence grammar stays intact."""
    required=[];value=normalize(text)
    nouns=NOUN_GLOSSES+tuple((re.escape(k),JOBS[k]) for k in sorted(JOBS,key=len,reverse=True))
    if re.search(r'아무|구함|구해|모집|초대|감(?:[!.]|$)|갑니다|가요|갈게요',text):
        nouns += ((r'아무\s*(?:파티|팟)(?:나|든|도)?','any party'),(r'보너스|보너쓰','bonus'),(r'러시|러쉬','rush'))
    for pattern,english in nouns:
        value,count=re.subn(pattern,lambda _:f' {english} ',value)
        if count:required.append(english)
    # Honorific 분 is a person counter only in explicit recruitment context.
    if re.search(r'구함|구해|구합니다|모집|초대|껴|끼워|가실',text):
        def person(match):
            phrase=f"{PEOPLE[match[1]]} {'person' if match[1]=='한' else 'people'}"
            required.append(phrase);return f' {phrase} '
        value=re.sub(r'(?<![가-힣])('+'|'.join(PEOPLE)+r')\s*(?:명|분)',person,value)
    return re.sub(r'\s+',' ',value).strip(),tuple(required)


def terms_preserved(required,translated):
    value=translated.casefold()
    return all(term.casefold() in value for term in required)


def unknown_shorthand(text):
    if normalize(text) in SOCIAL:return False
    return any(not re.fullmatch(r'[ㅋㅎ]+|[ㅠㅜ]+',value)
               for value in re.findall(r'[\u3130-\u318f\u1100-\u11ff]+',text))


def glossary(text, partial=False):
    """An explicit gloss only when all Korean words are covered; otherwise None."""
    text = normalize(text)
    if text in SOCIAL:
        return SOCIAL[text]
    if re.fullmatch(r"[ㅋㅎ]{2,}", text): return "lol"
    if re.fullmatch(r"[ㅠㅜ]{2,}", text): return "(crying)"
    # Ambiguous party-full/selling shorthand needs trade context.
    if re.fullmatch(r"ㅍㅍ\??", text): return None
    text = re.sub(r"(?<!\d)(\d{1,3})\s*(?=표도|클레|전사|법사|궁수)", r"Lv. \1 ", text)
    pieces = []
    for pattern, english in GLOSSES:
        def replace(match):
            pieces.append(english)
            return " \x01" + str(len(pieces)-1) + "\x02 "
        text = re.sub(pattern, replace, text)
    text = re.sub(r"(?<=\d)\s*(만|억)", lambda m:" "+m[1],text)
    def number(match):
        return amounts(match[0])[0]["display"]
    text = NUMBER.sub(number, text)
    # Numbers inside placeholders are not amounts and are restored verbatim.
    text = re.sub(r"\x01\s*(\d+)\s*\x02", lambda m:pieces[int(m[1])], text)
    if HANGUL.search(text) and not (partial and pieces): return None
    return re.sub(r"\s+", " ", text).strip()


def numbers_preserved(source, translated):
    """Reject invented/dropped numeric values, including a changed Korean scale."""
    def values(text):
        return sorted(Decimal(x["amount"] or x["number"]) for x in amounts(text))
    def currencies(text):
        result=set()
        if re.search(r"메소|\bmesos?\b",text,re.I):result.add("mesos")
        if re.search(r"\d[\d,.]*(?:만|억)?\s*원|\b(?:won|KRW)\b",text,re.I):result.add("won")
        if re.search(r"\$|\b(?:USD|dollars?)\b",text,re.I):result.add("dollars")
        return result
    def percentages(text):
        return sorted(Decimal(amounts(match[0])[0]['amount'] or amounts(match[0])[0]['number'])
                      for match in NUMBER.finditer(text)
                      if re.match(r'\s*(?:%|퍼센트|프로|percent\b)',text[match.end():],re.I))
    return values(source) == values(translated) and currencies(source)==currencies(translated) and percentages(source)==percentages(translated)
