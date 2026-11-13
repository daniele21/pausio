"""Local MCP bridge tests: no inference API, no unreviewed export."""
from __future__ import annotations

import io
import json
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path

from pausio.local_mcp import (
    StudioClient, MCPToolError, TOOLS, call_tool, response_for, serve_stdio
)
from pausio.studio import StudioWorkspace, create_server
from pausio.media import probe


class FakeStudio:
    def __init__(self):
        self.requests = []

    def request(self, method, path, payload=None):
        self.requests.append((method, path, payload))
        if path == "/api/editorial/suggest":
            return {"engine": "pausio-editorial-v1",
                    "preset": payload["preset"],
                    "base_revision": payload["revision"], "candidates": []}
        if path == "/api/visual-fx/suggest":
            return {"engine": "pausio.visualfx.cut-phrase-v1", "preset": payload["preset"],
                    "base_revision": payload["revision"], "candidates": [],
                    "media_sha256": "a" * 64}
        if path == "/api/command":
            return {"project_revision": 5, "last_command": "caption.correct",
                    "approved": False, "preview_ready": False}
        if path == "/api/jobs":
            return {"job": {"status": "running", "kind": payload["kind"]},
                    "preview_ready": False}
        return {"project_revision": 4, "media_id": "test",
                "approved": getattr(self, "approved", False),
                "export_ready": False, "preview_range_ready": False,
                "file": "take.mp4", "recovery_warning": "/Users/private/path",
                "secret_local_key": "must-never-be-visible",
                "transcript": {"segments": [{"text": "ciao"}]},
                "job": {"status": "idle"}, "preview_ready": False}


