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
    def test_cut_settings_roundtrip_undo_and_strict_validation(self):
        from pausio.planner import CUT_PRESETS, validate_cut_settings
        natural=validate_cut_settings()
        self.assertEqual(natural["preset"], "natural")
        custom={"preset":"custom",**CUT_PRESETS["dynamic"]}
        custom["noise_db"]=-22
        tape=ProjectTape(media()).append("analysis.propose",{
            "engine":"ffmpeg.silencedetect", "policy":"ai-natural",
            "noise_db":custom["noise_db"], "segments":proposed(),
            "settings":custom, "detected_silences":4,
        })
        self.assertEqual(tape.view.analysis_settings,custom)
        self.assertEqual(tape.view.detected_silences,4)
        self.assertEqual(ProjectTape.from_dict(tape.as_dict()).view,tape.view)
        self.assertIsNone(tape.undo().view.analysis_settings)
        self.assertEqual(tape.undo().redo().view.analysis_settings,custom)
        invalid=copy.deepcopy(tape.as_dict())
        invalid["commands"][0]["payload"]["settings"]["noise_db"]=-35
        with self.assertRaises(ProjectFormatError):
            ProjectTape.from_dict(invalid)
        for change in [{"preset":"natural"}, {"noise_db":True}, {"min_silence_ms":50}]:
            malformed={**custom,**change}
            with self.assertRaises(ValueError):
                validate_cut_settings(malformed)

    def test_legacy_analysis_import_retains_historical_defaults(self):
        tape=analyze(ProjectTape(media()))
        imported=ProjectTape.from_dict(tape.as_dict())
        self.assertEqual(imported.view.analysis_settings["preset"],"natural")
        self.assertIsNone(imported.view.detected_silences)


    def test_portable_captions_edit_undo_redo_and_approval(self):
        tape = analyze(ProjectTape(media()))
        tape = tape.append("caption.set", {
            "style": "social", "cues": [
                {"id": "a"*32, "start_ms": 0, "end_ms": 1100, "text": "Tre consigli"},
                {"id": "b"*32, "start_ms": 2200, "end_ms": 3200, "text": "AI locale"},
            ]
        })
        tape = tape.append("timeline.approve", {})
        self.assertTrue(tape.view.approved)
        tape = tape.append("caption.correct", {
            "caption_id": "a"*32, "text": "Tre consigli AI"
        })
        self.assertFalse(tape.view.approved)
        self.assertEqual(tape.view.captions[0]["text"], "Tre consigli AI")
        tape = tape.append("caption.style", {"style": "minimal"})
        self.assertEqual(tape.view.caption_style, "minimal")
        self.assertEqual(ProjectTape.from_dict(tape.as_dict()).view, tape.view)
        after_undo = tape.undo()
        self.assertEqual(after_undo.view.caption_style, "social")
        self.assertEqual(after_undo.redo().view.caption_style, "minimal")
        self.assertFalse(tape.append("caption.clear", {}).view.captions)
        for kind, payload in [
            ("caption.correct", {"caption_id":"f"*32,"text":"wrong target"}),
            ("caption.style", {"style":"unexpected"}),
            ("caption.set", {"style":"social","cues":[{
                "id":"a"*32,"start_ms":0,"end_ms":1200,"text":"first"
            },{
                "id":"b"*32,"start_ms":1000,"end_ms":2000,"text":"overlap"
            }]}),
            ("caption.correct", {"caption_id":"a"*32,"text":"{\\unsafe}"}),
        ]:
            with self.subTest(kind=kind), self.assertRaises(ProjectFormatError):
                tape.append(kind, payload)
        self.assertEqual(tape.view.captions[0]["text"], "Tre consigli AI")

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
        mutated["schema_version"] = 3
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
        with self.assertRaises(ProjectFormatError):
            tape.append("segment.insert", {"segment": {
                **segment(2100, 2300), "start_ms": "not a timestamp"
            }})

    def test_undo_redo_export_import_and_new_branch(self):
        tape = analyze(ProjectTape(media()))
        s = tape.view.segments[0]
        original_id = s["id"]
        tape = tape.append("segment.update", {
            "segment_id": original_id, "start_ms": 100, "end_ms": 1800
        }).append("timeline.approve", {})
        self.assertEqual(tape.revision, 3)
        self.assertTrue(tape.view.approved)

        undo_approval = tape.undo()
        self.assertFalse(undo_approval.view.approved)
        self.assertTrue(undo_approval.can_redo)
        self.assertEqual(undo_approval.history_cursor, 2)
        self.assertEqual(undo_approval.revision, 4)
        undo_trim = undo_approval.undo()
        self.assertEqual(undo_trim.view.segments[0]["id"], original_id)
        self.assertEqual(undo_trim.view.segments[0]["start_ms"], s["start_ms"])
        self.assertEqual(undo_trim.revision, 5)

        portable = ProjectTape.from_dict(json.loads(json.dumps(undo_trim.as_dict())))
        self.assertEqual(portable.revision, 5)
        self.assertEqual(portable.history_cursor, 1)
        self.assertEqual(len(portable.commands), 3)
        self.assertTrue(portable.can_undo)
        self.assertTrue(portable.can_redo)
        redo = portable.redo().redo()
        self.assertEqual(redo.view, tape.view)
        self.assertEqual(redo.revision, 7)

        forked = portable.append("timeline.keep_all", {})
        self.assertEqual(forked.history_cursor, 2)
        self.assertEqual(len(forked.commands), 2)
        self.assertFalse(forked.can_redo)
        self.assertEqual(forked.revision, 6)
        self.assertEqual(forked.view.segments[0]["end_ms"], 12_000)

    def test_v1_import_migrates_without_changing_legacy_event_ids(self):
        original = analyze(ProjectTape(media()))
        v1 = original.as_dict()
        del v1["history_cursor"]
        del v1["revision"]
        v1["schema_version"] = 1
        restored = ProjectTape.from_dict(v1)
        self.assertEqual(restored.as_dict()["schema_version"], 2)
        self.assertEqual(restored.commands, original.commands)
        self.assertEqual(restored.view, original.view)
        self.assertEqual(restored.history_cursor, len(original.commands))
        self.assertFalse(restored.can_redo)

    def test_invalid_cursor_revision_redo_tail_and_empty_history(self):
        tape = analyze(ProjectTape(media())).undo()
        document = tape.as_dict()
        for key, value in (
            ("history_cursor", -1),
            ("history_cursor", 5),
            ("history_cursor", True),
            ("revision", 0),
            ("revision", True),
            ("revision", 2**40),
        ):
            broken = copy.deepcopy(document)
            broken[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ProjectFormatError):
                ProjectTape.from_dict(broken)
        broken = copy.deepcopy(document)
        broken["commands"][0]["payload"]["segments"][0]["end_ms"] = 50_000
        with self.assertRaises(ProjectFormatError):
            ProjectTape.from_dict(broken)

        with self.assertRaises(ProjectFormatError):
            ProjectTape(media()).undo()
        with self.assertRaises(ProjectFormatError):
            ProjectTape(media()).redo()
        with self.assertRaises(ProjectFormatError):
            analyze(ProjectTape(media())).redo()

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
