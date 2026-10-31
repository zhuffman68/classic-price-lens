"""Anonymized real scroll/fade sequence, including previously missed pickups."""
import json
from pathlib import Path
import unittest

from price_lens.mesos import PickupTracker


class PickupBurstReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trace=json.loads((Path(__file__).parent/'fixtures/pickup-burst.json').read_text())

    def test_complete_annotated_burst_includes_faded_and_scrolled_arrivals_once(self):
        tracker=PickupTracker()
        tracker.reset(0)
        for frame in self.trace['frames']:
            at=frame['atMs']/1000
            tracker.tick(at)
            tracker.ingest(frame['pickups'],at)
        self.assertEqual(tracker.gain,sum(self.trace['arrivals']))
        self.assertEqual(tracker.gain,self.trace['expected_gain'])
        self.assertEqual(tracker.last_pickup,20)

    def test_repeated_and_out_of_order_delivery_cannot_recount_the_burst(self):
        tracker=PickupTracker()
        tracker.reset(0)
        previous=None
        for frame in self.trace['frames']:
            at=frame['atMs']/1000
            tracker.tick(at)
            tracker.ingest(frame['pickups'],at)
            tracker.ingest(frame['pickups'],at)
            if previous is not None:
                tracker.ingest(previous['pickups'],previous['atMs']/1000)
            tracker.ingest(frame['pickups'],at+.001)
            previous=frame
        self.assertEqual(tracker.gain,self.trace['expected_gain'])

    def test_seeded_initial_pickup_is_never_added_to_the_new_arrivals(self):
        tracker=PickupTracker()
        first=self.trace['frames'][0]
        for index in range(10):
            tracker.ingest(first['pickups'],index*.1)
        self.assertEqual(tracker.gain,0)
        self.assertIsNone(tracker.last_pickup)


if __name__=='__main__':
    unittest.main()
