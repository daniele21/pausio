"""Agent audio sampling: privacy, actual WAV, preview timing, resource limits."""
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
import wave
from pathlib import Path
from unittest.mock import patch

from pausio.local_mcp import StudioClient, MCPToolError, call_tool, response_for, TOOLS
from pausio.mcp_audio_observation import AudioContextError
from pausio.media import probe
from pausio.studio import StudioWorkspace, create_server


def args(state,scope="source",start=200,duration=1000):
    return {"revision":state["project_revision"],"media_id":state["media_id"],
            "scope":scope,"start_ms":start,"duration_ms":duration}


def fixture_wav() -> bytes:
    from pausio.audio_observation import SAMPLE_RATE
    out=io.BytesIO()
    with wave.open(out,"wb") as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(SAMPLE_RATE)
        wav.writeframes(b"\x00\x00\x00\x20"*800)
    return out.getvalue()


class FakeStudio:
    def __init__(self):
        self.state={"media_id":"a"*32,"project_revision":3,
                    "audio_sharing_enabled":False,
                    "preview_ready":False,"preview_range_ready":False}
        self.reads=[]

    def request(self,method,path,payload=None):
        if (method,path)!=("GET","/api/state"):
            raise AssertionError("Unexpected Studio request")
        return dict(self.state)

    def read_audio(self,**kwargs):
        self.reads.append(kwargs)
        return fixture_wav()


class AudioMCPBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.studio=FakeStudio()
        self.good=args(self.studio.state)

    def test_opt_in_and_true_audio_block_without_leaking_base64_in_metadata(self):
        self.assertIn("pausio_get_audio_context",{x["name"] for x in TOOLS})
        with self.assertRaises(AudioContextError):
            call_tool("pausio_get_audio_context",self.good,self.studio)
        self.assertEqual(self.studio.reads,[])
        self.studio.state["audio_sharing_enabled"]=True
        m=response_for({"jsonrpc":"2.0","id":4,"method":"tools/call",
                        "params":{"name":"pausio_get_audio_context",
                                  "arguments":self.good}},self.studio)
        payload=m["result"]
        self.assertFalse(payload["isError"])
        self.assertEqual(payload["content"][1]["type"],"audio")
        self.assertEqual(payload["content"][1]["mimeType"],"audio/wav")
        self.assertNotIn("data_base64",str(payload["structuredContent"]))
        self.assertEqual(payload["structuredContent"]["levels"]["sample_rate_hz"],16000)
        self.assertGreater(payload["structuredContent"]["levels"]["peak_dbfs"],-120)

    def test_unsafe_parameters_rejected_before_audio_read(self):
        self.studio.state["audio_sharing_enabled"]=True
        for bad in [
            {**self.good,"revision":True},{**self.good,"revision":4},
            {**self.good,"media_id":"b"*32},{**self.good,"media_id":"../x"},
            {**self.good,"scope":"file:///etc/passwd"},
            {**self.good,"start_ms":True},{**self.good,"start_ms":-1},
            {**self.good,"duration_ms":True},{**self.good,"duration_ms":6500},
            {**self.good,"duration_ms":400},{**self.good,"url":"https://example.org"},
        ]:
            with self.subTest(bad=bad),self.assertRaises(AudioContextError):
                call_tool("pausio_get_audio_context",bad,self.studio)
        self.assertEqual(self.studio.reads,[])
        for scope,flag in [("preview","preview_ready"),
                           ("range","preview_range_ready")]:
            with self.assertRaises(AudioContextError):
                call_tool("pausio_get_audio_context",
                          {**self.good,"scope":scope},self.studio)
            self.studio.state[flag]=True
            call_tool("pausio_get_audio_context",
                      {**self.good,"scope":scope},self.studio)
            self.studio.state[flag]=False


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                     "Real FFmpeg needed for audio observation")
class AudioObservationHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)
        source=self.path/"original.mp4"
        subprocess.run([
            "ffmpeg","-hide_banner","-loglevel","error","-nostdin","-y",
            "-f","lavfi","-i","color=c=blue:s=160x288:r=15:d=3.4",
            "-f","lavfi","-i","sine=frequency=440:duration=3.4",
            "-shortest","-c:v","mpeg4","-c:a","aac",str(source),
        ],check=True,timeout=40)
        self.workspace=StudioWorkspace()
        candidate,label=self.workspace.begin_import("original.mp4")
        shutil.copyfile(source,candidate)
        self.workspace.finish_import(candidate,label,probe(candidate))
        self.server=create_server(port=0,workspace=self.workspace)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.base=f"http://127.0.0.1:{self.server.server_port}"
        self.client=StudioClient(self.server.server_port)
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def tearDown(self):
        self.server.shutdown();self.server.server_close()
        self.thread.join(timeout=3);self.workspace.close();self.tmp.cleanup()

    def grant(self,enabled,*,origin=True):
        headers={"Content-Type":"application/json","X-Pausio-Client":"studio"}
        if origin:headers["Origin"]=self.base
        req=urllib.request.Request(
            self.base+"/api/observation/audio-consent",
            method="POST",headers=headers,
            data=json.dumps({"enabled":enabled}).encode())
        try:
            with self.opener.open(req,timeout=30) as resp:
                return resp.status,json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return e.code,json.loads(e.read())

    def test_mcp_cannot_turn_on_audio_or_observe_without_separate_optin(self):
        state=self.client.request("GET","/api/state")
        self.assertFalse(state["audio_sharing_enabled"])
        self.assertFalse(state["visual_sharing_enabled"])
        with self.assertRaises(AudioContextError):
            call_tool("pausio_get_audio_context",args(state),self.client)
        self.assertEqual(self.grant(True,origin=False)[0],400)
        self.assertFalse(self.workspace.audio_sharing_enabled)
        self.assertEqual(self.grant(True)[0],200)
        self.assertFalse(self.workspace.visual_sharing_enabled)
        r=response_for({"jsonrpc":"2.0","id":7,"method":"tools/call",
                        "params":{"name":"pausio_get_audio_context",
                                  "arguments":args(state)}},self.client)
        self.assertFalse(r["result"]["isError"])
        self.assertEqual(r["result"]["content"][1]["type"],"audio")
        levels=r["result"]["structuredContent"]["levels"]
        self.assertGreater(levels["peak_dbfs"],-25)
        self.assertLessEqual(levels["peak_dbfs"],0.1)
        with wave.open(io.BytesIO(self.client.read_audio(**args(state))),"rb") as wav:
            self.assertEqual((wav.getframerate(),wav.getnchannels(),wav.getsampwidth()),
                             (16000,1,2))
            self.assertGreater(wav.getnframes(),8000)
        self.assertEqual(self.grant(False)[0],200)
        with self.assertRaises(AudioContextError):
            call_tool("pausio_get_audio_context",args(state),self.client)
        self.assertEqual(self.grant(True)[0],200)
        candidate,label=self.workspace.begin_import("new.mp4")
        shutil.copyfile(self.path/"original.mp4",candidate)
        self.workspace.finish_import(candidate,label,probe(candidate))
        self.assertFalse(self.workspace.audio_sharing_enabled)
        with self.assertRaises(AudioContextError):
            call_tool("pausio_get_audio_context",args(state),self.client)

    def test_actual_short_preview_audio_and_out_of_range(self):
        self.assertEqual(self.grant(True)[0],200)
        before=self.client.request("GET","/api/state")
        call_tool("pausio_apply_command",{"revision":before["project_revision"],
            "type":"timeline.keep_all","payload":{}},self.client)
        current=self.client.request("GET","/api/state")
        with self.assertRaises(AudioContextError):
            call_tool("pausio_get_audio_context",
                      args(current,"range",500,800),self.client)
        call_tool("pausio_preview_range",{
            "range_start_ms":500,"range_duration_ms":2000},self.client)
        for _ in range(300):
            state=self.client.request("GET","/api/state")
            if state["job"]["status"] in {"completed","failed"}:break
            time.sleep(0.1)
        self.assertEqual(state["job"]["status"],"completed",state["job"])
        self.assertTrue(state["preview_range_ready"])
        output=call_tool("pausio_get_audio_context",args(state,"range",700,1000),
                         self.client)
        self.assertEqual(output["timebase"],"edited_output")
        self.assertGreater(output["levels"]["actual_duration_ms"],700)
        with self.assertRaisesRegex(MCPToolError,"fuori"):
            self.client.read_audio(**args(state,"range",2200,1000))
        # A new edit cannot read audio from a now-stale preview.
        call_tool("pausio_apply_command",{
            "revision":state["project_revision"],"type":"caption.clear","payload":{}
        },self.client)
        with self.assertRaises(AudioContextError):
            call_tool("pausio_get_audio_context",args(state,"range",700,1000),
                      self.client)

    def test_quota_and_revocation_after_extraction(self):
        self.assertEqual(self.grant(True)[0],200)
        state=self.client.request("GET","/api/state")
        with patch("pausio.studio.audio_wav",return_value=fixture_wav()) as ffmpeg:
            for _ in range(4):
                self.client.read_audio(**args(state))
            with self.assertRaisesRegex(MCPToolError,"4 estratti"):
                self.client.read_audio(**args(state))
            self.assertEqual(ffmpeg.call_count,4)
        self.assertEqual(self.grant(False)[0],200)
        self.assertEqual(self.workspace._audio_observation_times,[])
