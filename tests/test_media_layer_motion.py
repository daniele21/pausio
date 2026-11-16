"""Portable media motion: validation, undo/redo and actual local FFmpeg frames."""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from pausio.domain import Interval
from pausio.media import probe, render
from pausio.media_motion import compile_media_motion, validate_media_motion
from pausio.project_commands import ProjectFormatError, ProjectTape


class MediaLayerMotionTests(unittest.TestCase):
    def setUp(self):
        media = {"filename": "voice.mp4", "sha256": "a"*64,
                 "duration_ms": 3000, "has_audio": True}
        self.tape = ProjectTape(media).append("timeline.keep_all", {})
        self.motion = {"enter": "slide_left", "exit": "slide_right",
                       "enter_ms": 250, "exit_ms": 250}
        self.image = {"id": "b"*32, "asset_sha256": "c"*64,
                      "filename": "image.png", "start_ms": 500,
                      "duration_ms": 1500, "x_pct": 50, "y_pct": 20,
                      "width_pct": 50}
        self.video = {"id": "d"*32, "asset_sha256": "e"*64,
                      "filename": "broll.mp4", "start_ms": 500,
                      "duration_ms": 1500, "media_in_ms": 0,
                      "mode": "fullscreen", "x_pct": 50, "y_pct": 20,
                      "width_pct": 50}

    def test_portability_and_reversible_updates(self):
        for kind, payload_key, initial in (
            ("image.overlay", "image", self.image),
            ("video.broll", "video", self.video),
        ):
            with self.subTest(kind=kind):
                base=self.tape.append(kind+".add", {payload_key:initial})
                modified={**initial, "motion":dict(self.motion)}
                edited=base.append(kind+".update", {payload_key:modified})
                field="image_overlays" if kind.startswith("image") else "video_broll"
                self.assertEqual(getattr(edited.view,field)[0]["motion"], self.motion)
                self.assertEqual(edited.as_dict()["schema_version"],14)
                self.assertEqual(getattr(edited.undo().view,field)[0],initial)
                self.assertEqual(getattr(edited.undo().redo().view,field)[0],modified)
                self.assertEqual(getattr(ProjectTape.from_dict(edited.as_dict()).view,field)[0],modified)
                legacy={**base.as_dict(),"schema_version":13}
                self.assertEqual(getattr(ProjectTape.from_dict(legacy).view,field)[0],initial)

    def test_motion_strict_limits_and_safe_generated_expressions(self):
        for bad in (
            {"enter":"pop"}, {"exit":"shrink"}, {"enter":"shell"},
            {"enter":[]}, {"enter_ms":True}, {"enter_ms":810},
            {"exit_ms":-1}, {"run":"os.system"}, {"enter_ms":1200},
            {"exit":"none", "exit_ms":200},
        ):
            with self.subTest(bad=bad),self.assertRaises(ProjectFormatError):
                self.tape.append("image.overlay.add",{
                    "image": {**self.image,"motion":{**self.motion,**bad}}
                })
            with self.subTest(video_bad=bad),self.assertRaises(ProjectFormatError):
                self.tape.append("video.broll.add",{
                    "video":{**self.video,"motion":{**self.motion,**bad}}
                })
        with self.assertRaises(ProjectFormatError):
            self.tape.append("video.broll.add",{
                "video": {**self.video, "duration_ms": 450, "motion":self.motion}
            })
        result=validate_media_motion(self.motion, 1500)
        self.assertEqual(result,self.motion)
        fades,x,y=compile_media_motion({**self.video,"motion":result},
                                       size=(540,960),x="0",y="0")
        self.assertIn("fade=t=in",fades)
        self.assertIn("fade=t=out",fades)
        self.assertIn("max(",x)
        self.assertIn("min(",x)
        self.assertEqual(y,"0")

    @staticmethod
    def pixel_at(path: Path, seconds: float, x: int, y: int) -> tuple[int,int,int]:
        result=subprocess.run([
            "ffmpeg","-hide_banner","-nostdin","-v","error",
            "-ss",f"{seconds:.3f}","-i",str(path),
            "-frames:v","1",
            "-vf",f"crop=16:16:{x-8}:{y-8},scale=1:1",
            "-pix_fmt","rgb24","-f","rawvideo","-"
        ],capture_output=True,check=True,timeout=30)
        if len(result.stdout)!=3:
            raise AssertionError(f"Unexpected RGB length: {len(result.stdout)}")
        return tuple(result.stdout)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                         "FFmpeg/FFprobe required")
    def test_image_and_video_fades_in_out_without_cutting_speech(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            source, roll, image=(root/"speech.mp4", root/"red.mp4",root/"green.png")
            subprocess.run([
                "ffmpeg","-hide_banner","-nostdin","-v","error","-y",
                "-f","lavfi","-i","color=c=blue:s=180x320:r=30:d=3",
                "-f","lavfi","-i","sine=frequency=440:duration=3",
                "-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac",
                "-shortest",str(source)
            ],check=True,timeout=45)
            subprocess.run([
                "ffmpeg","-hide_banner","-nostdin","-v","error","-y",
                "-f","lavfi","-i","color=c=red:s=180x320:r=30:d=2",
                "-f","lavfi","-i","sine=frequency=880:duration=2",
                "-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac",
                "-shortest",str(roll)
            ],check=True,timeout=45)
            subprocess.run([
                "ffmpeg","-hide_banner","-nostdin","-v","error","-y",
                "-f","lavfi","-i","color=c=green:s=120x96:r=1:d=1",
                "-frames:v","1",str(image)
            ],check=True,timeout=30)
            keep=(Interval(0,3000),)
            video={**self.video,"asset_sha256":hashlib.sha256(roll.read_bytes()).hexdigest(),
                   "motion":self.motion}
            picture={**self.image,"asset_sha256":hashlib.sha256(image.read_bytes()).hexdigest(),
                     "motion":{"enter":"slide_up","exit":"slide_down",
                               "enter_ms":250,"exit_ms":250}}
            roll_output,pip_output=root/"roll.mp4",root/"image.mp4"
            render(source,roll_output,keep,has_audio=True,size=(540,960),
                   video_broll=[(roll,video)])
            render(source,pip_output,keep,has_audio=True,size=(540,960),
                   image_overlays=[(image,picture)])
            for output in (roll_output,pip_output):
                self.assertTrue(probe(output).has_audio)
                self.assertTrue(2900 <= probe(output).duration_ms <= 3100)
            for output, x, y, channel in (
                (roll_output,270,480,0), (pip_output,270,250,1)
            ):
                early=self.pixel_at(output,.55,x,y)
                middle=self.pixel_at(output,1.20,x,y)
                late=self.pixel_at(output,1.95,x,y)
                after=self.pixel_at(output,2.40,x,y)
                self.assertGreater(middle[channel],early[channel]+35,
                                   (output.name,early,middle))
                self.assertGreater(middle[channel],late[channel]+35,
                                   (output.name,late,middle))
                self.assertGreater(after[2],after[0]+80)
