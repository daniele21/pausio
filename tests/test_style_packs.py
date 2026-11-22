"""Style Pack and storyboard tests: no hidden edits, placeholders or false statistics."""
from __future__ import annotations

import json
import unittest
from copy import deepcopy

from pausio.scene_templates import TEMPLATES, validate_scene
from pausio.style_packs import PACKS, catalog, propose_three_variants, propose_variant


def copy_fields(template: str, **values) -> dict:
    # Fixture-only defaults. The production planner NEVER fills missing fields.
    content = {f["key"]: f["default"] for f in TEMPLATES[template]["fields"]}
    content.update(values)
    return content


def beat(a, b, purpose, visuals, verified=False):
    return {
        "start_ms": a, "end_ms": b, "purpose": purpose,
        "visuals": visuals, "evidence_verified": verified,
    }


def sample_beats():
    return [
        beat(0, 4000, "hook", {
            "floating_insight": copy_fields(
                "floating_insight", title="LA PASSWORD PUÒ FINIRE ONLINE",
                detail="Anche quando usi un agente per programmare",
            ),
        }),
        beat(5200, 11000, "problem", {
            "permission_mock": copy_fields("permission_mock"),
        }),
        beat(12500, 18000, "evidence", {
            "metric_spotlight": copy_fields(
                "metric_spotlight", heading="NUMERO DIMOSTRATIVO", number="3",
                unit="PASSAGGI", detail="Dati illustrativi per il test",
                source_note="PROTOTIPO • NON PUBBLICARE COME DATO REALE",
            ),
        }, verified=True),
        beat(19500, 25000, "explanation", {
            "code_inspector": copy_fields("code_inspector"),
        }),
        beat(27000, 31000, "takeaway", {
            "floating_insight": copy_fields("floating_insight"),
        }),
    ]


class StylePackTests(unittest.TestCase):
    def test_catalog_and_distinct_policies(self):
        self.assertEqual(list(PACKS), [
            "authority", "visual_explainer", "social_impact",
        ])
        names = [row["id"] for row in catalog()]
        self.assertEqual(names, list(PACKS))
        self.assertEqual(len({row["caption_preset"] for row in catalog()}), 3)
        self.assertEqual(len({row["max_scenes_per_minute"] for row in catalog()}), 3)

    def test_three_deterministic_reviewable_storyboards(self):
        beats = sample_beats()
        before = deepcopy(beats)
        result = propose_three_variants(beats, 35000)
        self.assertEqual(result, propose_three_variants(beats, 35000))
        self.assertEqual(beats, before)
        self.assertEqual([len(r["candidates"]) for r in result.values()],
                         [2, 4, 5])
        self.assertEqual(
            [c["payload"]["scene"]["template"] for c in
             result["visual_explainer"]["candidates"]],
            ["floating_insight", "permission_mock", "metric_spotlight",
             "code_inspector"],
        )
        for name, variant in result.items():
            self.assertEqual(variant["style_id"], name)
            self.assertTrue(variant["requires_editor_review"])
            self.assertEqual(variant["output_ms"], 35000)
            json.dumps(variant, ensure_ascii=False)
            previous_end = 0
            for candidate in variant["candidates"]:
                self.assertEqual(candidate["command_type"], "scene.template.add")
                scene = candidate["payload"]["scene"]
                self.assertEqual(validate_scene(scene, 35000), scene)
                self.assertGreaterEqual(scene["start_ms"], previous_end)
                previous_end = scene["start_ms"] + scene["duration_ms"]

    def test_unverified_metric_never_suggested(self):
        beats = sample_beats()
        beats[2]["evidence_verified"] = False
        for row in propose_three_variants(beats, 35000).values():
            self.assertNotIn("metric_spotlight", [
                c["payload"]["scene"]["template"] for c in row["candidates"]
            ])
        impact = propose_variant(beats, 35000, "social_impact")
        self.assertIn("unverified_metric", [s["reason"] for s in impact["skipped"]])

    def test_missing_content_not_synthesized(self):
        beats = [beat(0, 4000, "hook", {
            "floating_insight": {"title": "Una frase senza dettaglio"},
        })]
        result = propose_variant(beats, 4000, "authority")
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["skipped"][0]["reason"],
                         "invalid_or_incomplete_reviewed_visual")

    def test_strict_timing_data_and_style_validation(self):
        beats = sample_beats()
        for bad in (None, True, 0, 172800001):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                propose_three_variants(beats, bad)
        for style in ("", "arbitrary", None):
            with self.assertRaises(ValueError):
                propose_variant(beats, 35000, style)
        invalid = [
            [{**beats[0], "end_ms": 99999}],
            [beat(100, 2000, "hook", {}), beat(1500, 3000, "problem", {})],
            [{**beats[0], "start_ms": True}],
            [{**beats[0], "evidence_verified": "yes"}],
            [{**beats[0], "purpose": "viral"}],
            [{**beats[0], "visuals": {"script_tag": {}}}],
            [{**beats[0], "unknown": "extra"}],
        ]
        for row in invalid:
            with self.subTest(case=row), self.assertRaises(ValueError):
                propose_three_variants(row, 35000)


if __name__ == "__main__":
    unittest.main()
