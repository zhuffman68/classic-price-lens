"""Wallet OCR confirmation, interruptions and net accounting, without a game."""
import unittest
from price_lens.mesos import MesoTracker


class MesoTrackingTests(unittest.TestCase):
    def setUp(self):
        self.tracker=MesoTracker();self.tracker.reset(0);self.at=0

    def sample(self,value):
        self.at+=1;self.tracker.tick(self.at)
        return self.tracker.ingest({'mesos':value} if value is not None else None,self.at)

    def balance(self,value):self.sample(value);self.assertTrue(self.sample(value))

    def test_confirmed_zero_wallet_and_positive_and_negative_changes(self):
        self.balance(0);self.balance(70000)
        self.assertEqual(self.tracker.gain,70000)
        self.balance(68000);self.assertEqual(self.tracker.gain,68000)
        self.assertTrue(self.tracker.fresh(self.at))

    def test_hidden_wallet_is_stale_and_reconciles_when_reopened(self):
        self.balance(70000);self.sample(None)
        self.assertFalse(self.tracker.fresh(self.at));self.assertEqual(self.tracker.current,70000)
        self.balance(71200);self.assertEqual(self.tracker.gain,1200)

    def test_single_bad_digit_or_invalid_value_cannot_change_totals(self):
        self.balance(70000)
        for value in (7000,None,-1,True,1.5,2_147_483_648,'70000'):
            self.sample(value);self.assertEqual(self.tracker.gain,0)
        self.balance(70000);self.assertEqual(self.tracker.gain,0)

    def test_pause_discards_hidden_change_and_does_not_advance_timer(self):
        self.balance(70000);self.tracker.pause(True);before=self.tracker.seconds
        self.sample(50000);self.sample(50000)
        self.assertEqual(self.tracker.seconds,before)
        self.tracker.pause(False);self.balance(50000);self.balance(50100)
        self.assertEqual(self.tracker.gain,100)

    def test_capture_interrupt_does_not_merge_an_unseen_transfer(self):
        self.balance(70000);self.tracker.interrupt();self.balance(4000);self.balance(4100)
        self.assertEqual(self.tracker.gain,100)

    def test_rates_require_a_confirmed_baseline_and_fresh_counter(self):
        self.balance(70000)
        for _ in range(10):self.sample(70000)
        self.balance(71200)
        self.assertGreater(self.tracker.rate(self.at),0)
        self.sample(None);self.assertIsNone(self.tracker.rate(self.at))

    def test_history_segment_preserves_balance_and_does_not_double_count(self):
        self.balance(70000);self.balance(71200)
        first=self.tracker.checkpoint();self.assertEqual(first['mesos'],1200)
        self.assertEqual(first['wallet_start'],70000);self.assertEqual(first['wallet_end'],71200)
        self.balance(71200);self.balance(71500)
        self.assertEqual(self.tracker.checkpoint()['mesos'],300)
        self.assertEqual(self.tracker.gain,1500)
