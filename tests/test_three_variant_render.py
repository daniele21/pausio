"""Synthetic E2E smoke: three independent v15 editorial timelines produce distinct local MP4s.

No private media, no remote API, and no automatic publish/approval. This test
uses the same typed ProjectTape + FFmpeg path as Studio with shorter preview
resolution to keep CI affordable.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from pausio.domain import Interval
from pausio.media import ffmpeg_has_filter, probe, render
from pausio.project_commands import ProjectTape
from pausio.scene_templates import TEMPLATES
from pausio.variant_projects import VariantWorkspace


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                     "FFmpeg/ffprobe required for end-to-end video test")
class ThreeVariantRenderTests(unittest.TestCase):
    def test_three_local_exports_with_audio_scene_variants_and_replay(self):
        if not ffmpeg_has_filter("ass"):
            self.skipTest("FFmpeg with libass required")
        with tempfile.TemporaryDirectory(prefix="pausio-three-modes-") as tmp:
            directory = Path(tmp)
            original = directory / "synthetic.mp4"
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                "-f", "lavfi", "-i", "color=c=0x14202D:s=180x320:r=25:d=3.8",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=3.8",
                "-shortest", "-c:v", "mpeg4", "-c:a", "aac",
                str(original),
            ], check=True, timeout=50)
            info = probe(original)
            media = {
                "filename": original.name,
                "sha256": hashlib.sha256(original.read_bytes()).hexdigest(),
                "duration_ms": info.duration_ms,
                "has_audio": info.has_audio,
            }
            initial = ProjectTape(media).append("timeline.keep_all", {})
            initial = initial.append("caption.set", {
                "style": "social",
                "cues": [
                    {
                        "id": "1" * 32, "start_ms": 200, "end_ms": 1900,
                        "text": "Prova locale: tre regie indipendenti",
                    },
                ],
            })
            variants = VariantWorkspace.fork(initial)
            tapes = {}
            for key, preset in (
                ("authority", "minimal"),
                ("visual_explainer", "word_focus"),
                ("social_impact", "kinetic"),
            ):
                tape = variants.tapes[key].append("caption.style", {"style": preset})
                if key != "authority":
                    template = "floating_insight" if key == "visual_explainer" else "metric_countup"
                    scene = {
                        "id": ("2" if key == "visual_explainer" else "3") * 32,
                        "template": template,
                        "start_ms": 0, "duration_ms": 2200,
                        "accent": "orange" if key == "social_impact" else "mint",
                        "content": {
                            item["key"]: item["default"]
                            for item in TEMPLATES[template]["fields"]
                        },
                    }
                    if template == "metric_countup":
                        scene["content"]["number"] = "1.379"
                        scene["content"]["source_note"] = "METRICA SINTETICA · DEMO"
                    else:
                        scene["content"]["title"] = "ESEMPIO DI SPIEGAZIONE"
                    tape = tape.append("scene.template.add", {"scene": scene})
                tapes[key] = tape
            variants = VariantWorkspace("authority", tapes)
            restored = VariantWorkspace.from_dict(
                json.loads(json.dumps(variants.as_dict())),
                source_tape=variants.tapes["authority"],
            )
            self.assertEqual(
                [len(restored.tapes[k].view.scene_templates) for k in
                 ("authority", "visual_explainer", "social_impact")],
                [0, 1, 1],
            )
            outputs = []
            for style_id in ("authority", "visual_explainer", "social_impact"):
                tape = restored.tapes[style_id]
                self.assertFalse(tape.view.approved)
                tape = tape.append("timeline.approve", {})
                self.assertTrue(tape.view.approved)
                out = directory / f"pausio-{style_id}.mp4"
                plan = tape.edit_plan(str(original))
                render(
                    original, out, plan.segments, has_audio=True,
                    size=(540, 960), captions=list(tape.view.captions),
                    caption_style=tape.view.caption_style,
                    caption_config=tape.view.caption_config,
                    scene_templates=list(tape.view.scene_templates),
                )
                rendered = probe(out)
                self.assertTrue(rendered.has_audio)
                self.assertEqual((rendered.width, rendered.height), (540, 960))
                self.assertGreater(rendered.duration_ms, 3000)
                self.assertLessEqual(rendered.duration_ms, info.duration_ms + 150)
                self.assertGreater(out.stat().st_size, 1000)
                outputs.append(hashlib.sha256(out.read_bytes()).hexdigest())
            self.assertEqual(len(set(outputs)), 3, "Each style must render a distinct MP4")
            self.assertEqual(
                restored.tapes["authority"].view.caption_style, "minimal"
            )
            self.assertEqual(
                restored.tapes["social_impact"].view.caption_style, "kinetic"
            )


if __name__ == "__main__":
    unittest.main()
