import unittest
import shutil
import subprocess
from array import array
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pausio.domain import Interval
from pausio.media import MediaError, ffmpeg_has_filter, parse_silences, render, waveform_envelope


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

    def test_ffmpeg_has_filter_uses_actual_binary_listing(self):
        from subprocess import CompletedProcess
        listing = """
Filters:
  T.. = Timeline support
  .S. = Slice threading
  ..C = Command support
 ... ass               V->V       Render ASS subtitles
 ... subtitles         V->V       Render text subtitles
"""
        with (
            patch("pausio.media.require_binary", return_value="/tmp/ffmpeg"),
            patch("pausio.media._run", return_value=CompletedProcess([], 0, listing, "")) as run,
        ):
            self.assertTrue(ffmpeg_has_filter("ass"))
            self.assertTrue(ffmpeg_has_filter("subtitles"))
            self.assertFalse(ffmpeg_has_filter("nonexistent"))
            self.assertEqual(run.call_args.args[0][0], "/tmp/ffmpeg")
            self.assertIn("-filters", run.call_args.args[0])

    def test_render_captions_fails_early_without_libass(self):
        with TemporaryDirectory() as d:
            source=Path(d)/"input.mov"
            source.touch()
            cues=[{"id":"a"*32,"start_ms":200,"end_ms":900,"text":"CIAO"}]
            with (
                patch("pausio.media.ffmpeg_has_filter", return_value=False),
                patch("pausio.media.require_binary", return_value="/opt/homebrew/bin/ffmpeg"),
            ):
                with self.assertRaisesRegex(MediaError, "ffmpeg-full"):
                    render(source,Path(d)/"output.mp4",
                           (Interval(0,1000),),has_audio=True,captions=cues)
                # Dry run may still show the command without executing FFmpeg.
                cmd=render(source,Path(d)/"preview.mp4",
                           (Interval(0,1000),),has_audio=True,dry_run=True,captions=cues)
                self.assertIn("ass=filename=", cmd[cmd.index("-filter_complex")+1])
                render(source,Path(d)/"without.mp4",
                       (Interval(0,1000),),has_audio=True,dry_run=True)

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

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg unavailable")
    def test_exported_mp4_contains_audible_riser_only_at_scheduled_time(self):
        """Detect real PCM samples, not just an MP4 file with an audio stream."""
        with TemporaryDirectory() as d:
            root=Path(d)
            original=root/"silent-voice.mp4"
            riser=root/"riser.wav"
            output=root/"mixed-preview.mp4"
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                "-f", "lavfi", "-i", "color=c=black:s=160x284:r=15:d=2",
                "-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono",
                "-t", "2", "-shortest", "-c:v", "mpeg4", "-c:a", "aac", str(original),
            ], check=True, timeout=40)
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                "-f", "lavfi", "-i", "sine=frequency=700:duration=0.35",
                "-c:a", "pcm_s16le", str(riser),
            ], check=True, timeout=40)
            clip={
                "id": "a"*32, "asset_sha256": "b"*64, "filename": "riser.wav",
                "start_ms": 900, "duration_ms": 350, "gain_db": -6,
            }
            render(
                original, output, (Interval(0, 2000),),
                has_audio=True, size=(540, 960),
                audio_fx=[(riser, clip)],
            )

            def peak(at_seconds: float, path: Path = output) -> int:
                result=subprocess.run([
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
                    "-ss", str(at_seconds), "-i", str(path),
                    "-t", "0.12", "-map", "0:a:0", "-ac", "1", "-ar", "16000",
                    "-f", "s16le", "-",
                ], capture_output=True, check=True, timeout=30)
                samples=array("h")
                samples.frombytes(result.stdout)
                return max((abs(v) for v in samples),default=0)

            self.assertLess(peak(0.35), 50, "No sound should play before the riser")
            self.assertGreater(peak(1.0), 500, "Imported FX must be audible in exported MP4")
            self.assertLess(peak(1.6), 50, "FX must stop after its duration")

            quiet=root/"quiet-fx.mp4"
            render(original,quiet,(Interval(0,2000),),has_audio=True,
                   size=(540,960),audio_fx=[(riser,clip)],audio_mix={
                       "voice_gain_db":0,"voice_muted":False,
                       "fx_gain_db":-12,"fx_muted":False,
                   })
            muted=root/"muted-fx.mp4"
            render(original,muted,(Interval(0,2000),),has_audio=True,
                   size=(540,960),audio_fx=[(riser,clip)],audio_mix={
                       "voice_gain_db":0,"voice_muted":False,
                       "fx_gain_db":0,"fx_muted":True,
                   })
            self.assertLess(peak(1.0, quiet), peak(1.0)/2,
                            "Lowering FX bus should reduce decoded PCM amplitude")
            self.assertLess(peak(1.0, muted), 50,
                            "Muting FX bus should remove effect from exported MP4")

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg unavailable")
    def test_voice_track_attenuation_and_mute_affect_rendered_pcm(self):
        with TemporaryDirectory() as d:
            root=Path(d)
            original=root/"speaker.mp4"
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                "-f", "lavfi", "-i", "color=c=black:s=160x284:r=15:d=1",
                "-f", "lavfi", "-i", "sine=frequency=450:duration=1",
                "-shortest", "-c:v", "mpeg4", "-c:a", "aac", str(original),
            ],check=True,timeout=40)
            standard={"voice_gain_db":0,"voice_muted":False,
                      "fx_gain_db":0,"fx_muted":False}
            quiet=root/"quiet.mp4"
            muted=root/"muted.mp4"
            render(original,quiet,(Interval(0,1000),),has_audio=True,
                   size=(540,960),audio_mix={**standard,"voice_gain_db":-12})
            render(original,muted,(Interval(0,1000),),has_audio=True,
                   size=(540,960),audio_mix={**standard,"voice_muted":True})
            def peak(path):
                result=subprocess.run([
                    "ffmpeg","-hide_banner","-loglevel","error","-nostdin",
                    "-ss","0.3","-i",str(path),"-t","0.15","-map","0:a:0",
                    "-ac","1","-ar","16000","-f","s16le","-",
                ],capture_output=True,check=True,timeout=30)
                samples=array("h");samples.frombytes(result.stdout)
                return max((abs(v) for v in samples),default=0)
            self.assertGreater(peak(original),500)
            self.assertLess(peak(quiet),peak(original)/2)
            self.assertLess(peak(muted),50)

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
