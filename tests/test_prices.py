from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from price_lens.domain import Catalog, Item, Quote, compare

NOW = 2_000_000_000
ORE = Item(4010000, "Test Ore")
STAR = Item(2070000, "Test Stars", per_set=True)


def quote(**kwargs):
    return replace(Quote(ORE.game_id, 100.0, NOW, NOW - 60, 8, "NiaMeowDB", "https://example.org", "24h"), **kwargs)


class ComparisonTests(unittest.TestCase):
    def test_bundle_is_normalized_and_fee_applies(self):
        result = compare(ORE, 10, 800, quote(), NOW)
        self.assertEqual(result.label, "Below reference")
        self.assertEqual(result.unit_price, 80)
        self.assertEqual(result.net_margin, 17)

    def test_stars_are_per_set_not_per_projectile(self):
        result = compare(STAR, 500, 80, quote(game_id=STAR.game_id, per_set=True), NOW)
        self.assertEqual(result.unit_price, 80)
        self.assertEqual(result.label, "Below reference")

    def test_exact_ttl_boundary_removes_rating(self):
        self.assertEqual(compare(ORE, 1, 70, quote(), NOW + 899).label, "Below reference")
        self.assertEqual(compare(ORE, 1, 70, quote(), NOW + 900).label, "Expired")

    def test_recent_fetch_cannot_resurrect_old_reports(self):
        result = compare(ORE, 1, 1, quote(observed_at=NOW - 86401), NOW)
        self.assertEqual(result.label, "Expired")

    def test_unknown_report_time_or_future_clock_is_not_fresh(self):
        for q in (quote(observed_at=None), quote(observed_at=NOW + 1000), quote(fetched_at=NOW + 1)):
            self.assertEqual(compare(ORE, 1, 1, q, NOW).label, "Expired")

    def test_low_volume_and_uncertain_sources_cannot_be_good_deals(self):
        for q in (quote(sample_count=4), quote(uncertain=True)):
            self.assertEqual(compare(ORE, 1, 1, q, NOW).label, "Thin data")

    def test_equipment_assumed_unscrolled_uses_normal_comparison(self):
        item = replace(ORE, equipment=True)
        self.assertEqual(compare(item, 1, 1, quote(), NOW).label, "Below reference")

    def test_wrong_market_identity_units_or_condition_rejected(self):
        for q in (quote(world="COT2"), quote(game_id=9), quote(per_set=True), quote(condition="scrolled")):
            self.assertEqual(compare(ORE, 1, 1, q, NOW).label, "Reference mismatch")

    def test_invalid_ocr_never_produces_a_rating(self):
        for quantity, price in ((0, 2), (None, 3), (1, None), (1, -1), (True, 1), (1, float("nan"))):
            self.assertEqual(compare(ORE, quantity, price, quote(), NOW).label, "Unreadable")


class IdentityTests(unittest.TestCase):
    def test_equipment_gender_suffix_requires_matching_catalog_gender(self):
        catalog=Catalog({'items':[{'id':1040040,'name':'Red Hwarang Shirt','category':'Equipment','gender':'male'},
                                  {'id':1,'name':'Test Shirt','category':'Equipment','gender':'male'},
                                  {'id':2,'name':'Test Shirt','category':'Equipment','gender':'female'},
                                  {'id':3,'name':'Work Gloves','category':'Equipment'},
                                  {'id':4,'name':'Test Scroll','gender':'male'}]})
        self.assertEqual(catalog.resolve('Red Hwarang Shirt (M)').game_id,1040040)
        self.assertEqual(catalog.resolve('Test Shirt (F)').game_id,2)
        self.assertIsNone(catalog.resolve('Red Hwarang Shirt (F)'))
        self.assertIsNone(catalog.resolve('Work Gloves (M)'))
        self.assertIsNone(catalog.resolve('Test Scroll (M)'))
    def test_observed_scroll_ocr_error_preserves_stat_and_tier(self):
        catalog=Catalog({'scrolls':[{'id':1,'name':'Overall Armor DEX Scroll: Greater','tier':'Greater'},
                                    {'id':2,'name':'Overall Armor DEX Scroll: Chaos','tier':'Chaos'},
                                    {'id':3,'name':'Overall Armor LUK Scroll: Greater','tier':'Greater'}]})
        for word in ('Soroll','Seroll','ScroIl','ScroII','Scr0ll'):
            self.assertEqual(catalog.resolve('Overall Armor DEX '+word+': Greater').game_id,1)
        self.assertEqual(catalog.resolve('Overall Arrnor DEX Scroll: Greater').game_id,1)
        self.assertEqual(catalog.resolve('Overall Armor LUK Soroll: Greater').game_id,3)
        self.assertIsNone(catalog.resolve('Overall Armor DEX Soroll'))
        self.assertIsNone(catalog.resolve('Overall Armor STR Soroll: Greater'))
    def test_clipped_name_tag_ring_requires_a_unique_full_item(self):
        catalog=Catalog({'items':[{'id':1112223,'name':'Ink-and-Wash Painting Name Tag Ring'},
                                 {'id':1112227,'name':'Ink-and-Wash Thought Bubble Ring'}]})
        for visible in ('Ink-and-Wash Painting N...','Ink-and-Wash Painting N…','Ink-and-Wash Painting N.',
                        'Ink and Wash Painting N…','Ink-and-Wash Painting Nametag Ring'):
            self.assertEqual(catalog.resolve(visible).game_id,1112223)
        self.assertIsNone(catalog.resolve('Ink-and-Wash...'))
        for visible in ('lnk-and-Wash Painting N...', 'Ink-and-Wash Paintinq N..,',
                        'Ink-and-Wash Painting N. . .'):
            self.assertEqual(catalog.resolve(visible).game_id,1112223)
        collision=Catalog({'items':[{'id':1,'name':'Example File Ring'},{'id':2,'name':'Example Fiie Ring'}]})
        self.assertIsNone(collision.resolve('Example Flle Rinq'))

    def test_small_font_y_v_confusion_needs_one_unique_catalog_name(self):
        catalog = Catalog({"items": [{"id": 1, "name": "Blue Hawkeye"}, {"id": 2, "name": "Horny Mushroom Cap"}]})
        self.assertEqual(catalog.resolve("Blue Hawkeve").game_id, 1)
        self.assertEqual(catalog.resolve("Hornv Mushroom Cap").game_id, 2)
        ambiguous = Catalog({"items": [{"id": 1, "name": "Example Navy"}, {"id": 2, "name": "Example Nayy"}]})
        self.assertIsNone(ambiguous.resolve("Example Navv"))

    def setUp(self):
        self.catalog = Catalog({"items": [{"id": 1, "name": "Test Hat", "category": "Equipment"},
                                            {"id": 2, "name": "Test Helmet", "category": "Equipment"}],
                                "scrolls": [{"id": 10 + n, "name": "Overall Armor LUK Scroll: " + tier, "tier": tier}
                                            for n, tier in enumerate(("Lesser", "Intermediate", "Greater", "Chaos"))]})

    def test_exact_name_and_cut_off_scroll_tier(self):
        self.assertEqual(self.catalog.resolve("Test Hat").game_id, 1)
        self.assertEqual(self.catalog.resolve("Overall Armor LUK Scroll:...", "greater").game_id, 12)

    def test_ambiguous_prefix_ocr_typo_or_missing_ellipsis_is_unknown(self):
        for name in ("Overall Armor LUK Scroll:...", "Test H...", "Test Hatx", "Test Ha"):
            self.assertIsNone(self.catalog.resolve(name))



if __name__ == "__main__":
    unittest.main()
