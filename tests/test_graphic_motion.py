"""Source-bound video graphics motion: independent in/out, safety and render."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from pausio.domain import Interval
from pausio.graphic_motion import validate_motion
from pausio.graphic_overlays import compose_graphics_ass
from pausio.media import render, probe
from pausio.project_commands import ProjectFormatError, ProjectTape


class GraphicMotionTests(unittest.TestCase):
    def setUp(self):
        self.tape = ProjectTape({
            "filename": "clip.mp4", "sha256": "a" * 64,
            "duration_ms": 4000, "has_audio": True,
        }).append("timeline.keep_all", {})
        self.segment = self.tape.view.segments[0]["id"]
        self.graphic = {
            "id": "b" * 32, "segment_id": self.segment,
            "start_ms": 600, "end_ms": 2800,
            "text": "1.379 segreti", "kind": "stat", "animation": "fade",
            "x_pct": 50, "y_pct": 25, "font_size": 72, "color": "#FFE08A",
        }
        self.motion = {
            "enter": "slide_up", "exit": "slide_right",
            "enter_ms": 300, "exit_ms": 220,
        }

    def test_v13_replay_undo_and_legacy_motion_untouched(self):
        base = self.tape.append("graphic.overlay.add", {"graphic": self.graphic})
        self.assertEqual(base.as_dict()["schema_version"], 15)
        self.assertNotIn("motion", base.view.graphic_overlays[0])
        enhanced = {**self.graphic, "motion": self.motion}
        tape = base.append("graphic.overlay.update", {"graphic": enhanced})
        self.assertEqual(tape.view.graphic_overlays[0]["motion"], self.motion)
        self.assertEqual(tape.undo().view.graphic_overlays[0], self.graphic)
        self.assertEqual(tape.undo().redo().view.graphic_overlays[0], enhanced)
        self.assertEqual(ProjectTape.from_dict(tape.as_dict()).view.graphic_overlays,
                         tape.view.graphic_overlays)
        old = {**base.as_dict(), "schema_version": 12}
        self.assertEqual(ProjectTape.from_dict(old).view.graphic_overlays,
                         base.view.graphic_overlays)

    def test_invalid_timing_keys_and_script_pieces_are_rejected(self):
        invalid = [
            {"enter": "execute"}, {"enter": []},
            {"exit": "jump"}, {"exit": False},
            {"enter_ms": True}, {"exit_ms": -1},
            {"enter_ms": 900}, {"exit_ms": 805},
            {"extra": "arbitrary \\move"}, {"enter_ms": "200"},
        ]
        for change in invalid:
            with self.subTest(change=change), self.assertRaises(ProjectFormatError):
                self.tape.append("graphic.overlay.add", {
                    "graphic": {**self.graphic, "motion": {**self.motion, **change}}
                })
        with self.assertRaises(ProjectFormatError):
            self.tape.append("graphic.overlay.add", {
                "graphic": {**self.graphic, "motion": {
                    "enter": "fade", "exit": "none", "enter_ms": 0,
                    "exit_ms": 0
                }}
            })
        with self.assertRaises(ProjectFormatError):
            self.tape.append("graphic.overlay.add", {
                "graphic": {**self.graphic, "motion": {
                    "enter": "fade", "exit": "fade",
                    "enter_ms": 800, "exit_ms": 800
                }, "end_ms": 2100}
            })
        self.assertFalse(self.tape.view.graphic_overlays)

    def test_all_motion_modes_generate_three_nonoverlapping_events(self):
        for entry in ("fade", "pop", "slide_up", "slide_left"):
            for leave in ("fade", "shrink", "slide_down", "slide_right"):
                with self.subTest(entry=entry, leave=leave):
                    item = {**self.graphic, "motion": {
                        "enter": entry, "exit": leave,
                        "enter_ms": 260, "exit_ms": 200,
                    }}
                    ass = compose_graphics_ass([], [item])
                    self.assertEqual(ass.count("Dialogue: 1,"), 3)
                    self.assertIn("0:00:00.60,0:00:00.86", ass)
                    self.assertIn("0:00:00.86,0:00:02.60", ass)
                    self.assertIn("0:00:02.60,0:00:02.80", ass)
                    self.assertIn("1.379 segreti", ass)
                    self.assertNotIn("\\blur", ass)
        item = {**self.graphic, "motion": {
            "enter": "none", "exit": "none", "enter_ms": 0, "exit_ms": 0}}
        ass = compose_graphics_ass([], [item])
        self.assertEqual(ass.count("Dialogue: 1,"), 1)
        self.assertIn("0:00:00.60,0:00:02.80", ass)

    def test_remap_keeps_output_clock_and_sanitizes_text(self):
        item = {**self.graphic, "text": r"segreti {\blur10}",
                "motion": self.motion}
        ass = compose_graphics_ass([], [item])
        self.assertNotIn(r"\blur10", ass)
        self.assertNotIn("1.379", ass)
        self.assertIn("segreti blur10", ass)
        validate_motion(self.motion, 2200)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                         "FFmpeg/FFprobe required")
    def test_one_real_libass_preview_keeps_sound_and_duration(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, output = root / "source.mp4", root / "motion.mp4"
            subprocess.run([
                "ffmpeg", "-hide_banner", "-nostdin", "-v", "error", "-y",
                "-f", "lavfi", "-i", "color=c=black:s=180x320:r=30:d=4",
                "-f", "lavfi", "-i",
                "sine=frequency=440:sample_rate=48000:duration=4",
                "-c:v", "mpeg4", "-c:a", "aac", "-shortest", str(source)
            ], timeout=50, check=True)
            graphic = {**self.graphic, "motion": self.motion}
            render(source, output, (Interval(0, 4000),), has_audio=True,
                   graphic_overlays=[graphic], size=(540, 960))
            self.assertTrue(probe(output).has_audio)
            self.assertTrue(3900 <= probe(output).duration_ms <= 4100)
            self.assertGreater(output.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
