"""Split dashboard: typed commands, output-time FFmpeg video, original voice."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from pausio.domain import Interval
from pausio.media import ffmpeg_has_filter, probe, render
from pausio.project_commands import ProjectFormatError, ProjectTape
from pausio.scene_templates import TEMPLATES, catalog, compose_scene_events
from pausio.split_dashboard import compile_speaker_splits


def dashboard(start=0, duration=2800):
    return {
        "id":"d"*32, "template":"dashboard_split", "start_ms":start,
        "duration_ms":duration, "accent":"orange",
        "content":{f["key"]:f["default"]
                   for f in TEMPLATES["dashboard_split"]["fields"]},
    }


def media():
    return {"filename":"example.mp4","sha256":"f"*64,
            "duration_ms":4000,"has_audio":True}


class SplitDashboardTests(unittest.TestCase):
    def test_catalog_and_replay_v9_undo_legacy(self):
        self.assertEqual([r["id"] for r in catalog()], [
            "stat_reveal","permission_dialog","dashboard_split","code_highlight"
        ])
        self.assertEqual(next(r["layout"] for r in catalog()
                              if r["id"]=="dashboard_split"),"split_vertical")
        original=ProjectTape(media()).append("timeline.keep_all",{})
        scene=dashboard()
        edited=original.append("scene.template.add",{"scene":scene})
        self.assertEqual(edited.as_dict()["schema_version"],9)
        self.assertEqual(edited.view.scene_templates,(scene,))
        self.assertEqual(edited.undo().view.scene_templates,())
        self.assertEqual(edited.undo().redo().view.scene_templates,(scene,))
        self.assertEqual(ProjectTape.from_dict(edited.as_dict()).view,edited.view)
        # v8 projects containing older scene types still import into v9.
        old=ProjectTape(media()).append("timeline.keep_all",{}).as_dict()
        old["schema_version"]=8
        self.assertEqual(ProjectTape.from_dict(old).as_dict()["schema_version"],9)

    def test_no_arbitrary_expressions_and_bounded_controls(self):
        original=ProjectTape(media()).append("timeline.keep_all",{})
        scene=dashboard()
        for replacement in (
            {"presenter_height_pct":34},
            {"presenter_height_pct":56},
            {"presenter_height_pct":True},
            {"presenter_anchor_pct":90},
            {"progress_pct":101},
            {"progress_pct":-1},
            {"task_one":"x"*31},
            {"title":r"{\pos(0,0)}"},
        ):
            with self.subTest(change=replacement):
                candidate=dashboard()
                candidate["content"].update(replacement)
                if "title" in replacement:
                    # ASS-like text is escaped (not interpreted), not rejected.
                    new=original.append("scene.template.add",{"scene":candidate})
                    data=compose_scene_events(list(new.view.scene_templates),4000)
                    self.assertNotIn(r"{\pos(0,0)}",data)
                    continue
                with self.assertRaises(ProjectFormatError):
                    original.append("scene.template.add",{"scene":candidate})
        self.assertFalse(original.view.scene_templates)

    def test_split_filter_uses_bounded_crop_and_output_time(self):
        components=[]
        result=compile_speaker_splits(components,"[normalv]",[dashboard()],(540,960))
        self.assertEqual(result,"[sfull0]")
        graph=";".join(components)
        self.assertIn("crop=540:432:0:",graph)
        self.assertIn("overlay=x=0:y=528:",graph)
        self.assertIn(r"gte(t\,0.000)*lt(t\,2.800)",graph)
        self.assertNotIn("http",graph)
        ass=compose_scene_events([dashboard()],4000)
        self.assertIn("Avanzamento",ass)
        # Budget is intentionally shown later, not at 2.8 seconds.
        self.assertNotIn("Budget: sotto controllo", ass)
        long_ass=compose_scene_events([dashboard(duration=6500)],7000)
        self.assertIn("Budget: sotto controllo",long_ass)
        self.assertIn("✓",ass)
        self.assertIn("Dialogue:",ass)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                         "FFmpeg unavailable")
    def test_render_split_screen_is_video_real_and_preserves_speech(self):
        if not ffmpeg_has_filter("ass"):
            self.skipTest("FFmpeg libass not available")
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source=root/"source.mp4"
            output=root/"rendered.mp4"
            # White scene makes split boundary objectively testable.
            subprocess.run([
                "ffmpeg","-hide_banner","-nostdin","-loglevel","error","-y",
                "-f","lavfi","-i","color=c=white:s=180x320:r=30:d=4",
                "-f","lavfi","-i","sine=frequency=440:duration=4",
                "-shortest","-c:v","mpeg4","-c:a","aac",str(source),
            ],timeout=45,check=True)
            args=render(source,output,(Interval(0,3900),),
                        has_audio=True,size=(540,960),
                        scene_templates=[dashboard()])
            graph=args[args.index("-filter_complex")+1]
            self.assertIn("crop=540:432",graph)
            self.assertIn("ass=filename=",graph)
            info=probe(output)
            self.assertTrue(info.has_audio)
            self.assertEqual((info.width,info.height),(540,960))
            # Verify top dashboard is dark *while* bottom still shows video.
            def pixel(at, x, y):
                p=subprocess.run([
                    "ffmpeg","-hide_banner","-nostdin","-loglevel","error",
                    "-ss",str(at),"-i",str(output),"-frames:v","1",
                    "-vf",f"crop=16:16:{x}:{y},scale=1:1,format=gray",
                    "-f","rawvideo","-",
                ],capture_output=True,check=True,timeout=30)
                self.assertEqual(len(p.stdout),1)
                return p.stdout[0]
            self.assertLess(pixel(.7,20,50),100)
            self.assertGreater(pixel(.7,20,750),190)
            self.assertGreater(pixel(3.3,20,50),190)
            # Range preview shares the same filtergraph and keeps speaker audio.
            snippet=root/"range.mp4"
            render(source,snippet,(Interval(0,3900),),has_audio=True,
                   size=(540,960),scene_templates=[dashboard()],
                   output_window=(800,1200))
            self.assertTrue(probe(snippet).has_audio)
            self.assertLess(pixel(.7,20,50),100)
