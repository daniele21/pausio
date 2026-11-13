"""MCP asset boundary: no path/URL imports, exact metadata and real FFmpeg."""
from __future__ import annotations

import base64
import hashlib
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path

from pausio.mcp_assets import AssetToolError, decode_media
from pausio.local_mcp import StudioClient, call_tool, TOOLS, response_for
from pausio.media import probe
from pausio.studio import StudioWorkspace, create_server


class InMemoryStudio:
    def __init__(self):
        self.calls=[]
        self.state={
            "media_id":"a"*32,"project_revision":7,
            "media":{"duration_ms":5000},
            "plan":{"segments":[{"start_ms":0,"end_ms":3000}]},
            "image_overlays":[{
                "id":"b"*32,"asset_sha256":"c"*64,"filename":"reference.png",
                "start_ms":500,"duration_ms":1000,"x_pct":50,"y_pct":20,
                "width_pct":55,"available":True
            }],
            "audio_clips":[{
                "id":"d"*32,"asset_sha256":"e"*64,"filename":"riser.mp3",
                "start_ms":0,"duration_ms":700,"gain_db":-12,
                "available":True
            }]
        }

    def request(self, method, path, payload=None):
        self.calls.append((method,path,payload))
        if path=="/api/state":
            return dict(self.state)
        if path=="/api/command":
            self.state["project_revision"]+=1
            return {
                "project_revision":self.state["project_revision"],
                "last_command":payload["type"],"approved":False,
                "preview_ready":False
            }
        raise AssertionError(path)


