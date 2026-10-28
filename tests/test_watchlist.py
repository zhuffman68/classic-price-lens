"""Watch exact items and highlight visible encounters without fetching prices."""
import json
import unittest

from price_lens.domain import Item
from price_lens.watchlist import Watchlist, WatchEncounters


class Settings:
    def __init__(self):self.values = {}
    def value(self, key, default):return self.values.get(key, default)
    def setValue(self, key, value):self.values[key] = value


class WatchlistTests(unittest.TestCase):
    def test_exact_variants_persist_and_can_be_removed_independently(self):
        settings = Settings()
        watches = Watchlist(settings)
        normal = Item(2040001, "Hat Accuracy Scroll", tier="Normal")
        greater = Item(2040002, "Hat Accuracy Scroll", tier="Greater")
        watches.toggle(normal);watches.toggle(greater)
        restored = Watchlist(settings)
        self.assertEqual(restored.ids, {normal.game_id, greater.game_id})
        self.assertIn("Greater", restored.entries[greater.game_id])
        restored.remove(normal.game_id)
        self.assertEqual(Watchlist(settings).ids, {greater.game_id})

    def test_corrupt_preferences_do_not_create_guessed_item_identities(self):
        settings = Settings()
        settings.values['watched-items'] = '{not valid'
        self.assertFalse(Watchlist(settings).ids)
        settings.values['watched-items'] = json.dumps([
            {'id':True,'name':'Wrong'}, {'id':-1,'name':'Wrong'}, {'id':'12','name':'Wrong'},
            {'id':12,'name':'Exact item'}, {'name':'No identity'}])
        self.assertEqual(Watchlist(settings).ids, {12})

    @staticmethod
    def row(identity=12, key='slot:0', **changes):
        return dict(kind='shop', item_id=identity, key=key, name='Item', text='FM checking…', **changes)

    def test_highlight_does_not_need_a_price_and_never_matches_another_variant(self):
        encounter = WatchEncounters()
        rows = [self.row(), self.row(13,'slot:1'), {'kind':'experience','item_id':12,'key':'exp'}]
        encounter.apply(rows, {12}, now=0)
        self.assertTrue(rows[0]['watched'])
        self.assertGreater(rows[0]['watch_event'],0)
        self.assertFalse(rows[1]['watched'])
        self.assertFalse(rows[2]['watched'])

    def test_same_visible_item_stays_steady_across_long_render_gaps_and_quote_updates(self):
        encounter = WatchEncounters()
        first = self.row();encounter.apply([first], {12}, now=0)
        for now in (1,5,60,600):
            row = self.row(obscured=True, x=40+now)
            row['text'] = f'FM {now:,} mesos'
            encounter.apply([row], {12}, now=now)
            self.assertEqual(row['watch_event'],first['watch_event'])

    def test_short_reading_miss_does_not_rearm_but_confirmed_absence_does(self):
        encounter = WatchEncounters()
        row=self.row();encounter.apply([row], {12}, now=0);first=row['watch_event']
        encounter.apply([], {12}, now=1)
        row=self.row();encounter.apply([row], {12}, now=1.2)
        self.assertEqual(row['watch_event'],first)
        encounter.apply([], {12}, now=2)
        row=self.row();encounter.apply([row], {12}, now=4)
        self.assertNotEqual(row['watch_event'],first)

    def test_new_shop_page_rearms_without_rearming_an_inventory_tooltip(self):
        encounter = WatchEncounters()
        shop=self.row();hover={**self.row(key='hover'), 'kind':'item'}
        encounter.apply([shop,hover], {12}, page=1, now=0)
        next_shop=self.row();next_hover={**self.row(key='hover'), 'kind':'item'}
        encounter.apply([next_shop,next_hover], {12}, page=2, now=.1)
        self.assertNotEqual(next_shop['watch_event'],shop['watch_event'])
        self.assertEqual(next_hover['watch_event'],hover['watch_event'])

    def test_removing_then_readding_an_item_creates_a_new_encounter(self):
        encounter = WatchEncounters()
        row=self.row();encounter.apply([row], {12}, now=0);first=row['watch_event']
        encounter.apply([self.row()], set(), now=.1)
        row=self.row();encounter.apply([row], {12}, now=.2)
        self.assertNotEqual(row['watch_event'],first)


if __name__ == '__main__':unittest.main()
