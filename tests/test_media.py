import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pausio.domain import Interval
from pausio.media import MediaError, parse_silences, render


class TestMedia(unittest.TestCase):
    def test_silencedetect_parses_start_end_and_end_of_file(self):
        logs = """[silencedetect] silence_start: -0.02
[silencedetect] silence_end: 1.200 | silence_duration: 1.220
[silencedetect] silence_start: 5.25
"""
        self.assertEqual(parse_silences(logs, 6000), [Interval(0, 1200), Interval(5250, 6000)])

    def test_silencedetect_handles_empty_logs(self):
        self.assertEqual(parse_silences("hello\n", 5000), [])

    def test_render_refuses_overwriting_original(self):
        with TemporaryDirectory() as d:
            source = Path(d) / "a.mp4"
            source.touch()
            with self.assertRaises(MediaError):
                render(source, source, (Interval(0, 200),), has_audio=False)

    def test_render_builds_command_without_execution(self):
        with TemporaryDirectory() as d:
            source = Path(d) / "input.mov"
            source.touch()
            with patch("pausio.media.require_binary", return_value="ffmpeg"):
                cmd = render(
                    source, Path(d) / "export.mp4",
                    (Interval(0, 1000), Interval(1800, 2500)),
                    has_audio=True, dry_run=True,
                )
            filters = cmd[cmd.index("-filter_complex") + 1]
            self.assertIn("concat=n=2:v=1:a=1", filters)
            self.assertIn("atrim=start=1.800:end=2.500", filters)
            self.assertIn("pad=1080:1920", filters)


if __name__ == "__main__":
    unittest.main()
