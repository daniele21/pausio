"""End-to-end deterministic local video B-roll: commands, rights and render."""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from pausio.domain import Interval
from pausio.media import MediaError, probe, render
from pausio.project_commands import ProjectFormatError, ProjectTape
from pausio.video_broll import validate_video_broll, validate_video_brolls


class VideoBrollTests(unittest.TestCase):
    def setUp(self):
        self.media = {"filename": "speech.mp4", "sha256": "a" * 64,
                      "duration_ms": 3000, "has_audio": True}
        self.base = ProjectTape(self.media).append("timeline.keep_all", {})
        self.clip = {"id": "b" * 32, "asset_sha256": "c" * 64,
                     "filename": "roll.mp4", "start_ms": 700,
                     "duration_ms": 1200, "media_in_ms": 0,
                     "mode": "fullscreen", "x_pct": 50,
                     "y_pct": 20, "width_pct": 55}

    def test_reversible_portable_clip_and_legacy_v10(self):
        tape = self.base.append("video.broll.add", {"video": self.clip})
        self.assertEqual(tape.as_dict()["schema_version"], 14)
        self.assertEqual(tape.view.video_broll, (self.clip,))
        self.assertEqual(ProjectTape.from_dict(tape.as_dict()).view.video_broll,
                         tape.view.video_broll)
        self.assertEqual(tape.undo().view.video_broll, ())
        self.assertEqual(tape.undo().redo().view.video_broll, (self.clip,))
        updated = {**self.clip, "mode": "pip", "media_in_ms": 200}
        tape = tape.append("video.broll.update", {"video": updated})
        self.assertEqual(tape.view.video_broll[0], updated)
        self.assertFalse(tape.view.approved)
        tape = tape.append("video.broll.remove", {"video_id": self.clip["id"]})
        self.assertFalse(tape.view.video_broll)
        old = {**self.base.as_dict(), "schema_version": 10}
        self.assertEqual(ProjectTape.from_dict(old).view.video_broll, ())

    def test_invalid_fields_and_overlaps_rejected_before_side_effects(self):
        invalid = (
            {"asset_sha256": "wrong"}, {"id": "bad"}, {"filename": "../bad.mp4"},
            {"filename": "https://host/roll.mp4"}, {"filename": "bad.svg"},
            {"mode": "shell"}, {"mode": []}, {"start_ms": True}, {"start_ms": 2900},
            {"duration_ms": 20_001}, {"media_in_ms": -1},
            {"x_pct": -1}, {"width_pct": 100}, {"user_filter": "eval=abc"},
        )
        for change in invalid:
            with self.subTest(change=change), self.assertRaises(ProjectFormatError):
                self.base.append("video.broll.add", {"video": {**self.clip, **change}})
        with self.assertRaises(ProjectFormatError):
            self.base.append("video.broll.remove", {"video_id": self.clip["id"]})
        initial = self.base.append("video.broll.add", {"video": self.clip})
        duplicate = {**self.clip, "id": "d" * 32, "start_ms": 900}
        with self.assertRaises(ProjectFormatError):
            initial.append("video.broll.add", {"video": duplicate})
        self.assertEqual(len(initial.view.video_broll), 1)
        validate_video_broll(self.clip, 3000)
        validate_video_brolls([self.clip], 3000)

    def test_shortened_output_does_not_silently_retime_video(self):
        tape = self.base.append("video.broll.add", {"video": self.clip})
        segment = tape.view.segments[0]["id"]
        with self.assertRaises(ProjectFormatError):
            tape.append("segment.update", {
                "segment_id": segment, "start_ms": 0, "end_ms": 800
            })

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                         "FFmpeg/FFprobe required")
    def test_fullscreen_video_changes_only_its_window_and_keeps_speech_audio(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.mp4"
            cutaway = root / "cutaway.mp4"
            plain = root / "plain.mp4"
            result = root / "with-broll.mp4"
            subprocess.run([
                "ffmpeg", "-hide_banner", "-nostdin", "-v", "error", "-y",
                "-f", "lavfi", "-i", "color=c=blue:s=180x320:r=30:d=3",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=3",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-shortest", str(source)
            ], check=True, timeout=50)
            subprocess.run([
                "ffmpeg", "-hide_banner", "-nostdin", "-v", "error", "-y",
                "-f", "lavfi", "-i", "color=c=red:s=180x320:r=30:d=2",
                "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=48000:duration=2",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-shortest", str(cutaway)
            ], check=True, timeout=50)
            sha = hashlib.sha256(cutaway.read_bytes()).hexdigest()
            clip = {**self.clip, "asset_sha256": sha,
                    "start_ms": 800, "duration_ms": 1200}
            keep = (Interval(0, 3000),)
            render(source, plain, keep, has_audio=True, size=(540, 960))
            render(source, result, keep, has_audio=True, size=(540, 960),
                   video_broll=[(cutaway, clip)])
            self.assertTrue(probe(result).has_audio)
            self.assertTrue(2800 <= probe(result).duration_ms <= 3200)

            def pixel_at(path: Path, when: float) -> tuple[int, int, int]:
                out = subprocess.run([
                    "ffmpeg", "-hide_banner", "-nostdin", "-v", "error",
                    "-ss", str(when), "-i", str(path),
                    "-frames:v", "1", "-vf", "scale=1:1",
                    "-pix_fmt", "rgb24", "-f", "rawvideo", "-"
                ], check=True, capture_output=True, timeout=30).stdout
                return tuple(out[:3])

            before = pixel_at(result, 0.3)
            during = pixel_at(result, 1.1)
            after = pixel_at(result, 2.5)
            self.assertGreater(before[2], before[0] + 80)
            self.assertGreater(during[0], during[2] + 80)
            self.assertGreater(after[2], after[0] + 80)
            with self.assertRaises(MediaError):
                render(source, root / "bad.mp4", keep, has_audio=True,
                       video_broll=[(cutaway, {**clip, "asset_sha256": "0" * 64})],
                       size=(540, 960))
