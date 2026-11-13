"""Real template scene composition: replay, validation and FFmpeg audio parity."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from pausio.domain import Interval
from pausio.media import probe, render
from pausio.graphic_overlays import compose_graphics_ass
from pausio.project_commands import ProjectFormatError, ProjectTape
from pausio.scene_templates import (
    MAX_SCENES, TEMPLATES, catalog, compose_scene_events, validate_scene
)


def media(duration=12000):
    return {"filename": "phone.mp4", "sha256": "e" * 64,
            "duration_ms": duration, "has_audio": True}


def scene(kind, start, *, duration=2500, ident=None):
    return {
        "id": ident or "a"*32,
        "start_ms": start, "duration_ms": duration,
        "template": kind, "accent": "mint",
        "content": {f["key"]: f["default"] for f in TEMPLATES[kind]["fields"]}
    }


class SceneTemplateContractTests(unittest.TestCase):
    def test_catalog_matches_strict_command_and_replay_v8(self):
        kinds = [row["id"] for row in catalog()]
        self.assertEqual(kinds, ["stat_reveal", "permission_dialog", "code_highlight"])
        start = ProjectTape(media()).append("timeline.keep_all", {})
        a = scene("stat_reveal", 0)
        edited = start.append("scene.template.add", {"scene": a})
        self.assertEqual(edited.as_dict()["schema_version"], 8)
        self.assertEqual(edited.view.scene_templates, (a,))
        self.assertFalse(edited.view.approved)
        edited = edited.append("timeline.approve", {})
        self.assertTrue(edited.view.approved)
        updated = scene("stat_reveal", 0)
        updated["content"]["number"] = "1.379"
        changed = edited.append("scene.template.update", {"scene": updated})
        self.assertFalse(changed.view.approved)
        self.assertEqual(changed.view.scene_templates[0]["content"]["number"], "1.379")
        self.assertEqual(ProjectTape.from_dict(changed.as_dict()).view, changed.view)
        self.assertEqual(changed.undo().view.scene_templates[0], a)
        self.assertEqual(changed.undo().redo().view, changed.view)
        self.assertFalse(changed.append("scene.template.remove",
                                       {"scene_id": a["id"]}).view.scene_templates)
        legacy = {**edited.as_dict(), "schema_version": 7}
        self.assertEqual(ProjectTape.from_dict(legacy).as_dict()["schema_version"],8)

    def test_safe_failures_dont_mutate_tape(self):
        base = ProjectTape(media()).append("timeline.keep_all", {})
        good = scene("code_highlight", 3000)
        for invalid in (
            {**good,"start_ms": -1},
            {**good,"start_ms": True},
            {**good,"duration_ms": 13000},
            {**good,"template": "arbitrary_html"},
            {**good,"content": {**good["content"],"javascript": "alert(1)"}},
            {**good,"content": {**good["content"],"highlight_line": 0}},
            {**good,"content": {**good["content"],"code": "x"*35}},
            {**good,"content": {**good["content"],"code": "a\nb\nc\nd\ne\nf"}},
            {**good,"accent":"#123456"},
        ):
            with self.subTest(scene=invalid),self.assertRaises(ProjectFormatError):
                base.append("scene.template.add", {"scene": invalid})
        self.assertEqual(base.view.scene_templates,())
        first = base.append("scene.template.add",
                            {"scene":scene("stat_reveal", 0)})
        with self.assertRaises(ProjectFormatError):
            first.append("scene.template.add", {
                "scene":scene("permission_dialog",2000,ident="b"*32)})
        with self.assertRaises(ProjectFormatError):
            first.append("scene.template.add", {
                "scene":scene("permission_dialog",5000,ident="a"*32)})
        with self.assertRaises(ProjectFormatError):
            first.append("scene.template.update", {
                "scene":scene("permission_dialog",5000,ident="c"*32)})
        with self.assertRaises(ProjectFormatError):
            first.append("scene.template.remove", {"scene_id":"c"*32})
        invalid_json = first.as_dict()
        invalid_json["commands"][-1]["payload"]["scene"]["content"]["detail"] = ""
        with self.assertRaises(ProjectFormatError):
            ProjectTape.from_dict(invalid_json)

    def test_output_time_boundaries_and_cut_invalidation(self):
        base = ProjectTape(media()).append("timeline.keep_all",{})
        annotated = base.append("scene.template.add",{
            "scene":scene("stat_reveal", 8000, duration=3500)
        })
        with self.assertRaises(ProjectFormatError):
            annotated.append("segment.update",{
                "segment_id":annotated.view.segments[0]["id"],
                "start_ms": 0,"end_ms": 10000})
        # A scene cannot silently migrate to a different phrase after cuts.
        self.assertEqual(annotated.view.scene_templates[0]["start_ms"],8000)

    def test_fullscreen_ass_has_layering_stagger_and_no_override_injection(self):
        frames=[
            scene("stat_reveal",0),
            scene("permission_dialog",3000,ident="b"*32),
            scene("code_highlight",6000,ident="c"*32),
        ]
        frames[-1]["content"]["code"] = r"{\pos(0,0)}" + "\nno secret"
        frames[-1]["content"]["highlight_line"] = 1
        events=compose_scene_events(frames,12000)
        self.assertIn("SIMULAZIONE",events)
        self.assertIn("1.379",events)
        self.assertIn("SEGRETI",events)
        self.assertIn("1.122",events)
        self.assertIn("｛＼pos(0,0)｝",events)
        self.assertNotIn(r"{\pos(0,0)}",events)
        self.assertIn(r"\p1",events)
        self.assertIn("Dialogue: 4,",events)
        doc=compose_graphics_ass([{
            "id":"d"*32,"text":"Sottotitolo",
            "start_ms":0,"end_ms":1500
        }],[],scenes=frames,output_ms=12000)
        self.assertIn("Dialogue: 10,",doc)
        self.assertIn("Style: Scene,",doc)
        self.assertIn("Sottotitolo",doc)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                         "FFmpeg/FFprobe missing")
    def test_real_render_preserves_voice_under_scene_and_dark_background(self):
        from pausio.media import ffmpeg_has_filter
        if not ffmpeg_has_filter("ass"):
            self.skipTest("FFmpeg libass is required for real scene cards")
        with tempfile.TemporaryDirectory() as td:
            src=Path(td)/"white.mp4"
            dst=Path(td)/"scene.mp4"
            subprocess.run([
                "ffmpeg","-hide_banner","-loglevel","error","-nostdin","-y",
                "-f","lavfi","-i","color=c=white:s=180x320:r=30:d=2.9",
                "-f","lavfi","-i","sine=frequency=440:duration=2.9",
                "-shortest","-c:v","mpeg4","-c:a","aac",str(src)
            ],timeout=55,check=True)
            args=render(src,dst,(Interval(0,2800),),has_audio=True,
                        size=(540,960),scene_templates=[scene("stat_reveal",0)])
            self.assertIn("-filter_complex",args)
            self.assertIn("ass=filename=",args[args.index("-filter_complex")+1])
            info=probe(dst)
            self.assertTrue(info.has_audio)
            self.assertEqual((info.width,info.height),(540,960))
            self.assertGreater(dst.stat().st_size,1000)
            # A white source should be dark where the full-frame scene covers it.
            grab=subprocess.run([
                "ffmpeg","-hide_banner","-loglevel","error","-nostdin",
                "-ss","1.2","-i",str(dst),"-frames:v","1",
                "-vf","crop=16:16:8:8,scale=1:1,format=gray",
                "-f","rawvideo","-"
            ],capture_output=True,timeout=35,check=True)
            self.assertEqual(len(grab.stdout),1)
            self.assertLess(grab.stdout[0],85)
