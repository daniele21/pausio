"""Independent variant snapshots: deterministic replay, SHA checks and strict bundle import."""
from __future__ import annotations

import copy
import unittest

from pausio.project_commands import ProjectTape
from pausio.variant_projects import STYLE_IDS, VariantWorkspace


def source():
    tape = ProjectTape({
        "filename": "phone.mp4",
        "sha256": "a" * 64,
        "duration_ms": 10000,
        "has_audio": True,
    }).append("timeline.keep_all", {})
    return tape


class VariantWorkspaceTests(unittest.TestCase):
    def test_three_independent_tapes_and_undo(self):
        baseline = source()
        bundle = VariantWorkspace.fork(baseline)
        self.assertEqual(tuple(bundle.tapes), STYLE_IDS)
        self.assertEqual(bundle.tapes["authority"].as_dict(), baseline.as_dict())
        changed = bundle.tapes["social_impact"].append(
            "timeline.approve", {}
        )
        impact = bundle.switch("social_impact").with_active_tape(changed)
        self.assertTrue(impact.tapes["social_impact"].view.approved)
        self.assertFalse(impact.tapes["authority"].view.approved)
        self.assertFalse(impact.tapes["visual_explainer"].view.approved)
        self.assertEqual(baseline.as_dict(), bundle.tapes["authority"].as_dict())
        undone = impact.with_active_tape(changed.undo())
        self.assertFalse(undone.tapes["social_impact"].view.approved)
        self.assertTrue(undone.tapes["social_impact"].can_redo)

    def test_portable_bundle_roundtrip_and_source_binding(self):
        bundle = VariantWorkspace.fork(source())
        raw = bundle.as_dict()
        before = copy.deepcopy(raw)
        restored = VariantWorkspace.from_dict(
            raw, source_tape=bundle.tapes[bundle.active]
        )
        self.assertEqual(restored.as_dict(), raw)
        self.assertEqual(raw, before)
        self.assertEqual([item["id"] for item in restored.summary()],
                         list(STYLE_IDS))
        self.assertFalse(any("caption" in item for item in restored.summary()))

    def test_reject_unknown_media_corrupt_tapes_and_bad_versions(self):
        bundle = VariantWorkspace.fork(source())
        old = bundle.as_dict()
        for mutate in (
            lambda b: b.__setitem__("schema_version", 2),
            lambda b: b.__setitem__("unknown", "code"),
            lambda b: b.__setitem__("active", "arbitrary"),
            lambda b: b["projects"].pop("authority"),
            lambda b: b["projects"]["social_impact"]["media"].__setitem__("sha256","b"*64),
            lambda b: b["projects"]["social_impact"].__setitem__("schema_version",999),
            lambda b: b["projects"]["authority"].__setitem__("revision",-1),
        ):
            damaged = copy.deepcopy(old)
            mutate(damaged)
            with self.subTest(damaged=damaged), self.assertRaises(ValueError):
                VariantWorkspace.from_dict(damaged)
        other = source().append("timeline.approve", {})
        with self.assertRaises(ValueError):
            VariantWorkspace.from_dict(old, source_tape=other)
        with self.assertRaises(ValueError):
            bundle.switch("unknown")


if __name__ == "__main__":
    unittest.main()
