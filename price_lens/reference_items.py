"""Normalize incomplete exported item labels without altering verified payloads."""

# Exact scroll-family IDs plus the canonical name must agree. Never classify an
# unfamiliar scroll by a loose word match, or guess its success rate or effects.
SCROLL_FAMILIES={0:('Hat','Hat'),2:('Earring','Earring'),3:('Overall Armor','Overall'),
    4:('Topwear','Topwear'),6:('Bottomwear','Bottomwear'),7:('Shoes','Shoes'),
    8:('Gloves','Glove'),9:('Shield','Shield'),10:('Cape','Cape'),
    30:('One-Handed Sword','1H Sword'),31:('One-Handed Axe','1H Axe'),
    32:('One-Handed Blunt Weapon','1H Blunt'),33:('Dagger','Dagger'),
    37:('Wand','Wand'),38:('Staff','Staff'),40:('Two-Handed Sword','2H Sword'),
    41:('Two-Handed Axe','2H Axe'),42:('Two-Handed Blunt Weapon','2H Blunt'),
    43:('Spear','Spear'),44:('Polearm','Polearm'),45:('Bow','Bow'),
    46:('Crossbow','Crossbow'),47:('Claw','Claw'),80:('Pet Equip','Pet equipment')}


def normalize(row):
    scroll=row.get('scroll');identity=row.get('id')
    if not isinstance(scroll,dict) or type(identity) is not int or identity//10000!=204:return row
    family=SCROLL_FAMILIES.get(identity//100%100)
    if not family or not row.get('name','').startswith(family[0]+' '):return row
    result=dict(scroll)
    if scroll.get('slot') in (None,'','Other'):result['slot']=family[1]
    if scroll.get('stat')=='Other':
        keys=set((scroll.get('stats') or {}))
        if keys and keys<={'incPDD','incMDD'}:result['stat']='Defense'
        elif keys=={'incJump'}:result['stat']='Jump'
    return {**row,'scroll':result} if result!=scroll else row
