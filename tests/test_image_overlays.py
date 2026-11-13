"""Native local image PIP: strict portable data and synthetic FFmpeg rendering."""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from pausio.domain import Interval
from pausio.image_overlays import validate_image_overlay
from pausio.media import MediaError, probe, probe_image, render
from pausio.project_commands import ProjectFormatError, ProjectTape


class ImageOverlayTests(unittest.TestCase):
    def setUp(self):
        self.media = {"filename":"clip.mp4","sha256":"a"*64,
                      "duration_ms":4000,"has_audio":False}
        self.start = ProjectTape(self.media).append("timeline.keep_all",{})
        self.image = {"id":"b"*32,"asset_sha256":"c"*64,
                      "filename":"demo.png","start_ms":700,"duration_ms":1500,
                      "x_pct":65,"y_pct":20,"width_pct":45}

    def test_event_replay_portability_and_undo_redo(self):
        tape=self.start.append("image.overlay.add",{"image":self.image})
        self.assertEqual(tape.as_dict()["schema_version"],8)
        self.assertEqual(tape.view.image_overlays,(self.image,))
        self.assertEqual(ProjectTape.from_dict(tape.as_dict()).view.image_overlays,
                         tape.view.image_overlays)
        self.assertFalse(tape.undo().view.image_overlays)
        self.assertEqual(tape.undo().redo().view.image_overlays,(self.image,))
        updated={**self.image,"x_pct":40,"width_pct":60}
        tape=tape.append("image.overlay.update",{"image":updated})
        self.assertEqual(tape.view.image_overlays[0]["width_pct"],60)
        tape=tape.append("image.overlay.remove",{"image_id":self.image["id"]})
        self.assertEqual(tape.view.image_overlays,())
        self.assertEqual(len(tape.undo().view.image_overlays),1)

    def test_malformed_asset_and_out_of_bounds_rejected(self):
        cases=(
            {"id":"../../bad"}, {"asset_sha256":"notasha"},
            {"filename":"https://example.com/a.png"}, {"filename":"bad.svg"},
            {"filename":"bad\n.png"}, {"start_ms":True},
            {"start_ms":3900}, {"duration_ms":12001},
            {"x_pct":101}, {"width_pct":90}, {"hidden_shell":"echo unsafe"}
        )
        for case in cases:
            with self.subTest(case=case),self.assertRaises(ProjectFormatError):
                self.start.append("image.overlay.add",{"image":{**self.image,**case}})
        self.assertEqual(self.start.view.image_overlays,())

    def test_editing_keep_shorter_than_image_rejected(self):
        tape=self.start.append("image.overlay.add",{"image":self.image})
        segment=tape.view.segments[0]["id"]
        with self.assertRaises(ProjectFormatError):
            tape.append("segment.update",{"segment_id":segment,
                "start_ms":0,"end_ms":1000})

    def test_v6_legacy_project_is_accepted_without_images(self):
        old={**self.start.as_dict(),"schema_version":6}
        self.assertEqual(ProjectTape.from_dict(old).view.image_overlays,())

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                         "FFmpeg/ffprobe required")
    def test_real_ffmpeg_png_pip_changes_pixels_without_changing_speech_length(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/"source.mp4";image=root/"broll.png"
            subprocess.run(["ffmpeg","-hide_banner","-nostdin","-v","error","-y",
                "-f","lavfi","-i","testsrc2=size=180x320:rate=30:duration=2",
                "-c:v","libx264","-pix_fmt","yuv420p",str(source)],
                check=True,timeout=40)
            subprocess.run(["ffmpeg","-hide_banner","-nostdin","-v","error","-y",
                "-f","lavfi","-i","color=c=red:s=120x96:r=1:d=1",
                "-frames:v","1",str(image)],check=True,timeout=30)
            self.assertEqual(probe_image(image),(120,96))
            digest=hashlib.sha256(image.read_bytes()).hexdigest()
            pip={**self.image,"asset_sha256":digest,"start_ms":500,
                 "duration_ms":900}
            plain=root/"plain.mp4";with_pip=root/"pip.mp4"
            keep=(Interval(0,2000),)
            render(source,plain,keep,has_audio=False,size=(540,960))
            render(source,with_pip,keep,has_audio=False,size=(540,960),
                   image_overlays=[(image,pip)])
            info=probe(with_pip)
            self.assertEqual((info.width,info.height),(540,960))
            self.assertTrue(1800<=info.duration_ms<=2200)
            def frame_sha(path):
                out=subprocess.run(["ffmpeg","-hide_banner","-nostdin","-v","error",
                    "-ss","1.000","-i",str(path),"-frames:v","1",
                    "-f","image2pipe","-vcodec","ppm","-"],
                    capture_output=True,check=True,timeout=30)
                return hashlib.sha256(out.stdout).hexdigest()
            self.assertNotEqual(frame_sha(plain),frame_sha(with_pip))
            with self.assertRaises(MediaError):
                render(source,root/"unsafe.mp4",keep,has_audio=False,
                       image_overlays=[(image,{**pip,"asset_sha256":"0"*64})],
                       size=(540,960))
