"""Regression tests for the design-only automatic visual effect preset contract."""
from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "validate_visual_fx_presets.py"
spec = importlib.util.spec_from_file_location("pausio_visual_fx_validator", CHECKER)
assert spec and spec.loader
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class VisualFxPresetsTests(unittest.TestCase):
    def setUp(self):
        self.doc = json.loads(checker.CONFIG.read_text(encoding="utf-8"))

    def test_shipped_profiles_validate_and_are_suggestion_only(self):
        self.assertEqual(checker.validate(self.doc), [])
        self.assertEqual(set(self.doc["profiles"]), set(checker.PROFILE_IDS))
        self.assertEqual(self.doc["default_profile"], "naturale")
        for profile in self.doc["profiles"].values():
            self.assertEqual(profile["execution_mode"], "suggest")
            self.assertTrue(profile["guards"]["protect_speech"])
            self.assertTrue(profile["guards"]["protect_manual_edits"])

    def test_extreme_zoom_is_rejected(self):
        self.doc["profiles"]["naturale"]["zoom"]["punch_max_scale"] = 4.7
        self.assertTrue(any("zoom" in p for p in checker.validate(self.doc)))

    def test_density_over_budget_is_rejected(self):
        self.doc["profiles"]["dinamico"]["cadence"]["max_effects_per_minute"] = 1000
        self.assertTrue(any("cadence" in p for p in checker.validate(self.doc)))

    def test_integer_limits_cannot_be_bypassed_by_boolean(self):
        self.doc["profiles"]["dinamico"]["cadence"]["max_effects_per_minute"] = True
        self.assertTrue(any("cadence" in p for p in checker.validate(self.doc)))

    def test_invalid_automatic_acceptance_mode_is_rejected(self):
        self.doc["profiles"]["naturale"]["execution_mode"] = "silent_auto_apply"
        self.assertTrue(any("execution_mode" in p for p in checker.validate(self.doc)))

    def test_rejected_protection_disable(self):
        self.doc["profiles"]["educativo"]["guards"]["protect_manual_edits"] = False
        self.assertTrue(any("guards" in p for p in checker.validate(self.doc)))

    def test_transition_needs_safe_context_and_duration(self):
        p = self.doc["profiles"]["educativo"]["transition"]
        p["context_change_only"] = False
        self.assertTrue(any("transition" in issue for issue in checker.validate(self.doc)))
        p["context_change_only"] = True
        p["duration_ms"] = 2000
        self.assertTrue(any("transition" in issue for issue in checker.validate(self.doc)))

    def test_unknown_effect_or_ffmpeg_filter_injection_is_rejected(self):
        self.doc["profiles"]["dinamico"]["allowed_moves"].append("zoom:eval=system('curl')")
        self.assertTrue(any("allowed_moves" in issue for issue in checker.validate(self.doc)))

    def test_schema_version_and_unknown_keys_fail_closed(self):
        self.doc["schema_version"] = 2
        self.assertTrue(any("schema_version" in issue for issue in checker.validate(self.doc)))
        self.doc["schema_version"] = 1
        self.doc["shell"] = "echo bad"
        self.assertTrue(any("root" in issue for issue in checker.validate(self.doc)))

    def test_weights_have_a_defined_budget(self):
        self.doc["profiles"]["educativo"]["signals"]["speech_energy"] = 60
        self.assertTrue(any("signals" in issue for issue in checker.validate(self.doc)))

    def test_nan_scores_are_rejected(self):
        self.doc["profiles"]["educativo"]["zoom"]["punch_max_scale"] = float("nan")
        self.assertTrue(any("zoom" in issue for issue in checker.validate(self.doc)))

    def test_customized_copy_can_remain_within_bounds(self):
        edited = copy.deepcopy(self.doc)
        custom = edited["profiles"]["personalizzato"]
        custom["cadence"]["max_effects_per_minute"] = 4
        custom["zoom"]["punch_max_scale"] = 1.16
        self.assertEqual(checker.validate(edited), [])


if __name__ == "__main__":
    unittest.main()