class MCPAssetTests(unittest.TestCase):
    def setUp(self):
        self.studio=InMemoryStudio()

    def test_inventory_reports_only_bound_media_and_no_paths(self):
        expected={t["name"] for t in TOOLS}
        self.assertTrue({
            "pausio_list_assets","pausio_import_image","pausio_import_audio",
            "pausio_place_existing_image","pausio_place_existing_audio"
        } <= expected)
        listing=call_tool("pausio_list_assets",{},self.studio)
        self.assertEqual(len(listing["images"]),1)
        self.assertEqual(len(listing["audio"]),1)
        self.assertNotIn("source",str(listing))
        self.assertNotIn("private_path",str(listing))
        self.assertEqual(self.studio.calls[-1][:2],("GET","/api/state"))

    def test_duplicate_image_is_revision_checked_and_output_timed(self):
        args={"revision":7,"source_image_id":"b"*32,
              "output_start_ms":1900,"duration_ms":1000,
              "x_pct":65,"y_pct":20,"width_pct":45}
        response=call_tool("pausio_place_existing_image",args,self.studio)
        self.assertEqual(response["project_revision"],8)
        edit=self.studio.calls[-1][2]
        self.assertEqual(edit["type"],"image.overlay.add")
        self.assertEqual(edit["payload"]["image"]["asset_sha256"],"c"*64)
        self.assertEqual(edit["payload"]["image"]["start_ms"],1900)
        self.assertNotEqual(edit["payload"]["image"]["id"],"b"*32)
        before=len(self.studio.calls)
        with self.assertRaises(AssetToolError):
            call_tool("pausio_place_existing_image",args,self.studio)
        self.assertEqual(len(self.studio.calls),before+1)
        with self.assertRaises(AssetToolError):
            call_tool("pausio_place_existing_image",{
                **args,"revision":8,"duration_ms":12000
            },self.studio)
        self.assertEqual(len(self.studio.calls),before+2)

    def test_duplicate_audio_references_existing_bytes(self):
        args={"revision":7,"source_clip_id":"d"*32,
              "output_start_ms":1850,"gain_db":-24}
        answer=call_tool("pausio_place_existing_audio",args,self.studio)
        self.assertEqual(answer["last_command"],"audio.add")
        payload=self.studio.calls[-1][2]["payload"]["clip"]
        self.assertEqual(payload["start_ms"],1850)
        self.assertEqual(payload["asset_sha256"],"e"*64)
        self.assertEqual(payload["gain_db"],-24)

    def test_import_rejects_urls_files_and_large_or_fake_payloads(self):
        valid={"revision":7,"filename":"screenshot.png",
               "origin":"user_supplied","data_base64":base64.b64encode(b"png").decode(),
               "output_start_ms":100}
        for candidate in (
            {**valid,"origin":"stolen"},
            {**valid,"filename":"../steal.png"},
            {**valid,"filename":"/Users/me/private.png"},
            {**valid,"filename":"evil.svg"},
            {**valid,"data_base64":"https://evil.test/asset.png"},
            {**valid,"data_base64":"Z"*800000},
            {**valid,"revision":True},
            {**valid,"arbitrary_path":"/tmp/private"},
        ):
            with self.subTest(candidate=list(candidate)),self.assertRaises(AssetToolError):
                call_tool("pausio_import_image",candidate,self.studio)
        self.assertEqual(self.studio.calls,[])
        self.assertEqual(decode_media(valid,"image")[0],b"png")
        invalid=response_for({
            "jsonrpc":"2.0","id":17,"method":"tools/call",
            "params":{"name":"pausio_import_image",
                      "arguments":{**valid,"filename":"../steal.png"}}
        },self.studio)
        self.assertTrue(invalid["result"]["isError"])

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                         "FFmpeg/FFprobe not installed")
    def test_real_import_and_reuse_image_audio_through_studio(self):
        """No network: actual Studio importer, digest, commands and FFmpeg render."""
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            video=directory/"video.mp4"
            picture=directory/"image.png"
            sound=directory/"sound.mp3"
            subprocess.run([
                "ffmpeg","-hide_banner","-loglevel","error","-nostdin","-y",
                "-f","lavfi","-i","color=c=blue:s=160x288:r=15:d=1.8",
                "-f","lavfi","-i","sine=frequency=440:duration=1.8",
                "-shortest","-c:v","mpeg4","-c:a","aac",str(video)
            ],timeout=35,check=True)
            subprocess.run([
                "ffmpeg","-hide_banner","-loglevel","error","-nostdin","-y",
                "-f","lavfi","-i","color=c=red:s=120x96:r=1:d=1",
                "-frames:v","1","-threads:v","1",str(picture)
            ],timeout=35,check=True)
            subprocess.run([
                "ffmpeg","-hide_banner","-loglevel","error","-nostdin","-y",
                "-f","lavfi","-i","sine=frequency=620:duration=0.42",
                "-c:a","libmp3lame","-q:a","5",str(sound)
            ],timeout=35,check=True)
            workspace=StudioWorkspace()
            server=create_server(port=0,workspace=workspace)
            thread=threading.Thread(target=server.serve_forever,daemon=True)
            thread.start()
            try:
                candidate,label=workspace.begin_import("video.mp4")
                shutil.copyfile(video,candidate)
                workspace.finish_import(candidate,label,probe(candidate))
                client=StudioClient(server.server_port)
                call_tool("pausio_start_pause_analysis",{},client)
                for _ in range(300):
                    status=call_tool("pausio_get_job_status",{},client)
                    if status["job"]["status"] in {"completed","failed"}:break
                    time.sleep(0.1)
                self.assertEqual(status["job"]["status"],"completed",status["job"]["error"])
                state=call_tool("pausio_get_project",{},client)
                image=call_tool("pausio_import_image",{
                    "revision":state["project_revision"],"filename":"image.png",
                    "origin":"created_for_user",
                    "data_base64":base64.b64encode(picture.read_bytes()).decode(),
                    "output_start_ms":100,
                },client)
                self.assertTrue(image["inserted"])
                self.assertEqual(image["asset_sha256"],hashlib.sha256(picture.read_bytes()).hexdigest())
                audio=call_tool("pausio_import_audio",{
                    "revision":image["project_revision"],"filename":"sound.mp3",
                    "origin":"user_supplied",
                    "data_base64":base64.b64encode(sound.read_bytes()).decode(),
                    "output_end_ms":800,
                },client)
                self.assertTrue(audio["inserted"])
                listing=call_tool("pausio_list_assets",{},client)
                self.assertEqual(len(listing["images"]),1)
                self.assertEqual(len(listing["audio"]),1)
                self.assertTrue(listing["images"][0]["available"])
                self.assertTrue(listing["audio"][0]["available"])
                dupe=call_tool("pausio_place_existing_image",{
                    "revision":audio["project_revision"],
                    "source_image_id":image["asset_id"],
                    "output_start_ms":1100,"duration_ms":500,
                    "x_pct":40,"y_pct":20,"width_pct":40
                },client)
                self.assertEqual(dupe["last_command"],"image.overlay.add")
                reused=call_tool("pausio_place_existing_audio",{
                    "revision":dupe["project_revision"],
                    "source_clip_id":audio["asset_id"],
                    "output_start_ms":900,"gain_db":-22
                },client)
                self.assertEqual(reused["last_command"],"audio.add")
                self.assertFalse(reused["approved"])
                preview=call_tool("pausio_preview_range",{
                    "range_start_ms":300,"range_duration_ms":700
                },client)
                self.assertEqual(preview["job"]["kind"],"preview_range")
                for _ in range(300):
                    status=call_tool("pausio_get_job_status",{},client)
                    if status["job"]["status"] in {"completed","failed"}:break
                    time.sleep(0.1)
                self.assertEqual(status["job"]["status"],"completed",status["job"]["error"])
                self.assertTrue((workspace.directory/"preview-range.mp4").exists())
                self.assertTrue(probe(workspace.directory/"preview-range.mp4").has_audio)
            finally:
                server.shutdown();server.server_close()
                thread.join(timeout=3)
                workspace.close()
