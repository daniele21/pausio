import unittest

from pausio.domain import Interval
from pausio.planner import propose_segments


class TestPlanner(unittest.TestCase):
    def test_preserves_short_pause(self):
        self.assertEqual(propose_segments(5000, [Interval(2000, 2500)]), (Interval(0, 5000),))

    def test_cuts_only_centre_of_long_internal_silence(self):
        self.assertEqual(
            propose_segments(6000, [Interval(2000, 4000)]),
            (Interval(0, 2200), Interval(3750, 6000)),
        )

    def test_trims_leading_and_trailing_silence(self):
        self.assertEqual(
            propose_segments(7000, [Interval(0, 1800), Interval(5600, 7000)]),
            (Interval(1550, 5800),),
        )

    def test_merges_overlapping_silence(self):
        self.assertEqual(
            propose_segments(6000, [Interval(1600, 2800), Interval(2700, 4200)]),
            (Interval(0, 1800), Interval(3950, 6000)),
        )

    def test_does_not_drop_short_intervening_speech(self):
        retained = propose_segments(7000, [Interval(1000, 2300), Interval(2500, 4400)])
        # The second cut must not silently discard 200 ms of speech.
        self.assertTrue(any(seg.start_ms <= 2300 and seg.end_ms >= 2500 for seg in retained))

    def test_fully_silent_falls_back_to_original(self):
        self.assertEqual(propose_segments(3000, [Interval(0, 3000)]), (Interval(0, 3000),))

    def test_no_silences_returns_original(self):
        self.assertEqual(propose_segments(4500, []), (Interval(0, 4500),))


if __name__ == "__main__":
    unittest.main()
