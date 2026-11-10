import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pausio.domain import EditPlan, Interval


class TestEditPlan(unittest.TestCase):
    def test_round_trip(self):
        plan = EditPlan("clip.mp4", 8000, (Interval(0, 1200), Interval(2500, 8000)), True)
        self.assertEqual(EditPlan.from_dict(plan.as_dict()), plan)
        self.assertEqual(plan.output_duration_ms, 6700)

    def test_rejects_inverted_or_overlapping_intervals(self):
        with self.assertRaises(ValueError):
            Interval(100, 99)
        with self.assertRaises(ValueError):
            EditPlan("clip.mp4", 3000, (Interval(0, 1800), Interval(1700, 3000)), True)
        with self.assertRaises(ValueError):
            EditPlan("clip.mp4", 1000, (Interval(0, 1100),), True)

    def test_rejects_invalid_schema_and_unsafe_types(self):
        data = EditPlan("clip.mp4", 1000, (Interval(0, 1000),), False).as_dict()
        data["schema_version"] = 10
        with self.assertRaises(ValueError):
            EditPlan.from_dict(data)
        with self.assertRaises(ValueError):
            Interval(True, 100)
        with self.assertRaises(ValueError):
            EditPlan.from_dict({"segments": None})

    def test_resolves_media_path_relative_to_plan(self):
        with TemporaryDirectory() as directory:
            plan_file = Path(directory) / "project" / "edit.json"
            plan = EditPlan("../raw/video.mp4", 2000, (Interval(0, 2000),), False)
            self.assertEqual(plan.resolved_source(plan_file), (Path(directory) / "raw/video.mp4").resolve())


if __name__ == "__main__":
    unittest.main()
