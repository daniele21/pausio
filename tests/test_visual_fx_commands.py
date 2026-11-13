"""Pure source-anchored video effect replay, migration and validation tests."""
import copy
import unittest
import uuid

from pausio.project_commands import ProjectTape, ProjectFormatError, VERSION


def fixture():
    return {"filename": "talking-head.mp4", "sha256": "a" * 64,
            "duration_ms": 12000, "has_audio": True}


def segment(start, end):
    return {"id": uuid.uuid4().hex, "start_ms": start, "end_ms": end}


def effect(seg, *, start=1000, end=2500, kind="punch", scale=116):
    return {"id": uuid.uuid4().hex, "segment_id": seg["id"], "start_ms": start,
            "end_ms": end, "kind": kind, "start_scale_pct": scale if kind == "punch" else 100,
            "end_scale_pct": scale, "anchor_x_pct": 50, "anchor_y_pct": 48}


class VideoFxCommandsTests(unittest.TestCase):
    def setUp(self):
        self.a, self.b = segment(0, 3500), segment(5000, 12000)
        self.tape = ProjectTape(fixture()).append(
            "timeline.replace", {"segments": [self.a, self.b]}
        )

    def test_add_update_remove_replay_and_v3_export(self):
        fx = effect(self.a)
        added = self.tape.append("video.transform.add", {"effect": fx})
        self.assertEqual(added.view.video_fx[0], fx)
        self.assertEqual(added.as_dict()["schema_version"], VERSION)
        self.assertEqual(VERSION, 4)
        self.assertFalse(added.view.approved)
        replacement = {**fx, "start_scale_pct": 122, "end_scale_pct": 122,
                       "anchor_x_pct": 54}
        changed = added.append("video.transform.update", {"effect": replacement})
        self.assertEqual(changed.view.video_fx, (replacement,))
        self.assertEqual(changed.undo().view.video_fx, (fx,))
        self.assertEqual(changed.undo().redo().view.video_fx, (replacement,))
        self.assertEqual(ProjectTape.from_dict(changed.as_dict()).view.video_fx, (replacement,))
        removed = changed.append("video.transform.remove", {"effect_id": fx["id"]})
        self.assertEqual(removed.view.video_fx, ())
        self.assertEqual(removed.undo().view.video_fx, (replacement,))

    def test_v2_backward_compatibility_and_v3_migration(self):
        old = self.tape.as_dict()
        old["schema_version"] = 2
        restored = ProjectTape.from_dict(old)
        self.assertEqual(restored.view.video_fx, ())
        self.assertEqual(restored.as_dict()["schema_version"], 4)
        fx = effect(self.a)
        self.assertEqual(restored.append("video.transform.add", {"effect": fx}).view.video_fx, (fx,))

    def test_source_anchor_does_not_shift_across_removed_gap(self):
        fx = effect(self.b, start=5200, end=6300)
        changed = self.tape.append("video.transform.add", {"effect": fx})
        self.assertEqual(changed.view.video_fx[0]["start_ms"], 5200)
        # Shortening the segment beyond the effect invalidates the edit; it
        # must never silently reposition FX on a different piece of speech.
        with self.assertRaises(ProjectFormatError):
            changed.append("segment.update", {
                "segment_id": self.b["id"], "start_ms": 7000, "end_ms": 12000})
        self.assertEqual(changed.view.video_fx[0], fx)

    def test_ease_and_ratchet_are_versioned_replayable_motions(self):
        for kind in ("ease_push", "ratchet"):
            with self.subTest(kind=kind):
                base=effect(self.a,kind=kind,scale=126)
                tape=self.tape.append("video.transform.add",{"effect":base})
                self.assertEqual(tape.view.video_fx[0]["kind"],kind)
                copy_=ProjectTape.from_dict(tape.as_dict())
                self.assertEqual(copy_.view.video_fx,tape.view.video_fx)
                self.assertEqual(copy_.undo().view.video_fx,())
        old=self.tape.as_dict()
        old["schema_version"]=3
        self.assertEqual(ProjectTape.from_dict(old).as_dict()["schema_version"],4)

    def test_invalid_effects_rejected_without_mutating_original(self):
        base = effect(self.a)
        for change in (
            {"start_scale_pct": 500, "end_scale_pct": 500},
            {"start_scale_pct": 99},
            {"anchor_x_pct": -1},
            {"end_ms": 4000},
            {"end_ms": 1010},
            {"kind": "run_ffmpeg"},
            {"start_ms": True},
            {"segment_id": uuid.uuid4().hex},
            {"anchor_y_pct": 125},
            {"shell": "echo hi"},
        ):
            with self.subTest(change=change), self.assertRaises(ProjectFormatError):
                self.tape.append("video.transform.add", {"effect": {**base, **change}})
        self.assertEqual(self.tape.view.video_fx, ())

    def test_overlap_and_duplicate_effects_fail(self):
        fx = effect(self.a)
        one = self.tape.append("video.transform.add", {"effect": fx})
        overlap = effect(self.a, start=2000, end=3400)
        with self.assertRaises(ProjectFormatError):
            one.append("video.transform.add", {"effect": overlap})
        same_id = {**effect(self.b, start=6000, end=7400), "id": fx["id"]}
        with self.assertRaises(ProjectFormatError):
            one.append("video.transform.add", {"effect": same_id})
        neighbor = effect(self.a, start=2500, end=3400)
        allowed = one.append("video.transform.add", {"effect": neighbor})
        self.assertEqual(len(allowed.view.video_fx), 2)

    def test_invalid_redo_event_is_rejected_when_history_cursor_is_before_it(self):
        fx = effect(self.a)
        good = self.tape.append("video.transform.add", {"effect": fx})
        bad_doc = good.as_dict()
        bad_doc["history_cursor"] = 1
        bad_doc["commands"][-1]["payload"]["effect"]["end_scale_pct"] = 999
        with self.assertRaises(ProjectFormatError):
            ProjectTape.from_dict(bad_doc)

    def test_source_media_sha_validation_remains_strict(self):
        fx = effect(self.a)
        one = self.tape.append("video.transform.add", {"effect": fx})
        one.require_media(sha256="a"*64,duration_ms=12000,has_audio=True)
        with self.assertRaises(ProjectFormatError):
            one.require_media(sha256="b"*64,duration_ms=12000,has_audio=True)


if __name__ == "__main__":
    unittest.main()
