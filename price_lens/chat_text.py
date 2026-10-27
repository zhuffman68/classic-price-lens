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
GLOSSES = (
    (r"국산\s*팟(?:으로)?", "Korean-speaking party"),
    (r"(?:커파|커닝\s*파퀘|커닝\s*파티퀘스트)", "Kerning PQ"),
    (r"(?:러시|러쉬)\s*(?:팟|파티|짜)", "rush party"),
    (r"(?:보너스|보너쓰)\s*(?:팟|파티|짜)", "bonus party"),
    (r"(?:노가다\s*목장갑|노목)", "Work Gloves"),
    (r"장갑\s*공격력\s*주문서|장공", "Glove ATT scroll"),
    (r"홀리\s*심볼", "Holy Symbol"),
    (r"헤이스트", "Haste"), (r"하이퍼\s*바디", "Hyper Body"),
    (r"심심해(?:요)?", "I'm bored"),
    (r"초대\s*(?:점여|좀요|좀|점|해주세요|해줘요)", "please invite me"),
    (r"가실\s*분", "looking for people to join"),
    (r"(?:암데나|아무데나|어디든)", "any party"),
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
    return values(source) == values(translated) and currencies(source)==currencies(translated)
