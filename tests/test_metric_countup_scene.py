"""V15 count-up template: literal data, existing renderer and backwards compatibility."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from pausio.domain import Interval
from pausio.media import probe, render, ffmpeg_has_filter
from pausio.project_commands import ProjectTape, ProjectFormatError
from pausio.scene_templates import TEMPLATES, catalog, compose_scene_events, validate_scene


def media():
    return {"filename": "synthetic.mp4", "sha256": "e"*64,
            "duration_ms": 3600, "has_audio": True}


def example(kind="metric_countup",number="1.379"):
    content={f["key"]:f["default"] for f in TEMPLATES[kind]["fields"]}
    content["number"]=number
    return {
        "id":"a"*32, "template":kind, "start_ms":0,
        "duration_ms":2800, "accent":"orange", "content":content,
    }


class MetricCountupTemplateTests(unittest.TestCase):
    def test_v15_registered_and_strict_integer_only(self):
        self.assertEqual(catalog()[-1]["id"], "metric_countup")
        good=example()
        self.assertEqual(validate_scene(good,3600),good)
        for raw in ("12,5%", "-2", "01", "12.3", "10000000",
                    "999999999", r"{\\pos(0,0)}"):
            with self.subTest(number=raw),self.assertRaises(ValueError):
                validate_scene(example(number=raw),3600)
        self.assertEqual(validate_scene(example(number="0"),3600)["content"]["number"],"0")

    def test_v15_portable_replay_and_v14_metric_unchanged(self):
        tape=ProjectTape(media()).append("timeline.keep_all",{})
        scene=example()
        created=tape.append("scene.template.add",{"scene":scene})
        self.assertEqual(created.as_dict()["schema_version"],15)
        self.assertEqual(created.view.scene_templates[0],scene)
        self.assertEqual(created.undo().view.scene_templates,())
        self.assertEqual(ProjectTape.from_dict(created.as_dict()).view,created.view)
        old=tape.append("scene.template.add",{"scene":example("metric_spotlight")})
        legacy={**old.as_dict(),"schema_version":14}
        self.assertEqual(ProjectTape.from_dict(legacy).view,old.view)
        original=compose_scene_events([example("metric_spotlight")],3600)
        animated=compose_scene_events([scene],3600)
        self.assertEqual(original.count("1.379"),1)
        self.assertGreater(animated.count("Dialogue: 5,"),6)
        self.assertIn("1.379",animated)
        self.assertNotEqual(original,animated)
        self.assertEqual(compose_scene_events([scene],3600),animated)

    def test_json_schema_v15_declares_exact_animation_variant(self):
        path=Path(__file__).parents[1]/"schemas"/"pausio-project-v15.schema.json"
        parsed=json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(parsed["properties"]["schema_version"]["const"],15)
        entries=parsed["$defs"]["scene_template"]["oneOf"]
        countup=[e for e in entries if e["properties"]["template"]["const"]=="metric_countup"]
        self.assertEqual(len(countup),1)
        self.assertIn("number",countup[0]["properties"]["content"]["required"])
        self.assertIn("pattern",countup[0]["properties"]["content"]["properties"]["number"])

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                         "FFmpeg and FFprobe required")
    def test_real_ffmpeg_preview_preserves_voice_and_geometry(self):
        if not ffmpeg_has_filter("ass"):
            self.skipTest("FFmpeg libass is required")
        with tempfile.TemporaryDirectory() as td:
            src=Path(td)/"input.mp4"
            dst=Path(td)/"metric.mp4"
            subprocess.run([
                "ffmpeg","-hide_banner","-loglevel","error","-nostdin","-y",
                "-f","lavfi","-i","color=c=white:s=180x320:r=30:d=3.3",
                "-f","lavfi","-i","sine=frequency=440:duration=3.3",
                "-shortest","-c:v","mpeg4","-c:a","aac",str(src),
            ],check=True,timeout=60)
            args=render(src,dst,(Interval(0,3200),),has_audio=True,
                        size=(540,960),scene_templates=[example()])
            self.assertIn("ass=filename=",args[args.index("-filter_complex")+1])
            info=probe(dst)
            self.assertTrue(info.has_audio)
            self.assertEqual((info.width,info.height),(540,960))
            self.assertGreater(dst.stat().st_size,1000)


if __name__ == "__main__":
    unittest.main()