class LocalMCPProtocolTests(unittest.TestCase):
    def setUp(self):
        self.studio = FakeStudio()

    def test_initialize_and_tool_list(self):
        initialized = response_for({"jsonrpc": "2.0", "id": 1,
                                    "method": "initialize", "params": {}}, self.studio)
        self.assertEqual(initialized["result"]["protocolVersion"], "2025-03-26")
        listing = response_for({"jsonrpc": "2.0", "id": "list",
                                "method": "tools/list"}, self.studio)
        tools = {t["name"] for t in listing["result"]["tools"]}
        self.assertIn("pausio_get_project", tools)
        self.assertIn("pausio_render_preview", tools)
        self.assertIn("pausio_get_capabilities", tools)
        self.assertIn("pausio_get_scene_templates", tools)
        self.assertIn("pausio_suggest_editorial", tools)
        self.assertIn("pausio_preview_range", tools)
        self.assertIn("pausio_render_approved_video", tools)
        self.assertNotIn("pausio_export", tools)
        self.assertNotIn("pausio_approve", tools)
        self.assertEqual(len(tools), len(TOOLS))
        self.assertIsNone(response_for({"jsonrpc": "2.0",
                                        "method": "notifications/initialized"}, self.studio))

    def test_read_project_omits_transcript_until_requested(self):
        project = call_tool("pausio_get_project", {}, self.studio)
        self.assertNotIn("transcript", project)
        self.assertNotIn("secret_local_key", project)
        self.assertNotIn("recovery_warning", project)
        self.assertEqual(project["project_revision"], 4)
        transcript = call_tool("pausio_get_transcript", {}, self.studio)
        self.assertEqual(transcript["transcript"]["segments"][0]["text"], "ciao")

    def test_scene_template_catalog_and_typed_agent_command(self):
        tools=call_tool("pausio_get_scene_templates",{},self.studio)
        self.assertEqual(tools["timebase"],"output")
        self.assertEqual([x["id"] for x in tools["templates"]],
                         ["stat_reveal","permission_dialog","code_highlight"])
        self.assertEqual(self.studio.requests,[])
        for kind in ("scene.template.add","scene.template.update",
                     "scene.template.remove"):
            request={"revision":4,"type":kind,"payload":{"scene":{}}}
            result=call_tool("pausio_apply_command",request,self.studio)
            self.assertFalse(result["approved"])
            self.assertEqual(self.studio.requests[-1],
                             ("POST","/api/command",request))
        for invalid in ({"x":0},None,[]):
            with self.assertRaises(MCPToolError):
                call_tool("pausio_get_scene_templates",invalid,self.studio)

    def test_typed_edit_revision_passthrough_and_preview(self):
        request = {"revision": 4, "type": "caption.correct",
                   "payload": {"caption_id": "a" * 32, "text": "Corretto"}}
        changed = call_tool("pausio_apply_command", request, self.studio)
        self.assertEqual(changed["project_revision"], 5)
        self.assertFalse(changed["approved"])
        self.assertEqual(self.studio.requests[-1],
                         ("POST", "/api/command", request))
        preview = call_tool("pausio_render_preview", {}, self.studio)
        self.assertEqual(preview["job"]["kind"], "preview")
        self.assertEqual(self.studio.requests[-1][1], "/api/jobs")

    def test_visual_fx_proposals_are_read_only_and_edits_are_allowlisted(self):
        response=call_tool("pausio_suggest_visual_fx",
                           {"revision":4,"preset":"naturale"},self.studio)
        self.assertEqual(response["candidates"],[])
        self.assertEqual(self.studio.requests[-1],(
            "POST","/api/visual-fx/suggest",{"revision":4,"preset":"naturale"}))
        for candidate in ({"revision":4,"preset":"drop_tables"},
                          {"revision":True,"preset":"naturale"},
                          {"revision":4,"preset":"naturale","url":"http://evil.test"}):
            with self.assertRaises(MCPToolError):
                call_tool("pausio_suggest_visual_fx",candidate,self.studio)
        for kind in ("graphic.overlay.add","graphic.overlay.update",
                     "graphic.overlay.remove","image.overlay.update",
                     "image.overlay.remove","audio.mixer.configure",
                     "audio.clip.mix","caption.retime","caption.clear",
                     "segment.insert","segment.remove","timeline.keep_all",
                     "video.transform.add","video.transform.update",
                     "video.transform.remove", "video.transition.add",
                     "video.transition.update", "video.transition.remove"):
            request={"revision":4,"type":kind,"payload":{}}
            changed=call_tool("pausio_apply_command",request,self.studio)
            self.assertEqual(changed["project_revision"],5)
            self.assertEqual(self.studio.requests[-1],("POST","/api/command",request))
        self.assertNotIn("pausio_export", {t["name"] for t in TOOLS})

    def test_agent_cannot_approve_export_or_exfiltrate_via_tools(self):
        for operation in ("timeline.approve", "history.undo", "audio.add",
                          "image.overlay.add",
                          "project.import", "video.export"):
            with self.assertRaises(MCPToolError):
                call_tool("pausio_apply_command",
                          {"revision": 4, "type": operation, "payload": {}}, self.studio)
        for bad in (None, [], {"oops": True}):
            with self.assertRaises(MCPToolError):
                call_tool("pausio_get_project", bad, self.studio)
        with self.assertRaises(MCPToolError):
            call_tool("pausio_unsupported", {}, self.studio)
        with self.assertRaises(ValueError):
            StudioClient(65536)

    def test_capability_report_is_truthful_and_no_implicit_asset_import(self):
        inventory = call_tool("pausio_get_capabilities", {}, self.studio)
        self.assertEqual(inventory["transport"], "local_stdio_only")
        self.assertIn("graphic.overlay.add", inventory["allowed_edit_commands"])
        self.assertIn("image.overlay.update", inventory["allowed_edit_commands"])
        self.assertNotIn("timeline.approve", inventory["allowed_edit_commands"])
        self.assertNotIn("audio.add", inventory["allowed_edit_commands"])
        self.assertIn("video B-roll files", inventory["unsupported"])
        self.assertEqual(self.studio.requests, [])

    def test_editorial_preview_range_and_offline_transcription(self):
        item=call_tool("pausio_suggest_editorial", {
            "revision":4, "preset":"clean_tech"}, self.studio)
        self.assertEqual(item["preset"], "clean_tech")
        self.assertEqual(self.studio.requests[-1], ("POST", "/api/editorial/suggest",
            {"revision":4, "preset":"clean_tech"}))
        for settings in ({"revision":True,"preset":"educational"},
                         {"revision":4,"preset":"nonexistent"},
                         {"revision":4,"preset":"educational","url":"unsafe"}):
            with self.assertRaises(MCPToolError):
                call_tool("pausio_suggest_editorial", settings, self.studio)
        clip=call_tool("pausio_preview_range", {
            "range_start_ms":500, "range_duration_ms":2500}, self.studio)
        self.assertEqual(clip["job"]["kind"], "preview_range")
        self.assertEqual(self.studio.requests[-1], ("POST", "/api/jobs", {
            "kind":"preview_range","range_start_ms":500,"range_duration_ms":2500}))
        for bad in ({"range_start_ms": True,"range_duration_ms":500},
                    {"range_start_ms":-1,"range_duration_ms":500},
                    {"range_start_ms":0,"range_duration_ms":10001},
                    {"range_start_ms":0,"range_duration_ms":500,"extra":0}):
            with self.assertRaises(MCPToolError):
                call_tool("pausio_preview_range",bad,self.studio)
        call_tool("pausio_start_transcription", {}, self.studio)
        self.assertEqual(self.studio.requests[-1],
                         ("POST", "/api/jobs", {"kind": "transcribe"}))

    def test_final_render_requires_prior_manual_approval(self):
        with self.assertRaisesRegex(MCPToolError, "Conferma"):
            call_tool("pausio_render_approved_video", {}, self.studio)
        self.assertEqual(self.studio.requests[-1][1],"/api/state")
        self.studio.approved=True
        reply=call_tool("pausio_render_approved_video", {}, self.studio)
        self.assertEqual(reply["job"]["kind"],"render")
        self.assertEqual(self.studio.requests[-1],
                         ("POST", "/api/jobs", {"kind": "render"}))
        self.assertIn("Mac",reply["message"])

    def test_stdio_jsonrpc_wire_and_notifications(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ]
        inp = io.StringIO("".join(json.dumps(x) + "\n" for x in lines))
        out = io.StringIO()
        # Avoid a network round trip: the above only tests MCP handshakes.
        serve_stdio(8765, inp, out)
        replies = [json.loads(x) for x in out.getvalue().splitlines()]
        self.assertEqual(len(replies), 2)
        self.assertEqual([x["id"] for x in replies], [1, 2])
        self.assertIn("tools", replies[1]["result"])

    def test_tool_call_wire_response(self):
        reply = response_for({
            "jsonrpc": "2.0", "id": 8, "method": "tools/call",
            "params": {"name": "pausio_get_project", "arguments": {}}
        }, self.studio)
        self.assertFalse(reply["result"]["isError"])
        self.assertNotIn("transcript", reply["result"]["structuredContent"])
        self.assertEqual(reply["id"], 8)


