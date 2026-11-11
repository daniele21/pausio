"""Audio FX replay, validation and deterministic rendering contracts."""

import copy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pausio.domain import Interval
from pausio.media import MediaError, render
from pausio.project_commands import ProjectTape, ProjectFormatError


def source_media():
    return {
        "filename": "original.mp4", "sha256": "a" * 64,
        "duration_ms": 10000, "has_audio": True,
    }


def fx_clip():
    return {
        "id": "b" * 32, "asset_sha256": "c" * 64,
        "filename": "my riser.wav", "start_ms": 3000,
        "duration_ms": 2000, "gain_db": -12,
    }


class AudioFxReplayTests(unittest.TestCase):
    def test_add_edit_remove_undo_redo_and_json_roundtrip(self):
        clip = fx_clip()
        first = ProjectTape(source_media())
        added = first.append("audio.add", {"clip": clip})
        self.assertEqual(added.view.audio_clips[0], clip)
        changed = added.append("audio.update", {
            "clip_id": clip["id"], "start_ms": 1500, "gain_db": -18,
        })
        self.assertEqual(changed.view.audio_clips[0]["start_ms"], 1500)
        self.assertEqual(ProjectTape.from_dict(changed.as_dict()).view, changed.view)
        self.assertEqual(changed.undo().view.audio_clips[0], clip)
        self.assertEqual(changed.undo().redo().view, changed.view)
        removed = changed.append("audio.remove", {"clip_id": clip["id"]})
        self.assertEqual(removed.view.audio_clips, ())
        self.assertEqual(removed.undo().view.audio_clips[0]["gain_db"], -18)

    def test_reject_untrusted_asset_paths_and_invalid_properties(self):
        good = fx_clip()
        for edit in (
            {"filename": "../bad.wav"},
            {"filename": "not-audio.txt"},
            {"asset_sha256": "z" * 64},
            {"start_ms": True},
            {"start_ms": 10000},
            {"duration_ms": 0},
            {"duration_ms": 180001},
            {"gain_db": 15},
            {"gain_db": 1.5},
        ):
            with self.subTest(edit=edit):
                with self.assertRaises(ProjectFormatError):
                    ProjectTape(source_media()).append("audio.add", {"clip": {**good, **edit}})
        with self.assertRaises(ProjectFormatError):
            ProjectTape(source_media()).append("audio.remove", {"clip_id": "d" * 32})

    def test_approval_is_invalidated_by_fx_edit(self):
        tape = ProjectTape(source_media()).append("timeline.keep_all", {})
        tape = tape.append("timeline.approve", {})
        self.assertTrue(tape.view.approved)
        tape = tape.append("audio.add", {"clip": fx_clip()})
        self.assertFalse(tape.view.approved)
        self.assertTrue(tape.undo().view.approved)


class AudioFxRenderTests(unittest.TestCase):
    def test_preview_and_final_use_same_fx_mix(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "video.mp4"
            fx = Path(directory) / "sound.wav"
            source.touch()
            fx.touch()
            effects = [(fx, fx_clip())]
            with patch("pausio.media.require_binary", return_value="ffmpeg"):
                standard = render(
                    source, Path(directory) / "final.mp4",
                    (Interval(0, 2500), Interval(3000, 7500)),
                    has_audio=True, dry_run=True, audio_fx=effects,
                )
                preview = render(
                    source, Path(directory) / "preview.mp4",
                    (Interval(0, 2500), Interval(3000, 7500)),
                    has_audio=True, dry_run=True, audio_fx=effects, size=(540, 960),
                )
            std = standard[standard.index("-filter_complex") + 1]
            prv = preview[preview.index("-filter_complex") + 1]
            self.assertIn("adelay=3000:all=1", std)
            self.assertIn("volume=-12dB", std)
            self.assertIn("amix=inputs=2", std)
            self.assertIn("[outa]", std)
            self.assertIn(str(fx), standard)
            self.assertEqual(std.replace("1080:1920", "540:960"), prv)
            self.assertIn("[outa]", standard)

    def test_missing_fx_file_is_rejected(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "original.mp4"
            source.touch()
            with self.assertRaises(MediaError):
                render(source, Path(directory) / "result.mp4",
                       (Interval(0, 1000),), has_audio=True, dry_run=True,
                       audio_fx=[(Path(directory) / "gone.mp3", fx_clip())])


if __name__ == "__main__":
    unittest.main()
