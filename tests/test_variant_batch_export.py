"""Safe three-variant ZIP export: approval gates, isolated jobs, atomicity."""
from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile

from pausio.studio import StudioError
from pausio.variant_export import BATCH_FILENAME
from test_studio_recovery import applied_plan, imported_workspace, new_workspace


def prepare(ws):
    applied_plan(ws)
    ws.fork_style_variants({"revision": ws.tape.revision})
    for style in ("authority", "visual_explainer", "social_impact"):
        ws.switch_style_variant({
            "revision": ws.tape.revision, "style_id": style,
        })
        ws.approve_plan()


def await_export(ws):
    for _ in range(200):
        job = ws.snapshot()["job"]
        if job["status"] in {"completed", "failed"}:
            return job
        time.sleep(0.02)
    raise AssertionError("Export job did not terminate")


class ThreeVariantBatchExportTests(unittest.TestCase):
    def test_approval_revision_and_media_gates(self):
        with tempfile.TemporaryDirectory() as td:
            ws=imported_workspace(Path(td)/"workspace")
            try:
                applied_plan(ws)
                ws.fork_style_variants({"revision": ws.tape.revision})
                revision=ws.tape.revision
                ident=ws.media_id
                for payload in (
                    {"revision": revision, "media_id": ident},
                    {"revision": revision+1, "media_id": ident},
                    {"revision": True, "media_id": ident},
                    {"revision": revision, "media_id": "stale"},
                    {"revision": revision},
                    {"revision": revision, "media_id": ident, "extra": 1},
                ):
                    with self.subTest(payload=payload), self.assertRaises(StudioError):
                        ws.render_all_style_variants(payload)
                self.assertFalse(ws.snapshot()["batch_export_ready"])
                self.assertFalse((ws.directory/BATCH_FILENAME).exists())
            finally:
                ws.close()

    def test_one_click_packages_exactly_three_no_approval_mutation_and_invalidates(self):
        with tempfile.TemporaryDirectory() as td:
            directory=Path(td)/"workspace"
            ws=imported_workspace(directory)
            try:
                prepare(ws)
                before=ws.export_style_variants()
                seen=[]
                def render_fake(source, output, segments, **kwargs):
                    seen.append({
                        "filename":output.name, "size":kwargs["size"],
                        "approved_cues":list(kwargs["captions"]),
                        "audio":kwargs["has_audio"],
                    })
                    output.write_bytes(b"synthetic test MP4 content: "+output.name.encode())
                with (
                    patch("pausio.variant_export.render",side_effect=render_fake),
                    patch("pausio.variant_export.probe",return_value=SimpleNamespace(
                        width=1080,height=1920,has_audio=True)),
                ):
                    ws.render_all_style_variants({
                        "revision":ws.tape.revision,"media_id":ws.media_id
                    })
                    job=await_export(ws)
                self.assertEqual(job["status"],"completed",job)
                self.assertEqual((job["completed"],job["total"]),(3,3))
                self.assertTrue(ws.snapshot()["batch_export_ready"])
                self.assertEqual(before,ws.export_style_variants())
                self.assertEqual(len(seen),3)
                self.assertTrue(all(x["size"]==(1080,1920) for x in seen))
                self.assertTrue(all(x["audio"] for x in seen))
                archive=directory/BATCH_FILENAME
                with ZipFile(archive) as zip_file:
                    self.assertEqual(set(zip_file.namelist()),{
                        "pausio-authority.mp4","pausio-visual-explainer.mp4",
                        "pausio-social-impact.mp4",
                    })
                    self.assertIsNone(zip_file.testzip())
                # Any typed edit invalidates the ZIP; no stale version leaks.
                ws.switch_style_variant({
                    "revision":ws.tape.revision,"style_id":"authority"
                })
                self.assertFalse(ws.snapshot()["batch_export_ready"])
                self.assertFalse(archive.exists())
            finally:
                ws.close()
            restored=new_workspace(directory)
            try:
                self.assertFalse(restored.snapshot()["batch_export_ready"])
                self.assertEqual(len(restored.snapshot()["variant_workspaces"]),3)
            finally:
                restored.close()

    def test_mid_job_failure_never_creates_downloadable_partial_zip(self):
        with tempfile.TemporaryDirectory() as td:
            ws=imported_workspace(Path(td)/"workspace")
            try:
                prepare(ws)
                count=0
                gate=threading.Event()
                def fail_second(source,output,segments,**kwargs):
                    nonlocal count
                    count+=1
                    if count==1:
                        gate.wait(timeout=3)
                        output.write_bytes(b"first only")
                    else:
                        raise RuntimeError("synthetic video error")
                with (
                    patch("pausio.variant_export.render",side_effect=fail_second),
                    patch("pausio.variant_export.probe",return_value=SimpleNamespace(
                        width=1080,height=1920,has_audio=True)),
                ):
                    ws.render_all_style_variants({
                        "revision":ws.tape.revision,"media_id":ws.media_id
                    })
                    with self.assertRaises(StudioError):
                        ws.render_all_style_variants({
                            "revision":ws.tape.revision,"media_id":ws.media_id
                        })
                    self.assertFalse(ws.snapshot()["batch_export_ready"])
                    gate.set()
                    job=await_export(ws)
                self.assertEqual(job["status"],"failed",job)
                self.assertEqual(job["completed"],1)
                self.assertFalse(ws.snapshot()["batch_export_ready"])
                self.assertFalse((ws.directory/BATCH_FILENAME).exists())
            finally:
                gate.set()
                ws.close()


if __name__ == "__main__":
    unittest.main()
