"""Portable Pausio project event/replay contract tests."""

import copy
import json
import unittest
import uuid

from pausio.project_commands import (
    FORMAT, VERSION, ProjectTape, ProjectFormatError,
)


def media():
    return {
        "filename": "video-a56.mp4",
        "sha256": "c" * 64,
        "duration_ms": 12_000,
        "has_audio": True,
    }


def segment(start, end, key=None):
    return {"id": key or uuid.uuid4().hex, "start_ms": start, "end_ms": end}


def proposed():
    a, b = segment(0, 2000), segment(4000, 12000)
    return [a, b]


def analyze(tape, items=None):
    return tape.append("analysis.propose", {
        "engine": "ffmpeg.silencedetect",
        "policy": "ai-natural",
        "noise_db": -35,
        "segments": items or proposed(),
    })


class ProjectReplayTests(unittest.TestCase):
    def test_precise_commands_replay_to_same_edit_plan_after_json_import(self):
        tape = analyze(ProjectTape(media()))
        first, second = tape.view.segments
        tape = tape.append("segment.update", {
            "segment_id": first["id"], "start_ms": 100, "end_ms": 1800
        })
        tape = tape.append("segment.remove", {"segment_id": second["id"]})
        tape = tape.append("segment.insert", {"segment": segment(5000, 10_500)})
        tape = tape.append("timeline.approve", {})
        exported = json.loads(json.dumps(tape.as_dict()))
        recovered = ProjectTape.from_dict(exported)
        self.assertEqual(exported["format"], FORMAT)
        self.assertEqual(exported["schema_version"], VERSION)
        self.assertEqual(recovered.as_dict(), tape.as_dict())
        self.assertEqual(recovered.view, tape.view)
        self.assertTrue(recovered.view.approved)
        self.assertEqual(recovered.edit_plan("/tmp/video.mp4").output_duration_ms, 7200)
        self.assertEqual(recovered.revision, 5)
        self.assertNotIn("/tmp/video.mp4", json.dumps(exported))
        self.assertEqual(
            [c["type"] for c in exported["commands"]],
            ["analysis.propose", "segment.update", "segment.remove", "segment.insert",
             "timeline.approve"],
        )

    def test_keep_all_and_restore_original_ai_proposal(self):
        tape = analyze(ProjectTape(media()))
        suggested = tape.view.suggested
        tape = tape.append("timeline.keep_all", {}).append("timeline.approve", {})
        self.assertEqual((tape.view.segments[0]["start_ms"],
                          tape.view.segments[0]["end_ms"]), (0, 12_000))
        self.assertTrue(tape.view.approved)
        tape = tape.append("timeline.restore_suggestion", {})
        self.assertEqual(tape.view.segments, suggested)
        self.assertFalse(tape.view.approved)
        recovered = ProjectTape.from_dict(tape.as_dict())
        self.assertEqual(recovered.view, tape.view)

    def test_approval_invalidated_on_every_mutation(self):
        for kind, payload in (
            ("segment.update", lambda s: {
                "segment_id": s[0]["id"], "start_ms": 0, "end_ms": 1990}),
            ("segment.remove", lambda s: {"segment_id": s[1]["id"]}),
            ("segment.insert", lambda s: {"segment": segment(2100, 2200)}),
            ("timeline.keep_all", lambda s: {}),
            ("timeline.restore_suggestion", lambda s: {}),
        ):
            with self.subTest(kind=kind):
                approved = analyze(ProjectTape(media())).append("timeline.approve", {})
                self.assertFalse(approved.append(kind, payload(approved.view.segments)).view.approved)

    def test_media_digest_required_to_bind_imported_project(self):
        tape = analyze(ProjectTape(media()))
        tape.require_media(sha256="c" * 64, duration_ms=12_000, has_audio=True)
        for digest, duration, audio in (
            ("0" * 64, 12_000, True),
            ("c" * 64, 11_000, True),
            ("c" * 64, 12_000, False),
        ):
            with self.subTest(digest=digest, duration=duration, audio=audio):
                with self.assertRaises(ProjectFormatError):
                    tape.require_media(sha256=digest, duration_ms=duration, has_audio=audio)

    def test_rejects_unsupported_version_op_and_corrupted_event(self):
        tape = analyze(ProjectTape(media()))
        d = tape.as_dict()
        mutated = copy.deepcopy(d)
        mutated["schema_version"] = 2
        with self.assertRaises(ProjectFormatError):
            ProjectTape.from_dict(mutated)
        mutated = copy.deepcopy(d)
        mutated["commands"][0]["type"] = "execute.python"
        with self.assertRaises(ProjectFormatError):
            ProjectTape.from_dict(mutated)
        mutated = copy.deepcopy(d)
        mutated["commands"][0]["payload"]["segments"][0]["end_ms"] = 5000
        with self.assertRaises(ProjectFormatError):
            ProjectTape.from_dict(mutated)
        mutated = copy.deepcopy(d)
        mutated["commands"][0]["payload"]["extra"] = "unexpected"
        with self.assertRaises(ProjectFormatError):
            ProjectTape.from_dict(mutated)
        mutated = copy.deepcopy(d)
        mutated["commands"][0]["type"] = []
        with self.assertRaises(ProjectFormatError):
            ProjectTape.from_dict(mutated)

    def test_rejects_duplicated_ids_unsafe_paths_and_wrong_payload(self):
        with self.assertRaises(ProjectFormatError):
            ProjectTape({**media(), "filename": "../attack.mp4"})
        with self.assertRaises(ProjectFormatError):
            ProjectTape({**media(), "filename": "C:\\\\temp\\\\attack.mp4"})
        tape = analyze(ProjectTape(media()))
        duplicated = tape.as_dict()
        duplicated["commands"].append(copy.deepcopy(duplicated["commands"][0]))
        with self.assertRaises(ProjectFormatError):
            ProjectTape.from_dict(duplicated)
        with self.assertRaises(ProjectFormatError):
            tape.append("segment.update", {"segment_id": uuid.uuid4().hex,
                                           "start_ms": 0, "end_ms": 1000})
        with self.assertRaises(ProjectFormatError):
            tape.append("segment.remove", {"segment_id": "not-a-id"})
        with self.assertRaises(ProjectFormatError):
            tape.append("segment.insert", {"segment": {
                **segment(100, 200), "unexpected": True
            }})

    def test_invalid_actions_do_not_mutate_older_project(self):
        tape = analyze(ProjectTape(media()))
        original = json.dumps(tape.as_dict(), sort_keys=True)
        with self.assertRaises(ProjectFormatError):
            tape.append("segment.update", {
                "segment_id": tape.view.segments[0]["id"],
                "start_ms": 3000, "end_ms": 5000
            })
        self.assertEqual(json.dumps(tape.as_dict(), sort_keys=True), original)


if __name__ == "__main__":
    unittest.main()
