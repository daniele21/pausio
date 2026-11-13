"""Safe source-time transitions: no overlapping syllables, no inventing frames."""
from __future__ import annotations
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from pausio.domain import Interval
from pausio.media import render,probe
from pausio.visual_transitions import compile_dips


def cut(dur=300):
    return {"boundary_index":0,"kind":"dip_black","duration_ms":dur}

class TransitionTests(unittest.TestCase):
    def test_boundary_validation_and_no_timing_shift(self):
        clips=(Interval(0,1500),Interval(2500,4000))
        got=compile_dips(clips,[cut()])
        self.assertIn("fade=t=out",got[0][0])
        self.assertIn("fade=t=in",got[1][0])
        for change in (
            {"boundary_index":-1},
            {"boundary_index":True},
            {"boundary_index":2},
            {"duration_ms":800},
            {"duration_ms":150},
            {"kind":"xfade"},
            {"eval":"system()"},
        ):
            with self.subTest(change=change),self.assertRaises(ValueError):
                compile_dips(clips,[{**cut(),**change}])
        self.assertEqual(compile_dips(clips,[]),{})

    def test_missing_handles_are_rejected(self):
        for pair in (
            (Interval(0,999),Interval(1400,3500)),
            (Interval(0,3500),Interval(3600,4700)),
        ):
            with self.assertRaises(ValueError):
                compile_dips(pair,[cut()])
        with self.assertRaises(ValueError):
            compile_dips((Interval(0,5000),),[cut()])

    def test_duplicate_and_dense_dips_rejected(self):
        keep=(Interval(0,2000),Interval(3000,5000),Interval(7000,9000))
        with self.assertRaises(ValueError):
            compile_dips(keep,[cut(),cut()])
        with self.assertRaises(ValueError):
            compile_dips(keep,[cut(600),
                {"boundary_index":1,"kind":"dip_black","duration_ms":600}])

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                         "FFmpeg and FFprobe required")
    def test_render_black_dip_between_real_cuts(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            source=root/"source.mp4";rendered=root/"dip.mp4"
            subprocess.run(["ffmpeg","-nostdin","-hide_banner","-v","error","-y",
                            "-f","lavfi","-i","testsrc2=size=180x320:rate=30:duration=4",
                            "-c:v","libx264","-pix_fmt","yuv420p",str(source)],
                           check=True,timeout=40)
            keep=(Interval(0,1600),Interval(2300,3900))
            args=render(source,rendered,keep,has_audio=False,size=(540,960),
                        video_transitions=[cut(400)])
            graph=args[args.index("-filter_complex")+1]
            self.assertEqual(graph.count("fade=t="),2)
            self.assertIn("fade=t=out",graph)
            self.assertIn("fade=t=in",graph)
            data=probe(rendered)
            self.assertEqual((data.width,data.height),(540,960))
            self.assertLessEqual(abs(data.duration_ms-3200),80)
            self.assertFalse(data.has_audio)
            # Probe end-of-left and beginning-of-right sampled black sections.
            for t in (1.56,1.64):
                result=subprocess.run(["ffmpeg","-nostdin","-hide_banner","-v","error",
                    "-ss",str(t),"-i",str(rendered),"-frames:v","1",
                    "-vf","signalstats,metadata=print:file=-",
                    "-f","null","-"],capture_output=True,text=True,timeout=30)
                self.assertEqual(result.returncode,0,result.stderr[-300:])

if __name__=="__main__":unittest.main()
