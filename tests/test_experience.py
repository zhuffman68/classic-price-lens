"""EXP accounting through gains, losses, level-ups, interruptions and persistence."""
import csv
from pathlib import Path
import tempfile
import unittest

from price_lens.experience import ExperienceTracker, Reading, SessionHistory


def payload(exp=2000, total=10_000, level=27, name="TestWarrior"):
    return {"level":level,"character":name,"job":"Warrior",
            "bar":{"exp":exp,"percentHundredths":round(exp/total*10_000)}}


class ExperienceTests(unittest.TestCase):
    def tracker(self, exp=2000, total=10_000):
        tracker = ExperienceTracker()
        self.assertTrue(tracker.ingest(payload(exp,total), 0))
        self.assertTrue(tracker.start("Ant Tunnel", "Solo", started=1_000))
        return tracker

    def test_window_reports_observation_and_normalized_pace_separately(self):
        tracker = self.tracker()
        for second in range(1,61):
            self.assertTrue(tracker.ingest(payload(2000+10*second), second))
        result = tracker.window(300)
        self.assertEqual(result["seconds"],60)
        self.assertAlmostEqual(result["progress"],6)
        self.assertAlmostEqual(result["rate"]*300,30)
        self.assertAlmostEqual(result["exp_hour"],36_000)
        self.assertAlmostEqual(tracker.run.exp,600)
        self.assertAlmostEqual(result["eta"],740)

    def test_standing_still_counts_and_small_samples_have_no_forecast(self):
        tracker = self.tracker()
        for second in range(1,61):
            tracker.ingest(payload(2000),second)
            if second < 30:
                self.assertIsNone(tracker.window(300)["rate"])
        result = tracker.window(60)
        self.assertEqual(result["seconds"],60)
        self.assertEqual(result["rate"],0)
        self.assertIsNone(result["eta"])

    def test_rolling_window_excludes_earlier_faster_training(self):
        tracker = self.tracker()
        for second in range(1,121):
            tracker.ingest(payload(2000+min(second,60)*10),second)
        self.assertAlmostEqual(tracker.run.progress,6)
        self.assertEqual(tracker.window(60)["progress"],0)

    def test_level_up_carries_progress_and_marks_inferred_raw_total(self):
        tracker = self.tracker(exp=9900)
        self.assertFalse(tracker.ingest(payload(80,12_000,28),1))
        self.assertTrue(tracker.ingest(payload(90,12_000,28),2))
        self.assertAlmostEqual(tracker.run.progress,1.75)
        self.assertAlmostEqual(tracker.run.exp,190,delta=1)
        self.assertEqual(tracker.run.end_level,28)
        self.assertGreaterEqual(tracker.run.exp,0)

    def test_exp_loss_is_confirmed_and_deducted(self):
        tracker = self.tracker(exp=5000)
        self.assertFalse(tracker.ingest(payload(4700),1))
        self.assertTrue(tracker.ingest(payload(4710),2))
        self.assertAlmostEqual(tracker.run.progress,-2.9)
        self.assertAlmostEqual(tracker.run.lost,2.9)
        self.assertEqual(tracker.run.exp,-290)
        self.assertIsNone(tracker.window(300)["eta"])

    def test_single_bad_digit_or_level_does_not_change_totals(self):
        tracker = self.tracker()
        bad = payload()
        bad["bar"]["exp"] = 200
        self.assertFalse(tracker.ingest(bad,1))
        self.assertFalse(tracker.ingest(payload(200,12_000,28),2))
        self.assertTrue(tracker.ingest(payload(2030),3))
        self.assertEqual(tracker.run.exp,30)
        self.assertEqual(tracker.run.end_level,27)

    def test_character_switch_saves_previous_run_without_merging(self):
        tracker = self.tracker()
        tracker.ingest(payload(2010),1)
        tracker.ingest(payload(500,12_000,28,"SomeoneElse"),2)
        tracker.ingest(payload(510,12_000,28,"SomeoneElse"),3)
        self.assertIsNone(tracker.run)
        self.assertEqual(len(tracker.completed),1)
        self.assertEqual(tracker.completed[0].exp,10)
        self.assertEqual(tracker.completed[0].reason,"Character changed")

    def test_capture_gap_excludes_unseen_gain_and_elapsed_time(self):
        tracker = self.tracker()
        tracker.ingest(payload(2010),1)
        tracker.ingest(payload(2500),15)
        tracker.ingest(payload(2510),16)
        self.assertEqual(tracker.run.exp,20)
        self.assertEqual(tracker.run.seconds,2)
        self.assertEqual(tracker.run.gaps,1)

    def test_pause_and_resume_rebaseline_without_counting_pause_gain(self):
        tracker = self.tracker()
        tracker.ingest(payload(2010),1)
        tracker.pause()
        tracker.ingest(payload(2500),2)
        tracker.pause(False)
        tracker.ingest(payload(2600),3)
        tracker.ingest(payload(2610),4)
        self.assertEqual(tracker.run.exp,20)
        self.assertEqual(tracker.run.seconds,2)

    def test_explicit_context_loss_excludes_short_gap(self):
        tracker = self.tracker()
        tracker.ingest(payload(2010),1)
        tracker.interrupt()
        tracker.ingest(payload(2500),2)
        tracker.ingest(payload(2510),3)
        self.assertEqual(tracker.run.exp,20)
        self.assertEqual(tracker.run.gaps,1)

    def test_map_change_needs_two_reads_and_saves_the_test(self):
        tracker = self.tracker()
        tracker.ingest(payload(2010),1)
        for at in (0,5):
            tracker.observe_map({"mapRead":True,"map":{"street":"Dungeon","map":"Ant Tunnel"}},at)
        tracker.observe_map({"mapRead":True,"map":{"street":"Victoria Road","map":"Henesys"}},10)
        self.assertIsNotNone(tracker.run)
        tracker.observe_map({"mapRead":True,"map":{"street":"Victoria Road","map":"Henesys"}},15)
        self.assertIsNone(tracker.run)
        self.assertEqual(tracker.completed[0].reason,"Map changed")

    def test_repeated_timestamp_and_invalid_percent_are_ignored(self):
        tracker = self.tracker()
        self.assertFalse(tracker.ingest(payload(2500),0))
        bad = payload()
        bad["bar"]["percentHundredths"] = 10_000
        self.assertFalse(tracker.ingest(bad,1))
        self.assertIsNone(Reading.parse({"level":True,"bar":{}},1))
        self.assertEqual(tracker.run.exp,0)

    def test_rate_history_is_bounded_during_long_sessions(self):
        tracker = self.tracker(exp=100_000,total=1_000_000)
        for second in range(1,7300):
            tracker.ingest(payload(100_000+second,1_000_000),second)
        self.assertLessEqual(len(tracker.events),3602)
        self.assertAlmostEqual(tracker.window(300)["seconds"],300)

    def test_history_survives_reopen_and_exports_literal_notes(self):
        tracker = self.tracker()
        tracker.run.notes = '=HYPERLINK("bad")'
        tracker.ingest(payload(2010),1)
        run = tracker.finish()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"sessions.sqlite"
            history = SessionHistory(path)
            history.save(run)
            history.save(run)
            reopened = SessionHistory(path)
            self.assertEqual(len(reopened.rows()),1)
            self.assertEqual(reopened.rows()[0]["exp"],10)
            output = Path(directory)/"history.csv"
            reopened.export(output)
            with output.open(encoding="utf-8-sig",newline="") as stream:
                row = next(csv.DictReader(stream))
            self.assertTrue(row["notes"].startswith("'="))


if __name__ == "__main__":
    unittest.main()
