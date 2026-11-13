"""Small range-render tests: same graph, no duplicate editing engine."""
import shutil
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pausio.domain import Interval
from pausio.media import MediaError, probe, render


class PreviewWindowTests(unittest.TestCase):
    def test_output_time_validation_rejects_bad_windows(self):
        with TemporaryDirectory() as td:
            source = Path(td) / "source.mp4"
            source.touch()
            with patch("pausio.media.require_binary", return_value="ffmpeg"):
                for window in (("0", 500), (True, 500), (0, True), (-1, 500),
                               (0, 249), (0, 10001), (1600, 500), [0, 500]):
                    with self.subTest(window=window), self.assertRaises(MediaError):
                        render(source, Path(td) / "clip.mp4",
                               (Interval(0, 2000),), has_audio=False,
                               output_window=window, dry_run=True)

    def test_window_uses_same_graph_with_audio_after_composition(self):
        with TemporaryDirectory() as td:
            source = Path(td) / "source.mp4"
            source.touch()
            with patch("pausio.media.require_binary", return_value="ffmpeg"):
                cmd = render(source, Path(td) / "preview-range.mp4",
                             (Interval(100, 900), Interval(1500, 2400)),
                             has_audio=True, size=(540, 960), dry_run=True,
                             output_window=(700, 750))
            graph = cmd[cmd.index("-filter_complex")+1]
            self.assertIn("trim=start=0.100:end=0.900", graph)
            self.assertIn("atrim=start=1.500:end=2.400", graph)
            self.assertIn("[outv]trim=start=0.700:end=1.450,setpts=PTS-STARTPTS[rangev]", graph)
            self.assertIn("[joineda]atrim=start=0.700:end=1.450,asetpts=PTS-STARTPTS[rangea]", graph)
            self.assertIn("[rangev]", cmd)
            self.assertIn("[rangea]", cmd)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                         "FFmpeg/FFprobe not installed")
    def test_real_range_crosses_keep_cut_with_audio(self):
        with TemporaryDirectory() as td:
            source = Path(td) / "source.mp4"
            output = Path(td) / "range.mp4"
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "color=c=navy:s=180x320:r=30:d=2.6",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=2.6",
                "-shortest", "-c:v", "mpeg4", "-c:a", "aac", str(source),
            ], check=True, timeout=60)
            render(source, output, (Interval(0, 800), Interval(1300, 2400)),
                   has_audio=True, size=(540, 960), output_window=(650, 900))
            info = probe(output)
            self.assertEqual((info.width, info.height), (540, 960))
            self.assertTrue(info.has_audio)
            self.assertTrue(750 <= info.duration_ms <= 1050, info.duration_ms)
            self.assertGreater(output.stat().st_size, 1000)
