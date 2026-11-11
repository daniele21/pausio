import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pausio.domain import Interval
from pausio.media import MediaError, parse_silences, render, waveform_envelope


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

    def test_waveform_silent_source_needs_no_ffmpeg(self):
        self.assertEqual(waveform_envelope(Path("/no-file"), 1000, has_audio=False), [])

    def test_waveform_guards_unbounded_media_duration_and_bin_counts(self):
        with self.assertRaises(MediaError):
            waveform_envelope(Path("/no-file"), 1_800_000, has_audio=True)
        with self.assertRaises(ValueError):
            waveform_envelope(Path("/no-file"), 1000, has_audio=True, bins=2000)

    def test_low_resolution_preview_uses_same_cut_filter_graph(self):
        with TemporaryDirectory() as d:
            source = Path(d) / "input.mov"
            source.touch()
            with patch("pausio.media.require_binary", return_value="ffmpeg"):
                normal = render(
                    source, Path(d) / "final.mp4",
                    (Interval(100, 1200), Interval(1700, 2500)), has_audio=True,
                    dry_run=True,
                )
                preview = render(
                    source, Path(d) / "preview.mp4",
                    (Interval(100, 1200), Interval(1700, 2500)), has_audio=True,
                    dry_run=True, size=(540, 960),
                )
            original_filter = normal[normal.index("-filter_complex") + 1]
            draft_filter = preview[preview.index("-filter_complex") + 1]
            self.assertIn("trim=start=0.100:end=1.200", draft_filter)
            self.assertIn("atrim=start=1.700:end=2.500", draft_filter)
            self.assertIn("pad=540:960", draft_filter)
            self.assertIn("pad=1080:1920", original_filter)
            self.assertEqual(
                original_filter.split(";")[:-1], draft_filter.split(";")[:-1]
            )

    def test_render_burns_ass_captions_only_when_requested(self):
        with TemporaryDirectory() as d:
            source=Path(d)/"input.mov"
            source.touch()
            cues=[{"id":"a"*32,"start_ms":200,"end_ms":900,"text":"CIAO"}]
            with patch("pausio.media.require_binary",return_value="ffmpeg"):
                with_captions=render(source,Path(d)/"out.mp4",
                    (Interval(0,1000),),has_audio=True,dry_run=True,captions=cues)
                without=render(source,Path(d)/"no.mp4",
                    (Interval(0,1000),),has_audio=True,dry_run=True)
            self.assertIn("ass=filename=",with_captions[with_captions.index("-filter_complex")+1])
            self.assertNotIn("ass=filename=",without[without.index("-filter_complex")+1])

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