class LiveLoopbackMCPTests(unittest.TestCase):
    def test_reads_actual_running_studio_not_a_mock(self):
        workspace = StudioWorkspace()
        server = create_server(port=0, workspace=workspace)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            client = StudioClient(server.server_port)
            actual = call_tool("pausio_get_project", {}, client)
            self.assertIn("project_revision", actual)
            self.assertIsNone(actual["file"])
            status = call_tool("pausio_get_job_status", {}, client)
            self.assertEqual(status["job"]["status"], "idle")
            with self.assertRaisesRegex(MCPToolError, "Conferma"):
                call_tool("pausio_render_approved_video", {}, client)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=3)
            workspace.close()


    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                         "FFmpeg/FFprobe not installed")
    def test_local_mcp_edits_real_studio_previews_and_renders_only_after_approval(self):
        """Synthetic full path: MCP -> actual Studio reducer -> actual FFmpeg."""
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "speech-test.mp4"
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                "-f", "lavfi", "-i", "color=c=blue:s=160x288:r=15:d=1.7",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=1.7",
                "-shortest", "-c:v", "mpeg4", "-c:a", "aac", str(source)
            ], timeout=45, check=True)
            workspace = StudioWorkspace()
            server = create_server(port=0, workspace=workspace)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                candidate, label = workspace.begin_import("speech-test.mp4")
                shutil.copyfile(source, candidate)
                workspace.finish_import(candidate, label, probe(candidate))
                client = StudioClient(server.server_port)

                capabilities = call_tool("pausio_get_capabilities", {}, client)
                self.assertIn("graphic.overlay.add", capabilities["allowed_edit_commands"])
                call_tool("pausio_start_pause_analysis", {}, client)

                def completed(kind):
                    for _ in range(300):
                        status = call_tool("pausio_get_job_status", {}, client)
                        job = status["job"]
                        if job["kind"] == kind and job["status"] in {"failed","completed"}:
                            self.assertEqual(job["status"], "completed",job["error"])
                            return status
                        time.sleep(0.1)
                    self.fail("Timed out waiting for Pausio MCP job "+kind)

                completed("analyze")
                project = call_tool("pausio_get_project", {}, client)
                self.assertTrue(project["plan"])
                revised = call_tool("pausio_apply_command", {
                    "revision": project["project_revision"],
                    "type": "timeline.keep_all", "payload": {}
                }, client)
                self.assertGreater(revised["project_revision"], project["project_revision"])
                self.assertFalse(revised["approved"])
                with self.assertRaises(MCPToolError):
                    call_tool("pausio_render_approved_video", {}, client)

                clip = call_tool("pausio_preview_range", {
                    "range_start_ms":0, "range_duration_ms":700
                }, client)
                self.assertEqual(clip["job"]["kind"], "preview_range")
                self.assertTrue(completed("preview_range")["preview_range_ready"])
                self.assertTrue((workspace.directory / "preview-range.mp4").is_file())

                # Represents the human's explicit UI confirmation, not an MCP tool.
                state = workspace.snapshot()
                workspace.command({"revision":state["project_revision"],
                                   "type":"timeline.approve","payload":{}})
                render = call_tool("pausio_render_approved_video", {}, client)
                self.assertEqual(render["job"]["kind"], "render")
                self.assertTrue(completed("render")["export_ready"])
                final = workspace.directory / "export.mp4"
                self.assertTrue(final.is_file())
                self.assertTrue(probe(final).duration_ms > 500)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)
                workspace.close()


if __name__ == "__main__":
    unittest.main()
