"""Resolved source conflicts must not turn into invented rank progressions."""
from copy import deepcopy
import unittest
from price_lens.reference_skills import skill_ranks


class SkillReferences(unittest.TestCase):
    def test_rush_uses_numeric_ranks_without_smoothing_and_preserves_raw_source(self):
        for identity in (1101005,1201005,1301005):
            row={'id':identity,'name':'Rush','levels':[{'level':10,'damage':69,'range':130},{'level':11,'damage':69},{'level':14,'damage':74}],
                 'level_descriptions':['']*9+['MP -26; Rush, with 150 in distance; Damage 69%','Damage 70%','','','Damage 73%']}
            raw=deepcopy(row);levels,descriptions,notes=skill_ranks(row)
            self.assertEqual([l['damage'] for l in levels],[69,69,74]);self.assertIn('130 in distance',descriptions[9])
            self.assertEqual(descriptions[10],'Damage 69%');self.assertEqual(descriptions[13],'Damage 74%')
            self.assertEqual(set(notes),{10,11,14});self.assertEqual(row,raw)

    def test_knockback_does_not_replace_numeric_value_with_the_tooltip_progression(self):
        row={'id':3001003,'name':'Power Knockback','levels':[{'level':8,'damage':170}],
             'level_descriptions':['']*7+['MP -10; Damage 140%, Knockbacks up to 3 enemies by 170; Range +60']}
        levels,descriptions,notes=skill_ranks(row)
        self.assertEqual(levels[0]['damage'],170);self.assertIn('Damage 170%',descriptions[7]);self.assertIn(8,notes)

    def test_arrow_bomb_shows_the_verified_explosion_stage_for_every_rank(self):
        row={'id':3101004,'name':'Arrow Bomb','levels':[],'level_descriptions':[]}
        for rank in range(1,31):
            mp=14+(rank-1)//2;damage=130 if rank==30 else 68+2*rank;chance=60 if rank==30 else 29+rank
            row['levels'].append({'level':rank,'mpCon':mp,'damage':0,'mobCount':1})
            row['level_descriptions'].append(f'MP -{mp}; Stun chance {chance}% for 2 sec, damage {damage}%')
        raw=deepcopy(row);levels,descriptions,notes=skill_ranks(row)
        self.assertEqual(len(notes),30);self.assertEqual(levels[0]['damage'],70);self.assertEqual(levels[-1]['damage'],130)
        self.assertTrue(all(level['mobCount']==6 and level['time']==2 for level in levels));self.assertEqual(row,raw)

    def test_changed_or_unrelated_exports_do_not_receive_an_old_stage_override(self):
        cases=[{'id':3101004,'name':'Arrow Bomb','levels':[{'level':1,'mpCon':14,'damage':50,'mobCount':4}],
                'level_descriptions':['MP -14; Stun chance 30% for 2 sec, damage 70%']},
               {'id':3101004,'name':'Different skill','levels':[{'level':1,'mpCon':14,'damage':0,'mobCount':1}],
                'level_descriptions':['MP -14; Stun chance 30% for 2 sec, damage 70%']},
               {'id':3101004,'name':'Arrow Bomb','levels':[{'level':1,'mpCon':14,'damage':0,'mobCount':1}],
                'level_descriptions':['MP -14; Stun chance 30% for 2 sec, damage 75%']}]
        for row in cases:
            levels,descriptions,notes=skill_ranks(row)
            self.assertEqual(levels,row['levels']);self.assertEqual(notes,{})
