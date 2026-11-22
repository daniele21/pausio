"""Local Studio three-version workflow and crash-safe v3 recovery."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pausio.studio import StudioError
from pausio.studio_persistence import STATE_FILE, SESSION_VERSION, VARIANT_SESSION_VERSION
from test_studio_recovery import imported_workspace, new_workspace, applied_plan


class VariantStudioTests(unittest.TestCase):
    def test_fork_switch_edit_and_restart_preserve_each_revision(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td) / "private"
            ws = imported_workspace(directory)
            try:
                applied_plan(ws)
                baseline = ws.tape.as_dict()
                first_id = ws.media_id
                ws.fork_style_variants({"revision": ws.tape.revision})
                self.assertNotEqual(ws.media_id, first_id)
                self.assertEqual(len(ws.snapshot()["variant_workspaces"]), 3)
                self.assertEqual(ws.snapshot()["active_variant"], "authority")
                self.assertEqual(ws.tape.as_dict(), baseline)
                self.assertEqual(json.loads((directory / STATE_FILE).read_text())
                                 ["schema_version"], VARIANT_SESSION_VERSION)
                authority_rev = ws.tape.revision
                ws.switch_style_variant({
                    "revision": ws.tape.revision,
                    "style_id": "social_impact",
                })
                self.assertEqual(ws.snapshot()["active_variant"], "social_impact")
                self.assertEqual(ws.tape.revision, authority_rev)
                ws.approve_plan()
                impact_rev = ws.tape.revision
                self.assertTrue(ws.tape.view.approved)
                ws.switch_style_variant({
                    "revision": impact_rev, "style_id": "authority"
                })
                self.assertEqual(ws.tape.revision, authority_rev)
                self.assertFalse(ws.tape.view.approved)
                ws.switch_style_variant({
                    "revision": authority_rev, "style_id": "social_impact"
                })
                self.assertEqual(ws.tape.revision, impact_rev)
                self.assertTrue(ws.tape.view.approved)
            finally:
                ws.close()
            restored = new_workspace(directory)
            try:
                self.assertTrue(restored.snapshot()["recovered"])
                self.assertEqual(restored.snapshot()["active_variant"], "social_impact")
                self.assertEqual(restored.tape.revision, impact_rev)
                self.assertEqual(len(restored.snapshot()["variant_workspaces"]), 3)
                restored.switch_style_variant({
                    "revision": impact_rev, "style_id": "authority"
                })
                self.assertEqual(restored.tape.revision, authority_rev)
                self.assertFalse(restored.tape.view.approved)
                restored.clear_session()
                self.assertEqual(restored.snapshot()["variant_workspaces"], [])
                self.assertFalse((directory / STATE_FILE).exists())
            finally:
                restored.close()

    def test_same_media_guard_stale_revision_and_existing_variants(self):
        with tempfile.TemporaryDirectory() as td:
            ws = imported_workspace(Path(td)/"private")
            try:
                applied_plan(ws)
                for request in ({"revision": ws.tape.revision + 1},
                                {"revision": True}, {},
                                {"revision": ws.tape.revision, "extra": True}):
                    with self.assertRaises(StudioError):
                        ws.fork_style_variants(request)
                ws.fork_style_variants({"revision": ws.tape.revision})
                with self.assertRaises(StudioError):
                    ws.fork_style_variants({"revision": ws.tape.revision})
                for request in ({"style_id": "arbitrary", "revision": ws.tape.revision},
                                {"style_id": "social_impact", "revision": True},
                                {"style_id": "social_impact", "revision": ws.tape.revision + 1},
                                {"style_id": "social_impact"}):
                    with self.assertRaises(StudioError):
                        ws.switch_style_variant(request)
            finally:
                ws.close()

    def test_legacy_v2_session_is_left_unchanged_without_variants(self):
        with tempfile.TemporaryDirectory() as td:
            ws=imported_workspace(Path(td)/"private")
            try:
                applied_plan(ws)
                saved=json.loads((Path(td)/"private"/STATE_FILE).read_text())
                self.assertEqual(saved["schema_version"], SESSION_VERSION)
                self.assertNotIn("variants",saved)
            finally:
                ws.close()


if __name__ == "__main__":
    unittest.main()
