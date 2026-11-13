"""Privacy and pixel truth: actual MCP frames, consent and FFmpeg bounds."""
from __future__ import annotations

import io
import json
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from pausio.local_mcp import (
    StudioClient, MCPToolError, call_tool, response_for, TOOLS
)
from pausio.mcp_observation import VisualContextError
from pausio.media import probe
from pausio.studio import StudioWorkspace, StudioError, create_server


def arguments(state, *, scope="source", times=(400,)):
    return {"revision":state["project_revision"],"media_id":state["media_id"],
            "scope":scope,"times_ms":list(times)}


class FakeVisualStudio:
    def __init__(self):
        self.state={"media_id":"a"*32,"project_revision":7,
                    "visual_sharing_enabled":False,"preview_ready":False,
                    "preview_range_ready":False}
        self.queries=[]

    def request(self, method, path, payload=None):
        if method != "GET" or path != "/api/state":
            raise AssertionError("unexpected Studio operation")
        return dict(self.state)

    def read_frame(self, **args):
        self.queries.append(args)
        return b"\xff\xd8safe-fixture\xff\xd9"


class VisualToolBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.studio=FakeVisualStudio()
        self.args=arguments(self.studio.state)

    def test_capability_is_a_readonly_optin_image_tool(self):
        tools={t["name"]:t for t in TOOLS}
        self.assertTrue(tools["pausio_get_visual_context"]["annotations"]["readOnlyHint"])
        self.assertIn("pausio_get_visual_context",tools)
        with self.assertRaisesRegex(VisualContextError,"Abilita"):
            call_tool("pausio_get_visual_context",self.args,self.studio)
        self.assertEqual(self.studio.queries,[])
        denied=response_for({"jsonrpc":"2.0","id":1,"method":"tools/call",
            "params":{"name":"pausio_get_visual_context",
                      "arguments":self.args}},self.studio)
        self.assertTrue(denied["result"]["isError"])
        self.assertFalse(any(c.get("type")=="image" for c in denied["result"]["content"]))

    def test_image_content_blocks_not_embedded_in_structured_metadata(self):
        self.studio.state["visual_sharing_enabled"]=True
        args={**self.args,"times_ms":[100,450]}
        response=response_for({"jsonrpc":"2.0","id":4,"method":"tools/call",
            "params":{"name":"pausio_get_visual_context","arguments":args}},self.studio)
        result=response["result"]
        self.assertFalse(result["isError"])
        self.assertEqual(result["structuredContent"]["timestamps_ms"],[100,450])
        self.assertNotIn("data_base64",str(result["structuredContent"]))
        imgs=[x for x in result["content"] if x["type"]=="image"]
        self.assertEqual(len(imgs),2)
        self.assertTrue(all(x["mimeType"]=="image/jpeg" for x in imgs))
        self.assertEqual(len(self.studio.queries),2)
        self.assertEqual(self.studio.queries[0]["scope"],"source")

    def test_bad_fields_no_paths_no_url_no_stale_state(self):
        self.studio.state["visual_sharing_enabled"]=True
        good=self.args
        for bad in (
            {**good,"revision":True},
            {**good,"revision":8},
            {**good,"media_id":"b"*32},
            {**good,"scope":"https://evil.invalid"},
            {**good,"scope":"file:///Users/secret"},
            {**good,"times_ms":[]},
            {**good,"times_ms":[10,10]},
            {**good,"times_ms":[200,100]},
            {**good,"times_ms":[0,1,2,3,4]},
            {**good,"times_ms":[True]},
            {**good,"times_ms":[-1]},
            {**good,"consent":True},
        ):
            with self.subTest(bad=bad),self.assertRaises(VisualContextError):
                call_tool("pausio_get_visual_context",bad,self.studio)
        self.assertEqual(self.studio.queries,[])
        for scope,flag in (("preview","preview_ready"),
                           ("range","preview_range_ready")):
            with self.assertRaises(VisualContextError):
                call_tool("pausio_get_visual_context",
                          {**good,"scope":scope},self.studio)
            self.studio.state[flag]=True
            call_tool("pausio_get_visual_context",
                      {**good,"scope":scope},self.studio)
            self.studio.state[flag]=False


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                     "FFmpeg / FFprobe required for real visual observation")
class VisualObservationHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        original=self.root/"recording.mp4"
        subprocess.run([
            "ffmpeg","-hide_banner","-loglevel","error","-nostdin","-y",
            "-f","lavfi","-i","color=c=blue:s=160x288:r=15:d=3.4",
            "-f","lavfi","-i","sine=frequency=440:duration=3.4",
            "-shortest","-c:v","mpeg4","-c:a","aac",str(original)
        ],timeout=45,check=True)
        self.workspace=StudioWorkspace()
        candidate,label=self.workspace.begin_import("recording.mp4")
        shutil.copyfile(original,candidate)
        self.workspace.finish_import(candidate,label,probe(candidate))
        self.server=create_server(port=0,workspace=self.workspace)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.base=f"http://127.0.0.1:{self.server.server_port}"
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.client=StudioClient(self.server.server_port)

    def tearDown(self):
        self.server.shutdown();self.server.server_close()
        self.thread.join(timeout=3);self.workspace.close();self.temp.cleanup()

    def grant(self,enabled,*,origin=True):
        body=json.dumps({"enabled":enabled}).encode()
        headers={"X-Pausio-Client":"studio","Content-Type":"application/json"}
        if origin:headers["Origin"]=self.base
        request=urllib.request.Request(self.base+"/api/observation/consent",
                                       method="POST",data=body,headers=headers)
        try:
            with self.opener.open(request,timeout=25) as r:
                return r.status,json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code,json.loads(e.read())

    def test_consent_is_ui_only_local_volatile_and_source_frame_is_real(self):
        original=self.client.request("GET","/api/state")
        self.assertFalse(original["visual_sharing_enabled"])
        args=arguments(original)
        with self.assertRaises(VisualContextError):
            call_tool("pausio_get_visual_context",args,self.client)
        status,error=self.grant(True,origin=False)
        self.assertEqual(status,400,error)
        self.assertFalse(self.workspace.visual_sharing_enabled)
        self.assertEqual(self.grant(True)[0],200)
        result=call_tool("pausio_get_visual_context",args,self.client)
        self.assertEqual(result["scope"],"source")
        self.assertEqual(result["frames"][0]["at_ms"],400)
        packed=response_for({"jsonrpc":"2.0","id":1,"method":"tools/call",
            "params":{"name":"pausio_get_visual_context","arguments":args}},self.client)
        self.assertEqual(packed["result"]["content"][-1]["type"],"image")
        self.assertEqual(self.grant(False)[0],200)
        with self.assertRaises(VisualContextError):
            call_tool("pausio_get_visual_context",args,self.client)
        self.assertEqual(self.grant(True)[0],200)
        candidate,label=self.workspace.begin_import("recording-new.mp4")
        shutil.copyfile(self.root/"recording.mp4",candidate)
        self.workspace.finish_import(candidate,label,probe(candidate))
        self.assertFalse(self.workspace.visual_sharing_enabled)
        with self.assertRaises(VisualContextError):
            call_tool("pausio_get_visual_context",args,self.client)

    def test_preview_range_is_real_and_revision_gated(self):
        self.assertEqual(self.grant(True)[0],200)
        state=self.client.request("GET","/api/state")
        call_tool("pausio_apply_command",{
            "revision":state["project_revision"],"type":"timeline.keep_all",
            "payload":{}},self.client)
        next_state=self.client.request("GET","/api/state")
        from pausio.scene_templates import TEMPLATES
        scene={
            "id":"a"*32,"template":"stat_reveal","start_ms":0,
            "duration_ms":2500,"accent":"mint",
            "content":{x["key"]:x["default"]
                       for x in TEMPLATES["stat_reveal"]["fields"]}
        }
        call_tool("pausio_apply_command",{
            "revision":next_state["project_revision"],
            "type":"scene.template.add","payload":{"scene":scene}},self.client)
        current=self.client.request("GET","/api/state")
        with self.assertRaises(VisualContextError):
            call_tool("pausio_get_visual_context",
                      arguments(current,scope="range"),self.client)
        call_tool("pausio_preview_range",{
            "range_start_ms":0,"range_duration_ms":2700},self.client)
        for _ in range(300):
            status=self.client.request("GET","/api/state")
            if status["job"]["status"] in {"completed","failed"}:break
            time.sleep(0.1)
        self.assertEqual(status["job"]["status"],"completed",status["job"])
        self.assertTrue(status["preview_range_ready"])
        result=call_tool("pausio_get_visual_context",{
            **arguments(status,scope="range"),"times_ms":[500,1400]
        },self.client)
        self.assertEqual(len(result["frames"]),2)
        self.assertEqual(result["timebase"],"edited_output")
        self.assertNotEqual(result["frames"][0]["data_base64"],
                            call_tool("pausio_get_visual_context",
                                      arguments(status,scope="source",times=(500,)),
                                      self.client)["frames"][0]["data_base64"])
        # Changing a scene invalidates all old rendered preview frames.
        self.assertEqual(self.grant(True)[0],200)
        call_tool("pausio_apply_command",{
            "revision":status["project_revision"],
            "type":"scene.template.remove","payload":{"scene_id":scene["id"]}},
            self.client)
        with self.assertRaises(VisualContextError):
            call_tool("pausio_get_visual_context",
                      arguments(status,scope="range"),self.client)

    def test_per_minute_rate_limit_is_enforced_before_ffmpeg(self):
        self.assertEqual(self.grant(True)[0],200)
        state=self.client.request("GET","/api/state")
        with patch("pausio.studio.frame_jpeg",return_value=b"\xff\xd8sample\xff\xd9") as extract:
            for _ in range(12):
                payload=self.client.read_frame(scope="source",at_ms=200,
                     revision=state["project_revision"],media_id=state["media_id"])
                self.assertEqual(payload,b"\xff\xd8sample\xff\xd9")
            with self.assertRaisesRegex(MCPToolError,"12"):
                self.client.read_frame(scope="source",at_ms=200,
                     revision=state["project_revision"],media_id=state["media_id"])
            self.assertEqual(extract.call_count,12)
        self.assertEqual(self.grant(False)[0],200)
        self.assertEqual(self.grant(True)[0],200)
        self.assertEqual(self.workspace._observation_times,[])
