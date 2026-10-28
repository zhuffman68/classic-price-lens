"""Presentation of documented Classic World skill stages and stale rank text.

Cross-checked 2026-10-28 against bubbling.wiki/skills/{id} and NiaMeowDB's
Classic skill pages. Keep the downloaded records unchanged. Never interpolate
rank values: Rush and Power Knockback have real irregularities in the published
numeric data. See docs/DATABASE_SOURCES.md for the evidence and scope.
"""
import re


def skill_ranks(row):
    levels=[dict(level) for level in row.get('levels',[]) if isinstance(level,dict) and type(level.get('level')) is int]
    descriptions=list(row.get('level_descriptions') or [])
    notes={}
    identity=row.get('id');name=row.get('name')
    for level in levels:
        rank=level['level'];index=rank-1
        if not 0<=index<len(descriptions):continue
        original=descriptions[index]
        if identity in (1101005,1201005,1301005) and name=='Rush':
            # Both numeric exports agree; the English strings differ at these ranks.
            if (rank,level.get('damage')) in ((11,69),(14,74)):
                old={11:70,14:73}[rank]
                descriptions[index]=re.sub(rf'\bDamage {old}%',f"Damage {level['damage']}%",original)
            if rank==10 and level.get('range')==130:
                descriptions[index]=descriptions[index].replace('with 150 in distance','with 130 in distance')
            if descriptions[index]!=original:notes[rank]='Numeric rank data; the client description contains a different value.'
        elif identity==3001003 and name=='Power Knockback' and rank==8 and level.get('damage')==170:
            descriptions[index]=original.replace('Damage 140%','Damage 170%')
            if descriptions[index]!=original:notes[rank]='Numeric rank data; the client description says 140% at this rank.'
        elif identity==3101004 and name=='Arrow Bomb' and level.get('damage')==0 and level.get('mobCount')==1:
            # The zero belongs to the delivery arrow. The linked explosion is
            # confirmed in both current references; do not label the attack 0%.
            match=re.fullmatch(r'MP -(\d+); Stun chance (\d+)% for (\d+) sec, damage (\d+)%',original)
            if match:
                mp,chance,duration,damage=map(int,match.groups())
                expected_damage=130 if rank==30 else 68+2*rank
                expected_chance=60 if rank==30 else 29+rank
                if 1<=rank<=30 and mp==level.get('mpCon') and damage==expected_damage and chance==expected_chance and duration==2:
                    level.update(damage=damage,mobCount=6,prop=chance,time=duration)
                    notes[rank]='Explosion: up to six targets including the first enemy hit by the arrow.'
    return levels,descriptions,notes
