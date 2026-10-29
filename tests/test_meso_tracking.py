"""Pickup arrivals, repeated amounts and conservative coverage, without a game."""
import unittest
from price_lens.mesos import PickupTracker


def log(*values):
    return {'valid':True,'lines':[{'key':f'mesos:{n}','mesos':n} for n in values]}


class MesoTrackingTests(unittest.TestCase):
    def setUp(self):
        self.tracker=PickupTracker();self.tracker.reset(0);self.at=0

    def sample(self,*values,step=.2):
        self.at+=step;self.tracker.tick(self.at)
        return self.tracker.ingest(log(*values),self.at)

    def confirm(self,*values):self.sample(*values);self.assertTrue(self.sample(*values))

    def test_existing_lines_are_seeded_and_new_lines_are_counted_once(self):
        self.sample(29);self.confirm(29,50)
        for _ in range(6):self.sample(29,50)
        self.assertEqual(self.tracker.gain,50)

    def test_same_amount_in_distinct_arrivals_is_not_deduplicated_by_value(self):
        self.sample();self.confirm(29);self.confirm(29,29);self.confirm(29,29,29)
        self.assertEqual(self.tracker.gain,87)
        self.confirm();self.confirm(29)
        self.assertEqual(self.tracker.gain,116)

    def test_arrivals_confirm_even_while_other_pickups_keep_being_appended(self):
        self.sample();self.sample(10);self.sample(10,20);self.sample(10,20,30);self.sample(20,30,40);self.sample(30,40)
        self.assertEqual(self.tracker.gain,100)

    def test_scrolling_and_fading_do_not_recount_old_lines(self):
        self.sample();self.confirm(29,50,10);self.confirm(50,10);self.confirm(10,100)
        self.assertEqual(self.tracker.gain,189)
        self.confirm(100);self.assertEqual(self.tracker.gain,189)

    def test_single_bad_read_cannot_inflate_a_pickup(self):
        self.sample();self.sample(29000);self.confirm(29)
        self.assertEqual(self.tracker.gain,29)
        for amount in (-1,True,1.5,2147483648,'29'):
            self.at+=.2;self.assertFalse(self.tracker.ingest({'valid':True,'lines':[{'key':'bad','mesos':amount}]},self.at))
        self.assertEqual(self.tracker.gain,29)

    def test_pause_excludes_old_messages_and_holds_clock(self):
        self.sample();self.confirm(29);self.tracker.pause(True);seconds=self.tracker.seconds
        self.sample(1000);self.assertEqual(self.tracker.seconds,seconds)
        self.tracker.pause(False);self.sample(1000);self.confirm(1000,20)
        self.assertEqual(self.tracker.gain,49)

    def test_capture_gap_seeds_old_lines_without_inventing_income(self):
        self.sample();self.confirm(29);self.sample(1000,step=2)
        self.assertEqual(self.tracker.gaps,1);self.confirm(1000,20)
        self.assertEqual(self.tracker.gain,49)

    def test_ambiguous_replacement_has_no_shared_anchor_and_is_not_guessed(self):
        self.sample(10);self.confirm(1000)
        self.assertEqual(self.tracker.gain,0)
        self.confirm(1000,20);self.assertEqual(self.tracker.gain,20)

    def test_rate_and_history_keep_gross_pickups_and_do_not_reset_visible_log(self):
        self.sample();self.confirm(29)
        for _ in range(55):self.sample(29)
        self.assertGreater(self.tracker.rate(self.at),0)
        first=self.tracker.checkpoint();self.assertEqual(first['mesos'],29)
        self.assertEqual(first['meso_basis'],'pickups');self.assertNotIn('wallet_end',first)
        self.confirm(29,50);self.assertEqual(self.tracker.checkpoint()['mesos'],50)
        self.assertEqual(self.tracker.gain,79)

    def test_recent_pace_excludes_old_pickups_without_reducing_session_gain(self):
        self.sample();self.confirm(600)
        self.assertEqual(self.tracker.last_pickup,600)
        for _ in range(310):self.sample(600,step=1)
        self.assertEqual(self.tracker.gain,600);self.assertEqual(self.tracker.rate(self.at),0)
        self.confirm(600,300)
        self.assertAlmostEqual(self.tracker.rate(self.at),60)
        self.assertEqual(self.tracker.gain,900);self.assertEqual(self.tracker.last_pickup,300)

    def test_paused_time_does_not_expire_the_recent_pace_or_last_pickup(self):
        self.sample();self.confirm(600)
        for _ in range(20):self.sample(600,step=1)
        before=self.tracker.rate(self.at);self.tracker.pause(True)
        for _ in range(600):self.sample(600,step=1)
        self.assertEqual(self.tracker.rate(self.at),before);self.assertEqual(self.tracker.last_pickup,600)
        self.tracker.pause(False);self.sample(600)
        self.assertGreater(self.tracker.rate(self.at),0)

    def test_rate_history_is_bounded_and_checkpoints_do_not_reset_it(self):
        self.sample()
        for _ in range(700):
            self.confirm();self.confirm(10)
        before=self.tracker.rate(self.at);last=self.tracker.last_pickup
        self.tracker.checkpoint()
        self.assertEqual(self.tracker.rate(self.at),before);self.assertEqual(self.tracker.last_pickup,last)
        self.assertLessEqual(len(self.tracker.recent),301)

    def test_rate_has_only_a_ten_second_minimum_and_seeded_lines_are_not_last_pickup(self):
        self.sample(900);self.assertIsNone(self.tracker.last_pickup)
        for _ in range(9):self.sample(900,step=1)
        self.assertIsNone(self.tracker.rate(self.at))
        self.sample(900,step=1);self.assertEqual(self.tracker.rate(self.at),0)
