"""Structured pickup arrivals with fixed-bottom 14px log geometry; no screenshots."""
from copy import deepcopy
import math
import unittest

from price_lens.mesos import PickupTracker


def line(amount, y=156, *, visual=None):
    return dict(key=f'mesos:{amount}', mesos=amount, kind='meso',
                rect=dict(x=350, y=y, width=200, height=10),
                visualKey=visual or f'meso-pixels-{amount}')


def anchor(label, y=156, *, visual=None):
    return dict(key=f'item:{label}', mesos=None, kind='item',
                rect=dict(x=350, y=y, width=200, height=10),
                visualKey=visual or f'anchor-pixels-{label}')


def unknown(visual, y=156):
    return dict(key=f'unknown:{visual}', mesos=None, kind='unknown',
                rect=dict(x=350, y=y, width=200, height=10), visualKey=visual)


def packet(*rows, partial=False):
    readable = any(row.get('kind') != 'unknown' for row in rows)
    return dict(valid=True, state='readable' if readable else 'unreadable' if partial else 'empty',
                partial=partial, lines=list(rows))


class PickupArrivalTests(unittest.TestCase):
    def setUp(self):
        self.tracker = PickupTracker()
        self.tracker.reset(0)

    def sample(self, at, *rows, partial=False):
        self.tracker.tick(at)
        return self.tracker.ingest(packet(*rows, partial=partial), at)

    def test_same_amount_repeats_are_distinct_arrivals_when_a_shared_anchor_proves_scroll(self):
        self.sample(.2, anchor('baseline'))
        self.sample(.4, anchor('baseline', 142), line(29))
        self.assertEqual(self.tracker.gain, 0)
        self.sample(.6, anchor('baseline', 128), line(29, 142), line(29))
        self.sample(.8, anchor('baseline', 114), line(29, 128), line(29, 142), line(29))
        self.sample(1, anchor('baseline', 114), line(29, 128), line(29, 142), line(29))
        self.assertEqual(self.tracker.gain, 87)
        self.assertEqual(self.tracker.last_pickup, 29)

    def test_partial_bottom_replacement_requires_two_literal_observations(self):
        self.sample(.2, line(10))  # Already present when tracking began.
        self.sample(.4, line(29), partial=True)
        self.assertEqual(self.tracker.gain, 0)
        self.sample(.6, line(29), partial=True)
        self.assertEqual(self.tracker.gain, 29)
        self.assertEqual(self.tracker.last_pickup, 29)

    def test_partial_birth_proof_survives_until_a_later_clear_confirmation(self):
        self.sample(.2, line(10))
        self.sample(.4, line(29), partial=True)
        self.sample(1.6, unknown('meso-pixels-29'), partial=True)
        self.assertEqual(self.tracker.gain, 0)
        self.sample(1.8, line(29))
        self.assertEqual(self.tracker.gain, 29)

    def test_unrecognized_bottom_does_not_authorize_a_whole_partial_replacement(self):
        self.sample(.2, line(10))
        self.sample(.4, line(29, 142), unknown('unclassified-bottom'), partial=True)
        self.sample(.6, line(29, 142), unknown('unclassified-bottom'), partial=True)
        self.assertEqual(self.tracker.gain, 0)

    def test_visual_only_match_retains_but_never_confirms_a_new_currency_amount(self):
        self.sample(.2)
        self.sample(.4, line(29), partial=True)
        self.sample(.6, unknown('meso-pixels-29'), partial=True)
        self.assertEqual(self.tracker.gain, 0)
        self.sample(.8, line(29), partial=True)
        self.assertEqual(self.tracker.gain, 29)

    def test_identical_visual_anchor_does_not_make_a_gap_when_ocr_spelling_changes(self):
        self.sample(.2, anchor('first-read', visual='same-receipt-pixels'))
        self.sample(.4, anchor('second-read', visual='same-receipt-pixels'), partial=True)
        self.sample(.6, anchor('third-read', visual='same-receipt-pixels'), partial=True)
        self.assertEqual(self.tracker.gaps, 0)
        self.assertEqual(self.tracker.gain, 0)

    def test_partial_duplicate_ties_cannot_recount_a_seeded_recovered_prefix(self):
        # Every appended event shifts older rows upward by exactly 14px.
        # Only 2+1+2+3+3=11 arrived after Start. The old 1000 can never count.
        self.sample(.2, line(1000))
        self.sample(.4, line(2), partial=True)
        self.sample(.6, line(2, 128), line(1, 142), line(2), partial=True)
        self.sample(.8, line(1000, 114), line(2, 128), line(1, 142), line(2))
        self.sample(1, line(1000, 86), line(2, 100), line(1, 114), line(2, 128), line(3, 142), line(3))
        self.sample(1.2, line(1000, 86), line(2, 100), line(1, 114), line(2, 128), line(3, 142), line(3))
        # The first 2 and both trailing 3s have independent birth/confirmation
        # proof. Ambiguous middle duplicates may conservatively be omitted.
        self.assertGreaterEqual(self.tracker.gain, 8)
        self.assertLessEqual(self.tracker.gain, 11)

    def test_a_single_view_burst_is_never_counted_after_fading_to_unknown(self):
        self.sample(.2, anchor('first-baseline'))
        self.sample(.4, line(21, 100), line(30, 128), line(20, 142), anchor('new-bottom'), partial=True)
        self.sample(.6, unknown('meso-pixels-21', 100), unknown('meso-pixels-30', 128),
                    unknown('meso-pixels-20', 142), anchor('new-bottom'), partial=True)
        self.sample(.8, anchor('new-bottom'), partial=True)
        self.assertEqual(self.tracker.gain, 0)

    def test_short_ocr_dropout_is_not_an_empty_log_and_keeps_pending_arrivals(self):
        self.sample(.2, anchor('baseline'))
        self.sample(.4, anchor('baseline', 142), line(29))
        self.sample(.6, partial=True)
        self.sample(.8, anchor('baseline', 142), line(29), partial=True)
        self.assertEqual(self.tracker.gain, 29)
        self.assertEqual(self.tracker.gaps, 0)

    def test_lost_coverage_seeds_visible_messages_instead_of_confirming_old_pending_rows(self):
        self.sample(.2, anchor('baseline'))
        self.sample(.4, anchor('baseline', 142), line(29))
        self.sample(.6, partial=True)
        self.sample(2, anchor('baseline', 142), line(29), partial=True)
        self.sample(2.2, anchor('baseline', 142), line(29))
        self.assertEqual(self.tracker.gain, 0)
        self.assertEqual(self.tracker.gaps, 1)

    def test_covering_window_reseeds_messages_and_rejects_late_pre_cover_results(self):
        self.sample(.2)
        self.sample(.4, line(29))
        self.sample(.6, line(29))
        self.tracker.ingest(dict(valid=False, covered=True, lines=[]), .8)
        self.assertIsNone(self.tracker.lines)
        self.sample(.7, line(1000))
        self.assertIsNone(self.tracker.lines)
        self.sample(1, line(29, 142), line(1000))
        self.sample(1.2, line(29, 142), line(1000))
        self.sample(1.4, line(29, 128), line(1000, 142), line(20))
        self.sample(1.6, line(29, 128), line(1000, 142), line(20))
        self.assertEqual(self.tracker.gain, 49)
        self.assertEqual(self.tracker.gaps, 1)

    def test_duplicate_and_out_of_order_frames_cannot_confirm_a_new_amount(self):
        self.sample(.2)
        self.sample(.6, line(29))
        self.sample(.6, line(29))
        self.sample(.4, line(29))
        self.assertEqual(self.tracker.gain, 0)
        self.sample(.8, line(29))
        self.assertEqual(self.tracker.gain, 29)

    def test_nonfinite_timestamps_and_malformed_geometry_are_rejected(self):
        self.sample(.2)
        for at in (math.nan, math.inf, -math.inf):
            self.tracker.ingest(packet(line(29)), at)
        for fields in (dict(y=-1), dict(x=700, width=200), dict(height=0), dict(width=True)):
            row = line(29)
            row['rect'].update(fields)
            self.tracker.ingest(packet(row), .4)
        row = line(29)
        row['key'] = 'mesos:29000'
        self.tracker.ingest(packet(row), .4)
        self.assertEqual(self.tracker.gain, 0)
        self.assertEqual(self.tracker.last_observation, .2)

    def test_repeated_partial_unknowns_cannot_grow_the_pending_ledger_without_bound(self):
        self.sample(.2, anchor('baseline'))
        for index in range(400):
            self.sample(.4+index*.1, *(unknown(f'frame-{index}-row-{j}', 16+j*14) for j in range(20)), partial=True)
            self.assertLessEqual(len(self.tracker.instances), self.tracker.MAX_TRACKS)
        self.assertEqual(self.tracker.gain, 0)

    def test_long_arrival_stream_keeps_recent_buckets_bounded_and_session_gain_exact(self):
        self.sample(.2)
        visible = []
        expected = 0
        for index in range(1800):
            amount = index+1
            expected += amount
            visible = [line(row['mesos'], row['rect']['y']-14) for row in visible
                       if row['rect']['y']-14 >= 86] + [line(amount)]
            self.sample(.4+index*.2, *deepcopy(visible))
            self.assertLessEqual(len(self.tracker.instances), self.tracker.MAX_TRACKS)
            self.assertLessEqual(len(self.tracker.recent), 301)
        self.sample(.4+1800*.2, *visible)
        self.assertEqual(self.tracker.gain, expected)
        self.assertEqual(self.tracker.last_pickup, 1800)
        self.assertLessEqual(self.tracker.recent_gain, self.tracker.gain)
