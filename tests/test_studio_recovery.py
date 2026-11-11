"""Crash/restart, local privacy, and atomic-save regression tests.

Media probing is mocked: persistence tests concern session integrity and replay,
not codec support. Synthetic FFmpeg HTTP E2E remains in tests/test_studio.py.
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from pausio.media import MediaInfo
from pausio.studio import StudioWorkspace, StudioError
from pausio.studio_persistence import RecoveryError, STATE_FILE, BACKUP_FILE

INFO = MediaInfo(3000, 180, 320, True, "h264", "15/1")


def new_workspace(directory: Path) -> StudioWorkspace:
    with patch("pausio.studio.probe", return_value=INFO):
        return StudioWorkspace(data_dir=directory)


def imported_workspace(directory: Path) -> StudioWorkspace:
    ws = new_workspace(directory)
    candidate, label = ws.begin_import("ripresa smartphone.mp4")
    candidate.write_bytes(b"confidential original video bytes")
    ws.finish_import(candidate, label, INFO)
    return ws


def sample_transcript(ws: StudioWorkspace) -> dict:
    return {
        "schema_version": 1, "source": str(ws.source),
        "source_duration_ms": INFO.duration_ms, "provider": "pausio-local",
        "backend": "mlx-whisper", "model": "mlx-community/whisper-large-v3-turbo",
        "language": "it", "text": "Tre consigli per creare video. AI e coding.",
        "word_timestamps_available": True, "warnings": [],
        "segments": [
            {"start_ms":100, "end_ms":1400, "text":"Tre consigli per creare video.",
             "words":[{"start_ms":100,"end_ms":350,"text":"Tre"},
                      {"start_ms":400,"end_ms":900,"text":"consigli"},
                      {"start_ms":950,"end_ms":1400,"text":"video."}]},
            {"start_ms":1700, "end_ms":2800, "text":"AI e coding.",
             "words":[{"start_ms":1700,"end_ms":2100,"text":"AI"},
                      {"start_ms":2150,"end_ms":2300,"text":"e"},
                      {"start_ms":2350,"end_ms":2800,"text":"coding."}]},
        ]
    }


def complete_transcription(ws: StudioWorkspace, transcript: dict | None = None):
    data = sample_transcript(ws) if transcript is None else transcript
    with patch("pausio.studio.transcribe_video_local", return_value=data):
        ws.start_job("transcribe")
        for _ in range(250):
            job=ws.snapshot()["job"]
            if job["status"] in {"completed","failed"}:
                if job["status"] != "completed":
                    raise AssertionError(str(job))
                return data
            time.sleep(.02)
    raise AssertionError("Transcription timeout")


def applied_plan(ws: StudioWorkspace) -> None:
    ws.save_plan([
        {"start_ms": 0, "end_ms": 1100},
        {"start_ms": 1500, "end_ms": 3000},
    ])


class RecoveryTests(unittest.TestCase):
    def test_transcript_restores_with_words_model_after_restart_and_edit(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp)/"private"
            ws=imported_workspace(directory)
            try:
                transcript=complete_transcription(ws)
                self.assertEqual(ws.snapshot()["transcript"]["text"],transcript["text"])
                saved=json.loads((directory/STATE_FILE).read_text(encoding="utf-8"))
                self.assertEqual(saved["schema_version"],2)
                self.assertEqual(saved["transcript"]["media_sha256"],ws.media_sha256)
                self.assertNotIn("source",saved["transcript"]["data"])
                self.assertNotIn(str(ws.source),(directory/STATE_FILE).read_text())
                self.assertNotIn("transcript",ws.export_project())
                self.assertNotIn(transcript["text"],json.dumps(ws.export_project()))
                if os.name=="posix":
                    self.assertEqual(stat.S_IMODE((directory/STATE_FILE).stat().st_mode),0o600)
                applied_plan(ws)
                ws.approve_plan()
                self.assertEqual(json.loads((directory/STATE_FILE).read_text())
                                 ["transcript"]["data"]["text"],transcript["text"])
            finally:
                ws.close()
            restored=new_workspace(directory)
            try:
                snap=restored.snapshot()
                self.assertTrue(snap["recovered"])
                self.assertEqual(snap["transcript"]["text"],transcript["text"])
                self.assertEqual(snap["transcript"]["model"],transcript["model"])
                self.assertEqual(snap["transcript"]["segments"][0]["words"],
                                 transcript["segments"][0]["words"])
                with patch("pausio.studio.transcribe_video_local") as rerun:
                    restored.generate_captions({
                        "revision":restored.tape.revision, "style":"social"
                    })
                    rerun.assert_not_called()
                self.assertTrue(restored.snapshot()["captions"])
            finally:
                restored.close()

    def test_v1_session_migrates_to_v2_on_next_autosave(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp)/"private"
            ws=imported_workspace(directory)
            try:
                state=json.loads((directory/STATE_FILE).read_text())
                state["schema_version"]=1
                state.pop("transcript")
                (directory/STATE_FILE).write_text(json.dumps(state),encoding="utf-8")
            finally:
                ws.close()
            restored=new_workspace(directory)
            try:
                self.assertTrue(restored.snapshot()["recovered"])
                self.assertIsNone(restored.snapshot()["transcript"])
                applied_plan(restored)
                upgraded=json.loads((directory/STATE_FILE).read_text())
                self.assertEqual(upgraded["schema_version"],2)
                self.assertIsNone(upgraded["transcript"])
            finally:
                restored.close()

    def test_transcript_is_cleared_with_new_media_and_explicit_delete(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp)/"private"
            ws=imported_workspace(directory)
            try:
                complete_transcription(ws)
                candidate,label=ws.begin_import("new.mp4")
                candidate.write_bytes(b"another example media")
                ws.finish_import(candidate,label,INFO)
                self.assertIsNone(ws.snapshot()["transcript"])
                self.assertIsNone(json.loads((directory/STATE_FILE).read_text())["transcript"])
                complete_transcription(ws)
                ws.clear_session()
                self.assertIsNone(ws.snapshot()["transcript"])
                self.assertFalse((directory/STATE_FILE).exists())
            finally:
                ws.close()
            restored=new_workspace(directory)
            try:
                self.assertIsNone(restored.snapshot()["transcript"])
            finally:
                restored.close()

    def test_failed_transcription_autosave_does_not_expose_unsaved_data(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp)/"private"
            ws=imported_workspace(directory)
            try:
                before=(directory/STATE_FILE).read_bytes()
                with patch.object(ws.store,"save",side_effect=OSError("disk full")):
                    with patch("pausio.studio.transcribe_video_local",
                               return_value=sample_transcript(ws)):
                        ws.start_job("transcribe")
                        for _ in range(250):
                            job=ws.snapshot()["job"]
                            if job["status"] in {"completed","failed"}:break
                            time.sleep(.02)
                self.assertEqual(ws.snapshot()["job"]["status"],"failed")
                self.assertIsNone(ws.snapshot()["transcript"])
                self.assertEqual((directory/STATE_FILE).read_bytes(),before)
            finally:ws.close()

    def test_reopen_after_restart_restores_media_timeline_cursor_and_redo(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / "private"
            ws = imported_workspace(directory)
            try:
                applied_plan(ws)
                first = ws.tape.view.segments[0]
                ws.command({"revision": 1, "type": "segment.update", "payload": {
                    "segment_id": first["id"], "start_ms": 100, "end_ms": 1050
                }})
                ws.approve_plan()
                assert ws.tape.revision == 3
                ws.command({"revision": 3, "type": "history.undo", "payload": {}})
                before = ws.snapshot()
                self.assertFalse(before["approved"])
                self.assertTrue(before["can_redo"])
                self.assertTrue(before["autosaved"])
                self.assertEqual(before["project_revision"], 4)
                source_bytes = ws.source.read_bytes()
                source = ws.source
                self.assertEqual(stat.S_IMODE((directory / STATE_FILE).stat().st_mode), 0o600)
                if os.name == "posix":
                    self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
                self.assertNotIn(str(source), (directory / STATE_FILE).read_text())
            finally:
                ws.close()

            restored = new_workspace(directory)
            try:
                self.assertTrue(restored.snapshot()["recovered"])
                self.assertEqual(restored.snapshot()["editor_segments"], before["editor_segments"])
                self.assertEqual(restored.snapshot()["project_revision"], 4)
                self.assertEqual(restored.snapshot()["history_cursor"], 2)
                self.assertTrue(restored.snapshot()["can_redo"])
                self.assertEqual(restored.source.read_bytes(), source_bytes)
                restored.command({"revision": 4, "type": "history.redo", "payload": {}})
                self.assertTrue(restored.snapshot()["approved"])
                self.assertEqual(restored.snapshot()["project_revision"], 5)
            finally:
                restored.close()

    def test_corrupted_primary_uses_prior_checkpoint_then_repairs_primary(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / "private"
            ws = imported_workspace(directory)
            try:
                applied_plan(ws)  # backup holds state before this edit
                ws.approve_plan()  # backup now holds the valid first edit
                previous = json.loads((directory / BACKUP_FILE).read_text())
                self.assertEqual(previous["project"]["revision"], 1)
                (directory / STATE_FILE).write_text("{broken json", encoding="utf-8")
            finally:
                ws.close()
            restored = new_workspace(directory)
            try:
                self.assertTrue(restored.snapshot()["recovered"])
                self.assertIn("precedente", restored.snapshot()["recovery_warning"])
                self.assertEqual(restored.snapshot()["project_revision"], 1)
                self.assertFalse(restored.snapshot()["approved"])
                repaired = json.loads((directory / STATE_FILE).read_text())
                self.assertEqual(repaired["project"]["revision"], 1)
                restored.approve_plan()
                self.assertEqual(restored.snapshot()["project_revision"], 2)
            finally:
                restored.close()

    def test_disk_write_failure_does_not_commit_memory_or_destroy_previous(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / "private"
            ws = imported_workspace(directory)
            try:
                applied_plan(ws)
                before = ws.snapshot()
                saved = (directory / STATE_FILE).read_bytes()
                with patch.object(ws.store, "_atomic_bytes", side_effect=OSError("disk full")):
                    with self.assertRaises(OSError):
                        ws.command({"revision": 1, "type": "timeline.keep_all", "payload": {}})
                self.assertEqual(ws.snapshot()["editor_segments"], before["editor_segments"])
                self.assertEqual(ws.snapshot()["project_revision"], 1)
                self.assertEqual(saved, (directory / STATE_FILE).read_bytes())
            finally:
                ws.close()
            restored = new_workspace(directory)
            try:
                self.assertEqual(restored.snapshot()["editor_segments"], before["editor_segments"])
            finally:
                restored.close()

    def test_failure_during_new_import_preserves_old_saved_session(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / "private"
            ws = imported_workspace(directory)
            try:
                applied_plan(ws)
                old_source = ws.source
                old_project = ws.snapshot()["plan"]
                candidate, label = ws.begin_import("altro.mp4")
                candidate.write_bytes(b"another private video")
                with patch.object(ws.store, "save", side_effect=OSError("disk full")):
                    with self.assertRaises(OSError):
                        ws.finish_import(candidate, label, INFO)
                ws.abort_import(candidate)
                self.assertEqual(ws.source, old_source)
                self.assertEqual(ws.snapshot()["plan"], old_project)
            finally:
                ws.close()
            restored = new_workspace(directory)
            try:
                self.assertEqual(restored.snapshot()["plan"]["segments"], old_project["segments"])
                cached = sorted(p.name for p in directory.glob("media-*"))
                self.assertEqual(len(cached), 1)  # orphaned incoming media cleaned
            finally:
                restored.close()

    def test_corrupt_saved_file_never_automatically_deletes_private_media(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / "private"
            ws = imported_workspace(directory)
            source = ws.source
            ws.close()
            (directory / STATE_FILE).write_text("{broken json", encoding="utf-8")
            restored = new_workspace(directory)
            try:
                self.assertIsNone(restored.snapshot()["file"])
                self.assertIsNotNone(restored.snapshot()["recovery_warning"])
                self.assertTrue(source.exists())
            finally:
                restored.close()

    def test_explicit_clear_removes_video_and_autosave_and_allows_fresh_session(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / "private"
            ws = imported_workspace(directory)
            try:
                applied_plan(ws)
                self.assertTrue((directory / STATE_FILE).exists())
                ws.clear_session()
                self.assertFalse((directory / STATE_FILE).exists())
                self.assertFalse((directory / BACKUP_FILE).exists())
                self.assertFalse(list(directory.glob("media-*")))
                self.assertIsNone(ws.snapshot()["file"])
            finally:
                ws.close()
            reopened = new_workspace(directory)
            try:
                self.assertIsNone(reopened.snapshot()["file"])
                self.assertFalse(reopened.snapshot()["recovered"])
            finally:
                reopened.close()

    def test_two_processes_cannot_open_same_autosave_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / "private"
            ws = new_workspace(directory)
            try:
                with self.assertRaises(RecoveryError):
                    new_workspace(directory)
            finally:
                ws.close()
            successor = new_workspace(directory)
            successor.close()

    def test_source_fingerprint_tampering_blocks_recovery(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / "private"
            ws = imported_workspace(directory)
            source = ws.source
            ws.close()
            with source.open("ab") as handle:
                handle.write(b"tampered")
            restored = new_workspace(directory)
            try:
                self.assertIsNone(restored.source)
                self.assertIn("SHA-256", restored.snapshot()["recovery_warning"])
                self.assertTrue(source.exists())
            finally:
                restored.close()


if __name__ == "__main__":
    unittest.main()
