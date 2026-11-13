"""Synthetic FFmpeg verification for source-timed punch and slow push."""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from pausio.domain import Interval
from pausio.media import MediaError, render, probe
from pausio.visual_fx import prepare_motion_fx, motion_filter


def entry(start=300, end=1200, kind="punch", amount=118):
    return {
        "segment_index": 0, "start_ms": start, "end_ms": end,
        "kind": kind, "start_scale_pct": amount if kind=="punch" else 100,
        "end_scale_pct": amount, "anchor_x_pct": 50, "anchor_y_pct": 50,
    }


class VisualFxRendererTests(unittest.TestCase):
    def test_source_keep_and_unsafe_parameters_are_rejected(self):
        s=(Interval(0,1500),)
        for variation in (
            {"end_ms":2000}, {"start_scale_pct":900, "end_scale_pct":900},
            {"kind":"zoompan=z=eval(system())"},
            {"segment_index":99}, {"anchor_y_pct":-1},
            {"start_ms":True}, {"unknown":"filters"},
        ):
            with self.subTest(variation=variation), self.assertRaises(ValueError):
                prepare_motion_fx(s,[{**entry(),**variation}])
        self.assertEqual(prepare_motion_fx(s,None),{})

    def test_escaped_zoompan_keyframes_are_deterministic(self):
        groups=prepare_motion_fx((Interval(0,1500),),[
            entry(kind="slow_push",start=300,end=1200,amount=121)
        ])
        expr=motion_filter(groups[0],0,(540,960))
        self.assertIn("zoompan=z=",expr)
        self.assertIn("between(on\\,9\\,35)",expr)
        self.assertIn("format=yuv420p",expr)
        self.assertEqual(expr,motion_filter(groups[0],0,(540,960)))

    def test_eased_zoom_and_three_step_ratchet_are_numeric_only(self):
        for kind,token in (("ease_push","3-2*"),("ratchet","floor(3*")):
            with self.subTest(kind=kind):
                prepared=prepare_motion_fx(
                    (Interval(0,1800),),
                    [entry(start=300,end=1600,kind=kind,amount=124)]
                )
                graph=motion_filter(prepared[0],0,(540,960))
                self.assertIn(token,graph)
                self.assertNotIn("system",graph)
                self.assertIn("format=yuv420p",graph)

    def test_pulse_and_sweep_safe_bounded_motion_curves(self):
        for kind, token in (("pulse", "if(lt("), ("sweep", "0.5+(")):
            with self.subTest(kind=kind):
                fx=entry(start=250,end=2200,kind=kind,amount=122)
                if kind=="sweep":
                    fx["anchor_x_pct"]=68
                    fx["anchor_y_pct"]=39
                checked=prepare_motion_fx((Interval(0,2400),),[fx])
                graph=motion_filter(checked[0],0,(540,960))
                self.assertIn(token,graph)
                self.assertIn("zoompan=z=",graph)
                self.assertEqual(graph,motion_filter(checked[0],0,(540,960)))
        for kind,duration in (("pulse",850),("sweep",1250)):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                prepare_motion_fx((Interval(0,2500),),[
                    entry(start=200,end=200+duration,kind=kind,amount=120)])

    def test_overlapping_events_rejected(self):
        s=(Interval(0,3000),)
        with self.assertRaises(ValueError):
            prepare_motion_fx(s,[entry(),entry(start=800,end=1700)])

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                         "FFmpeg and FFprobe required")
    def test_real_preview_zoom_changes_pixels_and_preserves_mp4_geometry(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/"input.mp4"
            subprocess.run([
                "ffmpeg","-hide_banner","-nostdin","-v","error","-y",
                "-f","lavfi","-i","testsrc2=size=180x320:rate=30:duration=1.5",
                "-c:v","libx264","-pix_fmt","yuv420p",str(source)
            ],check=True,timeout=40)
            standard=root/"plain.mp4";zoomed=root/"motion.mp4"
            keep=(Interval(0,1500),)
            render(source,standard,keep,has_audio=False,size=(540,960))
            render(source,zoomed,keep,has_audio=False,size=(540,960),
                   video_fx=[entry()])
            info=probe(zoomed)
            self.assertEqual((info.width,info.height),(540,960))
            self.assertFalse(info.has_audio)
            def frame(path,at):
                result=subprocess.run([
                    "ffmpeg","-hide_banner","-nostdin","-v","error",
                    "-ss",str(at),"-i",str(path),"-frames:v","1",
                    "-f","image2pipe","-vcodec","ppm","-"
                ],capture_output=True,check=True,timeout=30)
                return hashlib.sha256(result.stdout).hexdigest()
            # Earlier than the effect, frames are approximately identical.
            # Within the punch window, the output is visibly re-cropped.
            self.assertNotEqual(frame(standard,0.7),frame(zoomed,0.7))

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                         "FFmpeg and FFprobe required")
    def test_pulse_and_sweep_render_actual_video_without_changing_duration(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/"source.mp4"
            subprocess.run([
                "ffmpeg","-hide_banner","-nostdin","-v","error","-y",
                "-f","lavfi","-i","testsrc2=size=180x320:rate=30:duration=2.5",
                "-c:v","libx264","-pix_fmt","yuv420p",str(source),
            ],check=True,timeout=40)
            for kind in ("pulse","sweep"):
                with self.subTest(kind=kind):
                    fx=entry(start=250,end=2100,kind=kind,amount=120)
                    if kind=="sweep":
                        fx["anchor_x_pct"]=65
                        fx["anchor_y_pct"]=40
                    target=Path(d)/(kind+".mp4")
                    render(source,target,(Interval(0,2500),),has_audio=False,
                           size=(540,960),video_fx=[fx])
                    info=probe(target)
                    self.assertEqual((info.width,info.height),(540,960))
                    self.assertTrue(2250<=info.duration_ms<=2700)
                    self.assertFalse(info.has_audio)

    @unittest.skipUnless(shutil.which("ffmpeg"),"ffmpeg required")
    def test_dry_run_effect_filter_precedes_joined_caption_pipeline(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/"video.mp4";source.touch()
            cmd=render(source,Path(d)/"out.mp4",(Interval(0,1500),),
                       has_audio=False,size=(540,960),dry_run=True,
                       video_fx=[entry(kind="slow_push")])
            graph=cmd[cmd.index("-filter_complex")+1]
            self.assertIn("zoompan=z=",graph)
            self.assertLess(graph.index("zoompan="),graph.index("concat=n=1"))


if __name__=="__main__":
    unittest.main()
