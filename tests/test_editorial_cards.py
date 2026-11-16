"""Real editorial sequences: face, short UI overlays, full metric, back to face."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from pausio.domain import Interval
from pausio.graphic_overlays import compose_graphics_ass
from pausio.media import ffmpeg_has_filter, probe, render
from pausio.project_commands import ProjectFormatError, ProjectTape
from pausio.scene_templates import TEMPLATES, catalog, compose_scene_events


def media(duration=10000):
    return {"filename": "creator.mp4", "sha256": "d" * 64,
            "duration_ms": duration, "has_audio": True}


def card(kind, at=0, duration=2500, *, identity=None, accent="orange"):
    return {"id":identity or "a"*32, "template":kind, "start_ms":at,
            "duration_ms":duration, "accent":accent,
            "content":{f["key"]:f["default"] for f in TEMPLATES[kind]["fields"]}}


class EditorialCompositionContractTests(unittest.TestCase):
    def test_discoverable_modular_catalog_and_replay_v10(self):
        formats={f["id"]:f for f in catalog()}
        self.assertEqual(len(formats),8)
        self.assertEqual(formats["floating_insight"]["layout"],"overlay")
        self.assertEqual(formats["metric_spotlight"]["layout"],"fullscreen")
        self.assertEqual(formats["permission_mock"]["min_duration_ms"],1600)
        self.assertEqual(formats["code_inspector"]["max_duration_ms"],7000)
        self.assertEqual(formats["stat_reveal"]["min_duration_ms"],2500)
        base=ProjectTape(media()).append("timeline.keep_all",{})
        first=card("floating_insight",1000,1200)
        edited=base.append("scene.template.add",{"scene":first})
        self.assertEqual(edited.as_dict()["schema_version"],14)
        self.assertEqual(edited.view.scene_templates,(first,))
        self.assertEqual(edited.undo().view.scene_templates,())
        self.assertEqual(edited.undo().redo().view.scene_templates,(first,))
        self.assertEqual(ProjectTape.from_dict(edited.as_dict()).view,edited.view)
        old={**base.as_dict(),"schema_version":9}
        self.assertEqual(ProjectTape.from_dict(old).as_dict()["schema_version"],14)

    def test_timed_beats_include_real_face_only_gaps(self):
        base=ProjectTape(media(15000)).append("timeline.keep_all",{})
        rows=[
            card("floating_insight",1000,1200,identity="1"*32),
            card("metric_spotlight",5000,2000,identity="2"*32),
            card("permission_mock",8000,1800,identity="3"*32),
            card("code_inspector",10000,2200,identity="4"*32),
        ]
        for scene in rows:base=base.append("scene.template.add",{"scene":scene})
        rendered=compose_scene_events(list(base.view.scene_templates),15000)
        self.assertIn("SIMULAZIONE UI",rendered)
        self.assertIn("settings.local.json",rendered)
        self.assertIn("1.379",rendered)
        self.assertIn("Don't ask again",rendered)
        # No graphic events before the first beat nor after the last one.
        self.assertNotIn("Dialogue: 2,0:00:00.",rendered)
        self.assertNotIn("Dialogue: 2,0:00:13.",rendered)
        self.assertIn(r"\blur16",rendered)
        self.assertIn(r"\p1",rendered)
        output=compose_graphics_ass([],[],scenes=rows,output_ms=15000)
        self.assertIn("Style: Scene,",output)
        self.assertIn("Dialogue:",output)

    def test_injection_and_bounded_validation(self):
        tape=ProjectTape(media()).append("timeline.keep_all",{})
        for kind,duration in (
            ("floating_insight",900),
            ("permission_mock",1600),
            ("code_inspector",1800),
            ("metric_spotlight",1800),
        ):
            c=card(kind,2000,duration)
            item=tape.append("scene.template.add",{"scene":c})
            self.assertEqual(item.view.scene_templates[0]["template"],kind)
        for kind,duration in (
            ("floating_insight",899),
            ("permission_mock",1599),
            ("code_inspector",1799),
            ("metric_spotlight",7001),
            ("stat_reveal",900),
        ):
            with self.subTest(kind=kind,duration=duration),self.assertRaises(ProjectFormatError):
                tape.append("scene.template.add",{"scene":card(kind,0,duration)})
        inject=card("code_inspector",0,2000)
        inject["content"]["line_one"]=r"{\pos(0,0)}"
        inject["content"]["highlight"]="NOT A REAL TOKEN"
        data=compose_scene_events([inject],10000)
        self.assertIn("｛＼pos(0,0)｝",data)
        self.assertNotIn(r"{\pos(0,0)}",data)
        with self.assertRaises(ProjectFormatError):
            tape.append("scene.template.add",{
                "scene":{**card("floating_insight",0,1000),
                         "content":{"title":"text","detail":"good","script":"rm -rf"}}})
        self.assertEqual(tape.view.scene_templates,())

    def test_legacy_scenes_unchanged_and_no_intersections(self):
        base=ProjectTape(media()).append("timeline.keep_all",{})
        scene=card("stat_reveal",0,2500)
        one=base.append("scene.template.add",{"scene":scene})
        with self.assertRaises(ProjectFormatError):
            one.append("scene.template.add",{
                "scene":card("floating_insight",1900,1000,identity="b"*32)})
        self.assertEqual(one.view.scene_templates,(scene,))
        self.assertEqual(one.append("scene.template.remove",
                                   {"scene_id":scene["id"]}).view.scene_templates,())

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                         "Real FFmpeg/FFprobe needed for pixel oracle")
    def test_real_composition_preserves_voice_and_switches_layouts(self):
        if not ffmpeg_has_filter("ass"):
            self.skipTest("libass filter unavailable")
        with tempfile.TemporaryDirectory() as td:
            src=Path(td)/"phone.mp4"
            dst=Path(td)/"edited.mp4"
            subprocess.run([
                "ffmpeg","-hide_banner","-loglevel","error","-nostdin","-y",
                "-f","lavfi","-i","color=c=blue:s=180x320:r=30:d=6",
                "-f","lavfi","-i","sine=frequency=440:duration=6",
                "-shortest","-c:v","mpeg4","-c:a","aac",str(src)
            ],check=True,timeout=45)
            scenes=[
                card("floating_insight",650,1250,identity="1"*32),
                card("metric_spotlight",2550,2100,identity="2"*32),
            ]
            render(src,dst,(Interval(0,5900),),size=(540,960),
                   has_audio=True,scene_templates=scenes)
            info=probe(dst)
            self.assertTrue(info.has_audio)
            self.assertEqual((info.width,info.height),(540,960))

            def pixel(seconds,x,y):
                result=subprocess.run([
                    "ffmpeg","-hide_banner","-loglevel","error",
                    "-nostdin","-ss",str(seconds),"-i",str(dst),
                    "-frames:v","1","-vf",
                    f"crop=12:12:{x}:{y},scale=1:1,format=gray",
                    "-f","rawvideo","-",
                ],check=True,capture_output=True,timeout=30)
                self.assertEqual(len(result.stdout),1)
                return result.stdout[0]
            # Blue source stays visible on non-graphic moments.
            baseline=pixel(.25,110,175)
            self.assertLess(baseline,100)
            # At 1.2s the bright floating top card appears but face underneath remains.
            self.assertGreater(pixel(1.30,110,175),180)
            self.assertLess(pixel(1.30,110,750),100)
            # Metric insert deliberately takes over the whole frame only briefly.
            self.assertGreater(pixel(3.40,110,750),150)
            # After the insert all graphic layers are gone; natural video resumes.
            self.assertLess(pixel(5.20,110,175),100)
            self.assertLess(pixel(5.20,110,750),100)
