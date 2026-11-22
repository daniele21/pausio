"""Deterministic counter frames, ASS sanitization and frame-accurate boundaries."""
from __future__ import annotations

import unittest

from pausio.motion_metric import countup_frames, compose_counter_events
from pausio.scene_templates import _event, _safe


class MetricMotionTests(unittest.TestCase):
    def test_integer_animation_is_bounded_and_exact_at_the_end(self):
        frames = countup_frames("1.379", 380, 3200)
        self.assertGreaterEqual(len(frames), 6)
        self.assertLessEqual(len(frames), 12)
        self.assertEqual(frames[-1][2], "1.379")
        self.assertEqual(frames[0][0], 380)
        self.assertEqual(frames[-1][1], 3200)
        for left, right in zip(frames, frames[1:]):
            self.assertEqual(left[1], right[0])
            self.assertLess(left[0], left[1])
        values = [int(label.replace(".", "")) for _, _, label in frames]
        self.assertEqual(values, sorted(values))
        self.assertEqual(values[-1], 1379)

    def test_unparsable_values_are_kept_verbatim(self):
        for text in ("12,5%", "1.23", "01", "–", "ABC", "9999999999999"):
            with self.subTest(text=text):
                self.assertEqual(countup_frames(text, 0, 3200), [(0, 3200, text)])
        self.assertEqual(countup_frames("1379", 0, 600), [(0, 600, "1379")])

    def test_unsafe_copy_cannot_inject_ass(self):
        attacker = r"{\pos(0,0)}"
        events = compose_counter_events(attacker, 0, 3200, _event, _safe)
        self.assertNotIn(attacker, events)
        self.assertIn("｛＼pos(0,0)｝", events)
        self.assertIn("Dialogue: 5,", events)
        self.assertIn(r"\an5\pos(540,810)", events)

    def test_reject_invalid_window_and_geometry(self):
        for start, end in ((-1, 1200), (1000, 900), (True, 3000)):
            with self.assertRaises(ValueError):
                countup_frames("1379", start, end)
        for kwargs in ({"x": -1}, {"size": 500}, {"color": "red"},
                       {"color": "#ff0000"}, {"y": True}):
            with self.assertRaises(ValueError):
                compose_counter_events("1379", 0, 2800, _event, _safe, **kwargs)

    def test_one_label_even_for_zero_and_very_small_integer(self):
        for number in ("0", "1", "2"):
            frames = countup_frames(number, 0, 2800)
            self.assertEqual(frames[-1][2], number)
            self.assertTrue(all(a < b for a, b, _ in frames))


if __name__ == "__main__":
    unittest.main()
