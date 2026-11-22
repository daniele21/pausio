"""Studio read-only storyboard API contract; no video, ASR or network required."""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from pausio.project_commands import ProjectTape
from pausio.scene_templates import TEMPLATES
from pausio.studio import StudioError, StudioWorkspace


class StudioStylePackTests(unittest.TestCase):
    def setUp(self):
        self.workspace = StudioWorkspace()
        self.workspace.source = self.workspace.directory / "synthetic.mp4"
        self.workspace.media_sha256 = "a" * 64
        self.workspace.info = SimpleNamespace(duration_ms=12000, as_dict=lambda: {"duration_ms": 12000})
        tape = ProjectTape({
            "filename": "synthetic.mp4", "sha256": "a" * 64,
            "duration_ms": 12000, "has_audio": True,
        }).append("timeline.keep_all", {})
        self.workspace._install_tape(tape)

    def tearDown(self):
        self.workspace.close()

    def _beats(self):
        return [{
            "start_ms": 0, "end_ms": 4000, "purpose": "hook",
            "visuals": {
                "floating_insight": {
                    field["key"]: field["default"] for field in
                    TEMPLATES["floating_insight"]["fields"]
                },
            },
            "evidence_verified": False,
        }]

    def test_catalog_visible_but_no_change_to_tape(self):
        snapshot = self.workspace.snapshot()
        self.assertEqual(len(snapshot["style_pack_catalog"]), 3)
        before = self.workspace.tape.as_dict()
        result = self.workspace.suggest_style_variants({
            "revision": self.workspace.tape.revision,
            "beats": self._beats(),
        })
        self.assertTrue(result["review_required"])
        self.assertEqual(result["base_revision"], self.workspace.tape.revision)
        self.assertEqual(result["media_sha256"], "a" * 64)
        self.assertEqual(set(result["variants"]), {
            "authority", "visual_explainer", "social_impact",
        })
        self.assertEqual(before, self.workspace.tape.as_dict())

    def test_automatic_three_style_technical_proposals_are_read_only(self):
        before = self.workspace.tape.as_dict()
        response = self.workspace.suggest_style_variants_auto({
            "revision": self.workspace.tape.revision,
        })
        self.assertEqual(response["base_revision"], self.workspace.tape.revision)
        self.assertTrue(response["review_required"])
        self.assertEqual(set(response["variants"]), {
            "authority", "visual_explainer", "social_impact",
        })
        self.assertEqual([
            x["caption_preset_suggestion"] for x in response["variants"].values()
        ], ["minimal", "word_focus", "kinetic"])
        for variant in response["variants"].values():
            self.assertIn("semantic_director", variant["missing_signals"])
            for candidate in variant["candidates"]:
                self.assertIn(candidate["command_type"], {
                    "graphic.overlay.add", "video.transform.add",
                })
        self.assertEqual(self.workspace.tape.as_dict(), before)

    def test_automatic_style_rejects_bad_payload_and_stale_revision(self):
        revision = self.workspace.tape.revision
        for request in (
            {"revision": revision + 1},
            {"revision": True},
            {"revision": revision, "beats": []},
            {},
        ):
            with self.subTest(request=request), self.assertRaises(StudioError):
                self.workspace.suggest_style_variants_auto(request)
        self.workspace.tape = None
        with self.assertRaises(StudioError):
            self.workspace.suggest_style_variants_auto({"revision": revision})

    def test_fails_closed_on_stale_revision_invalid_beats_or_missing_media(self):
        for request in (
            {"revision": self.workspace.tape.revision + 1,
             "beats": self._beats()},
            {"revision": True, "beats": self._beats()},
            {"revision": self.workspace.tape.revision, "beats": []},
            {"revision": self.workspace.tape.revision, "beats": self._beats(),
             "unknown": "ignored"},
        ):
            with self.subTest(request=request), self.assertRaises(StudioError):
                self.workspace.suggest_style_variants(request)
        self.workspace.info = None
        with self.assertRaises(StudioError):
            self.workspace.suggest_style_variants({
                "revision": self.workspace.tape.revision,
                "beats": self._beats(),
            })


if __name__ == "__main__":
    unittest.main()
