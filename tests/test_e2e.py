"""Small real-media smoke test; skipped when local FFmpeg tools are absent."""

import json
import shutil
import subprocess
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from pausio.cli import main
from pausio.media import probe


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg not installed")
class TestRealMedia(unittest.TestCase):
    def test_end_to_end_tiny_video_with_audio(self):
        with TemporaryDirectory() as td:
            d = Path(td)
            source, plan, output = d / "clip.mp4", d / "plan.json", d / "export.mp4"
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "color=c=navy:s=180x320:r=15:d=2.2",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=2.2",
                "-shortest", "-c:v", "mpeg4", "-c:a", "aac", str(source),
            ], check=True, timeout=60)
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["plan", str(source), "-o", str(plan)]), 0)
            data = json.loads(plan.read_text(encoding="utf-8"))
            self.assertEqual(data["schema_version"], 1)
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["render", str(plan), "-o", str(output)]), 0)
            result = probe(output)
            self.assertEqual((result.width, result.height), (1080, 1920))
            self.assertTrue(result.has_audio)
            self.assertGreater(result.duration_ms, 1000)
            self.assertTrue(output.stat().st_size > 1000)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg not installed")
class TestRealMediaSilent(unittest.TestCase):
    def test_end_to_end_video_without_audio(self):
        with TemporaryDirectory() as td:
            d = Path(td)
            source, plan, output = d / "noaudio.mp4", d / "plan.json", d / "export.mp4"
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "color=c=blue:s=90x160:r=12:d=1.2",
                "-c:v", "mpeg4", str(source),
            ], check=True, timeout=60)
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["plan", str(source), "-o", str(plan)]), 0)
                self.assertEqual(main(["render", str(plan), "-o", str(output)]), 0)
            self.assertFalse(probe(output).has_audio)
            self.assertEqual((probe(output).width, probe(output).height), (1080, 1920))
