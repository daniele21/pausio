"""Local HTTP Studio integration tests; no browser automation or real creator media."""

from __future__ import annotations

import errno
import json
from http.server import BaseHTTPRequestHandler
import socket
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import call, patch, sentinel, Mock

from pausio.studio import (STATIC_DIR, StudioWorkspace, StudioHandler, StudioServer,
                           MAX_ACTIVE_CONNECTIONS, SOCKET_IDLE_TIMEOUT_S,
                           STUDIO_LISTEN_BACKLOG, create_server, run_studio)
from pausio.media import waveform_envelope, probe


class StudioHttpTests(unittest.TestCase):
    def setUp(self):
        self.workspace = StudioWorkspace()
        self.server = create_server(port=0, workspace=self.workspace)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:" + str(self.server.server_port)
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.workspace.close()

    def request(self, method, path, data=None, headers=None):
        args = dict(method=method, headers=headers or {})
        if data is not None:
            args["data"] = data
        req = urllib.request.Request(self.base + path, **args)
        try:
            with self.opener.open(req, timeout=20) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as error:
            return error.code, dict(error.headers), error.read()

    def post(self, endpoint, body):
        return self.request(
            "POST", endpoint, json.dumps(body).encode("utf-8"),
            {"Content-Type": "application/json", "X-Pausio-Client": "studio",
             "Origin": self.base},
        )

    def get_state(self):
        status, _, data = self.request("GET", "/api/state")
        self.assertEqual(status, 200)
        return json.loads(data)

    def await_job(self, kind):
        for _ in range(300):
            state = self.get_state()
            if state["job"]["status"] in {"completed", "failed"}:
                self.assertEqual(state["job"]["kind"], kind)
                self.assertEqual(state["job"]["status"], "completed", state["job"]["error"])
                return state
            time.sleep(0.1)
        self.fail(kind + " did not complete in time")

    def test_assets_are_served_with_security_headers(self):
        for path, snippet in (
            ("/", b"Studio"),
            ("/styles.css", b"focus-visible"),
            ("/app.js", b"/api/command"),
        ):
            status, headers, content = self.request("GET", path)
            self.assertEqual(status, 200)
            self.assertIn(snippet, content)
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.assertEqual(headers["Cross-Origin-Resource-Policy"], "same-origin")
            self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertIn(b'role="tablist"', self.request("GET", "/")[2])
        self.assertIn(b'id="approve-action"', self.request("GET", "/")[2])

    def test_browser_favicon_request_is_not_a_spurious_404(self):
        for method in ("GET", "HEAD"):
            with self.subTest(method=method):
                status, headers, body = self.request(method, "/favicon.ico")
                self.assertEqual(status, 204)
                self.assertEqual(body, b"")
                self.assertEqual(headers["Content-Length"], "0")
                self.assertEqual(headers["Cross-Origin-Resource-Policy"], "same-origin")
        self.assertEqual(self.get_state()["job"]["status"], "idle")
        self.assertEqual(self.request("GET", "/unknown-resource")[0], 404)

    def test_http_client_disconnects_are_silent_but_other_failures_propagate(self):
        for exception in (
            ConnectionResetError(54, "Connection reset by peer"),
            ConnectionAbortedError(53, "Software caused connection abort"),
            BrokenPipeError(32, "Broken pipe"),
            TimeoutError("read idle socket timeout"),
        ):
            with self.subTest(exception=type(exception).__name__):
                handler = object.__new__(StudioHandler)
                handler.close_connection = False
                with patch.object(
                    BaseHTTPRequestHandler, "handle_one_request", side_effect=exception
                ):
                    handler.handle_one_request()
                self.assertTrue(handler.close_connection)

        # Do not blanket-catch arbitrary exceptions, e.g. an application bug.
        handler = object.__new__(StudioHandler)
        with patch.object(
            BaseHTTPRequestHandler, "handle_one_request",
            side_effect=RuntimeError("application failure")
        ):
            with self.assertRaisesRegex(RuntimeError, "application failure"):
                handler.handle_one_request()

    def test_dns_rebinding_host_is_rejected_for_read_head_and_write(self):
        """Host must be checked for GET too: Origin-only checks cannot protect reads."""
        cases = [
            ("GET", "/api/state", None, {"Host": "attacker.example"}),
            ("GET", "/api/media", None, {"Host": "attacker.example"}),
            ("GET", "/", None, {"Host": "attacker.example"}),
            ("HEAD", "/api/preview", None, {"Host": "attacker.example"}),
            ("POST", "/api/jobs", b'{"kind":"analyze"}',
             {"Host": "attacker.example", "Content-Type": "application/json",
              "X-Pausio-Client": "studio"}),
            ("GET", "/api/state", None, {"Host": "127.0.0.1:1"}),
        ]
        for method, path, data, headers in cases:
            with self.subTest(method=method, path=path, host=headers["Host"]):
                status, _, body = self.request(method, path, data, headers)
                self.assertEqual(status, 403, body[:300])
                if method != "HEAD":
                    self.assertIn("Host non autorizzato", body.decode("utf-8"))
        self.assertEqual(self.get_state()["job"]["status"], "idle")

    def test_localhost_alias_allowed_but_foreign_origin_rejected(self):
        status, _, payload = self.request(
            "GET", "/api/state", headers={"Host": f"localhost:{self.server.server_port}"}
        )
        self.assertEqual(status, 200, payload[:100])
        status, _, payload = self.request(
            "POST", "/api/jobs", b'{"kind":"analyze"}',
            {"Host": f"localhost:{self.server.server_port}",
             "Content-Type": "application/json", "X-Pausio-Client": "studio",
             "Origin": self.base},
        )
        self.assertEqual(status, 400)
        self.assertIn("Origine", json.loads(payload)["error"])
        # A request from the alternate localhost origin reaches normal
        # project validation; it must not be rejected as a foreign origin.
        status, _, payload = self.request(
            "POST", "/api/jobs", b'{"kind":"analyze"}',
            {"Host": f"localhost:{self.server.server_port}",
             "Content-Type": "application/json", "X-Pausio-Client": "studio",
             "Origin": f"http://localhost:{self.server.server_port}"},
        )
        self.assertEqual(status, 400)
        self.assertIn("Importa prima", json.loads(payload)["error"])

    def test_transport_has_bounded_connections_and_socket_timeout(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")
        self.assertEqual(self.server.request_queue_size, STUDIO_LISTEN_BACKLOG)
        self.assertGreater(MAX_ACTIVE_CONNECTIONS, 1)
        self.assertLessEqual(MAX_ACTIVE_CONNECTIONS, 32)
        self.assertGreater(SOCKET_IDLE_TIMEOUT_S, 0)
        # All occupied slots -> refuse an extra local client, no thread spawned.
        slots = self.server._client_slots
        for _ in range(MAX_ACTIVE_CONNECTIONS):
            self.assertTrue(slots.acquire(blocking=False))
        try:
            saturated = Mock()
            self.server.process_request(saturated, ("127.0.0.1", 9999))
            saturated.close.assert_called_once_with()
        finally:
            for _ in range(MAX_ACTIVE_CONNECTIONS):
                slots.release()
        self.assertTrue(slots.acquire(blocking=False))
        slots.release()
        # The transport sets a timeout on each accepted socket; no sleep test.
        fake_sock = Mock()
        with patch.object(StudioServer.__mro__[1], "get_request",
                          return_value=(fake_sock, ("127.0.0.1", 19999))):
            accepted, _ = self.server.get_request()
        self.assertIs(accepted, fake_sock)
        fake_sock.settimeout.assert_called_once_with(SOCKET_IDLE_TIMEOUT_S)

    def test_cross_origin_and_missing_client_token_are_rejected(self):
        status, _, data = self.request(
            "POST", "/api/jobs", b'{"kind":"analyze"}', {"Content-Type": "application/json"}
        )
        self.assertEqual(status, 400)
        self.assertIn("autorizzata", json.loads(data)["error"])
        status, _, data = self.request(
            "POST", "/api/jobs", b'{"kind":"analyze"}',
            {"Content-Type": "application/json", "X-Pausio-Client": "studio",
             "Origin": "https://other.example"},
        )
        self.assertEqual(status, 400)
        self.assertIn("Origine", json.loads(data)["error"])

    def test_studio_requires_media_for_analysis_and_approval(self):
        status, _, _ = self.post("/api/jobs", {"kind": "analyze"})
        self.assertEqual(status, 400)
        status, _, _ = self.post("/api/approve", {})
        self.assertEqual(status, 400)

    def test_unsupported_upload_preserves_empty_session(self):
        status, _, payload = self.request("POST", "/api/import", b"not-a-video",
            {"Content-Type": "application/octet-stream", "X-Pausio-Client": "studio",
             "X-Filename": "virus.exe", "Origin": self.base})
        self.assertEqual(status, 400)
        self.assertIn("Formato", json.loads(payload)["error"])
        self.assertIsNone(self.get_state()["file"])


class StudioPortSelectionTests(unittest.TestCase):
    def test_real_occupied_port_is_skipped_without_touching_listener(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
            occupied.bind(("127.0.0.1", 0))
            occupied.listen()
            starting_port = occupied.getsockname()[1]
            if starting_port == 65535:
                self.skipTest("OS picked the last TCP port")
            workspace = StudioWorkspace()
            server = None
            try:
                server = create_server(port=starting_port, workspace=workspace)
                self.assertGreater(server.server_port, starting_port)
                self.assertEqual(server.server_address[0], "127.0.0.1")
                # The original listener is still bound: Pausio never stops it.
                self.assertEqual(occupied.getsockname()[1], starting_port)
            finally:
                if server is not None:
                    server.server_close()
                workspace.close()

    def test_falls_forward_one_port_per_address_in_use(self):
        with patch("pausio.studio.StudioServer") as factory:
            factory.side_effect = [
                OSError(errno.EADDRINUSE, "port occupied"),
                OSError(errno.EADDRINUSE, "port occupied"),
                sentinel.server,
            ]
            result = create_server(port=8765, workspace=sentinel.workspace)
            self.assertIs(result, sentinel.server)
            self.assertEqual(factory.call_args_list, [
                call(("127.0.0.1", 8765), sentinel.workspace),
                call(("127.0.0.1", 8766), sentinel.workspace),
                call(("127.0.0.1", 8767), sentinel.workspace),
            ])

    def test_port_zero_and_other_socket_failures_are_not_retried(self):
        with patch("pausio.studio.StudioServer", return_value=sentinel.server) as factory:
            self.assertIs(create_server(port=0, workspace=sentinel.workspace),
                          sentinel.server)
            factory.assert_called_once_with(("127.0.0.1", 0), sentinel.workspace)
        with patch("pausio.studio.StudioServer",
                   side_effect=OSError(errno.EACCES, "permission denied")) as factory:
            with self.assertRaises(OSError) as caught:
                create_server(port=8765, workspace=sentinel.workspace)
            self.assertEqual(caught.exception.errno, errno.EACCES)
            self.assertEqual(factory.call_count, 1)

    def test_last_port_does_not_wrap_around(self):
        with patch("pausio.studio.StudioServer",
                   side_effect=OSError(errno.EADDRINUSE, "occupied")) as factory:
            with self.assertRaises(OSError) as caught:
                create_server(port=65535, workspace=sentinel.workspace)
            self.assertEqual(caught.exception.errno, errno.EADDRINUSE)
            factory.assert_called_once_with(("127.0.0.1", 65535), sentinel.workspace)

    def test_startup_opens_url_of_actual_port(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
            occupied.bind(("127.0.0.1", 0))
            occupied.listen()
            starting_port = occupied.getsockname()[1]
            if starting_port == 65535:
                self.skipTest("OS picked the last TCP port")
            with tempfile.TemporaryDirectory() as directory:
                from io import StringIO
                from contextlib import redirect_stdout
                with (patch("pausio.studio.webbrowser.open") as open_browser,
                      patch("pausio.studio.StudioServer.serve_forever")):
                    output = StringIO()
                    with redirect_stdout(output):
                        run_studio(port=starting_port, data_dir=Path(directory))
                    printed = output.getvalue()
                    self.assertIn("Porta " + str(starting_port) + " già occupata", printed)
                    open_browser.assert_called_once()
                    self.assertIn(open_browser.call_args.args[0], printed)
                    self.assertNotEqual(
                        open_browser.call_args.args[0],
                        f"http://127.0.0.1:{starting_port}"
                    )


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg unavailable")
class StudioMediaWorkflowTests(StudioHttpTests):
    def make_clip(self, destination: Path):
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=blue:s=180x320:r=15:d=1.5",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1.5",
            "-shortest", "-c:v", "mpeg4", "-c:a", "aac", str(destination),
        ], timeout=35, check=True)

    def import_clip(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "test footage.mp4"
            self.make_clip(source)
            original = source.read_bytes()
            status, _, payload = self.request(
                "POST", "/api/import", original,
                {"Content-Type": "application/octet-stream",
                 "X-Pausio-Client": "studio",
                 "X-Filename": "test%20footage.mp4", "Origin": self.base},
            )
            self.assertEqual(status, 200, payload[:200])
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(json.loads(payload)["file"], "test footage.mp4")
        return original

    def test_import_custom_audio_fx_preview_relink_and_export(self):
        self.import_clip()
        state = self.get_state()
        with tempfile.TemporaryDirectory() as directory:
            fx = Path(directory) / "my riser.wav"
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "sine=frequency=880:duration=0.6",
                "-c:a", "pcm_s16le", str(fx),
            ], timeout=35, check=True)
            raw = fx.read_bytes()
        headers = {
            "Content-Type": "application/octet-stream", "X-Pausio-Client": "studio",
            "Origin": self.base, "X-Filename": "my%20riser.wav",
            "X-Pausio-Revision": str(state["project_revision"]),
            "X-Pausio-Start-Ms": "1100",
        }
        bad = dict(headers, **{"X-Filename": "notes.txt"})
        status, _, _ = self.request("POST", "/api/audio/import", raw, bad)
        self.assertEqual(status, 400)
        status, _, content = self.request("POST", "/api/audio/import", raw, headers)
        self.assertEqual(status, 200, content)
        imported = json.loads(content)
        self.assertEqual(len(imported["audio_clips"]), 1)
        clip = imported["audio_clips"][0]
        self.assertTrue(clip["available"])
        self.assertEqual(clip["start_ms"], 500)
        self.assertEqual(clip["gain_db"], -12)
        import hashlib
        self.assertEqual(clip["asset_sha256"], hashlib.sha256(raw).hexdigest())
        fx_path = self.workspace._audio_path(clip["asset_sha256"])
        self.assertEqual(fx_path.read_bytes(), raw)
        status, _, data = self.request("GET", "/api/audio/" + clip["asset_sha256"],
                                       headers={"Range": "bytes=0-31"})
        self.assertEqual(status, 206)
        self.assertEqual(data, raw[:32])
        status, _, wave = self.request(
            "GET", "/api/audio/waveform/" + clip["asset_sha256"]
        )
        self.assertEqual(status, 200, wave[:200])
        waveform = json.loads(wave)
        self.assertEqual(waveform["asset_sha256"], clip["asset_sha256"])
        self.assertEqual(len(waveform["values"]), 900)
        self.assertGreater(max(waveform["values"]), 0)
        self.assertEqual(
            self.request("GET", "/api/audio/waveform/" + "0"*64)[0], 400
        )
        status, _, project_bytes = self.request("GET", "/api/project/export")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(project_bytes)["commands"][-1]["type"], "audio.add")
        self.assertNotIn("file_path", project_bytes.decode())

        status, _, data = self.post("/api/command", {
            "revision": imported["project_revision"], "type": "history.undo", "payload": {},
        })
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data)["audio_clips"], [])
        status, _, data = self.post("/api/command", {
            "revision": json.loads(data)["project_revision"], "type": "history.redo", "payload": {},
        })
        self.assertEqual(status, 200)
        self.assertEqual(len(json.loads(data)["audio_clips"]), 1)
        state = json.loads(data)
        status, _, data = self.post("/api/command", {
            "revision": state["project_revision"], "type": "timeline.keep_all", "payload": {},
        })
        self.assertEqual(status, 200)
        status, _, data = self.post("/api/jobs", {"kind": "preview"})
        self.assertEqual(status, 202, data)
        self.await_job("preview")
        self.assertEqual(self.request("GET", "/api/preview")[0], 200)

        fx_path.unlink()
        self.assertFalse(self.get_state()["audio_clips"][0]["available"])
        self.assertEqual(self.post("/api/jobs", {"kind": "preview"})[0], 400)
        state = self.get_state()
        headers["X-Pausio-Revision"] = str(state["project_revision"])
        status, _, data = self.request("POST", "/api/audio/import", raw, headers)
        self.assertEqual(status, 200, data)
        relinked = json.loads(data)
        self.assertEqual(len(relinked["audio_clips"]), 1)
        self.assertEqual(relinked["project_revision"], state["project_revision"])
        self.assertTrue(relinked["audio_clips"][0]["available"])
        status, _, data = self.post("/api/command", {
            "revision": relinked["project_revision"], "type": "timeline.approve", "payload": {},
        })
        self.assertEqual(status, 200)
        status, _, data = self.post("/api/jobs", {"kind": "render"})
        self.assertEqual(status, 202, data)
        self.await_job("render")
        self.assertEqual(self.request("GET", "/api/export")[0], 200)

    def test_configurable_presets_persist_and_invalid_requests_are_safe(self):
        self.import_clip()
        state=self.get_state()
        self.assertIn("balanced",state["cut_presets"])
        custom={"preset":"custom",**state["cut_presets"]["dynamic"]}
        custom["noise_db"]=-20
        previous_revision=state["project_revision"]
        status,_,error=self.post("/api/jobs",{"kind":"analyze","settings":{**custom,"noise_db":True}})
        self.assertEqual(status,400,error)
        self.assertEqual(self.get_state()["project_revision"],previous_revision)
        status,_,data=self.post("/api/jobs",{"kind":"analyze","settings":custom})
        self.assertEqual(status,202,data)
        state=self.await_job("analyze")
        self.assertEqual(state["analysis_settings"],custom)
        self.assertIsInstance(state["detected_silences"],int)
        status,_,export=self.request("GET","/api/project/export")
        self.assertEqual(status,200)
        tape=json.loads(export)
        payload=tape["commands"][-1]["payload"]
        self.assertEqual(payload["settings"],custom)
        self.assertEqual(payload["noise_db"],-20)
        self.assertEqual(payload["detected_silences"],state["detected_silences"])
        status,_,data=self.post("/api/jobs",{"kind":"analyze","settings":
            {"preset":"balanced",**state["cut_presets"]["balanced"]}})
        self.assertEqual(status,202,data)
        new_state=self.await_job("analyze")
        self.assertEqual(new_state["analysis_settings"]["preset"],"balanced")
        self.assertEqual(new_state["project_revision"],previous_revision+2)
        self.assertFalse(new_state["approved"])
        self.assertEqual(len(self.workspace.tape.commands),2)

    def test_face_reframing_is_readonly_until_typed_approval(self):
        from unittest.mock import patch
        self.import_clip()
        status,_,raw=self.post("/api/plan",{"segments":[
            {"start_ms":0,"end_ms":1400}
        ]})
        self.assertEqual(status,200,raw)
        state=json.loads(raw)
        seg=state["editor_segments"][0]
        effect={"id":"a"*32,"segment_id":seg["id"],
                "start_ms":200,"end_ms":1100,"kind":"slow_push",
                "start_scale_pct":100,"end_scale_pct":116,
                "anchor_x_pct":50,"anchor_y_pct":50}
        status,_,raw=self.post("/api/command",{
            "revision":state["project_revision"],"type":"video.transform.add",
            "payload":{"effect":effect}})
        self.assertEqual(status,200,raw)
        edited=json.loads(raw)
        with patch("pausio.studio.propose_face_anchor",return_value={
            "status":"ready","anchor_x_pct":78,"anchor_y_pct":44,
            "samples":5,"method":"local-haar-stable-crop-v1"
        }):
            status,_,raw=self.post("/api/visual-fx/face-anchor",{
                "revision":edited["project_revision"],"effect_id":effect["id"]})
        self.assertEqual(status,200,raw)
        suggestion=json.loads(raw)
        self.assertEqual(suggestion["status"],"ready")
        self.assertEqual(suggestion["media_sha256"],self.workspace.media_sha256)
        self.assertEqual(self.get_state()["video_fx"],[effect])
        self.assertEqual(self.get_state()["project_revision"],edited["project_revision"])
        self.assertEqual(self.post("/api/visual-fx/face-anchor",{
            "revision":-1,"effect_id":effect["id"]})[0],409)
        approved={**effect,"anchor_x_pct":78,"anchor_y_pct":44}
        status,_,raw=self.post("/api/command",{
            "revision":edited["project_revision"],"type":"video.transform.update",
            "payload":{"effect":approved}})
        self.assertEqual(status,200,raw)
        self.assertEqual(json.loads(raw)["video_fx"],[approved])

    def test_visual_fx_readonly_suggestions_then_typed_preview_and_export(self):
        self.import_clip()
        initial=self.get_state()
        denied, _, raw=self.post("/api/visual-fx/suggest", {
            "revision": initial["project_revision"], "preset": "naturale"
        })
        self.assertEqual(denied,200,raw)
        self.assertEqual(json.loads(raw)["candidates"],[])
        self.assertEqual(self.get_state()["project_revision"], initial["project_revision"])
        self.assertEqual(self.get_state()["video_fx"], [])
        self.assertEqual(self.post("/api/visual-fx/suggest", {
            "revision": -1, "preset": "naturale"
        })[0],409)
        self.assertEqual(self.post("/api/visual-fx/suggest", {
            "revision": 0, "preset": "unknown"
        })[0],400)
        self.post("/api/jobs",{"kind":"analyze"})
        analyzed=self.await_job("analyze")
        revision=analyzed["project_revision"]
        status,_,raw=self.post("/api/visual-fx/suggest",{
            "revision":revision,"preset":"dinamico"
        })
        self.assertEqual(status,200,raw)
        suggestion=json.loads(raw)
        self.assertEqual(suggestion["base_revision"],revision)
        self.assertEqual(suggestion["media_sha256"],self.workspace.media_sha256)
        self.assertEqual(self.get_state()["project_revision"],revision)
        seg=analyzed["editor_segments"][0]
        start=seg["start_ms"]
        if seg["end_ms"]-start < 350:
            self.skipTest("fixture KEEP segment shorter than 350 ms")
        effect={"id":"d"*32,"segment_id":seg["id"],"start_ms":start,
                "end_ms":min(start+1000,seg["end_ms"]),
                "kind":"punch","start_scale_pct":116,"end_scale_pct":116,
                "anchor_x_pct":50,"anchor_y_pct":50}
        status,_,raw=self.post("/api/command",{
            "revision":revision,"type":"video.transform.add","payload":{"effect":effect}
        })
        self.assertEqual(status,200,raw)
        changed=json.loads(raw)
        self.assertEqual(changed["video_fx"],[effect])
        self.assertFalse(changed["approved"])
        self.assertEqual(self.post("/api/visual-fx/suggest",{
            "revision":revision,"preset":"naturale"
        })[0],409)
        status,_,_=self.post("/api/jobs",{"kind":"preview"})
        self.assertEqual(status,202)
        preview=self.await_job("preview")
        self.assertTrue(preview["preview_ready"])
        status,_,content=self.request("GET","/api/preview",headers={"Range":"bytes=0-99"})
        self.assertEqual(status,206)
        self.assertEqual(len(content),100)
        status,_,document=self.request("GET","/api/project/export")
        self.assertEqual(status,200)
        self.assertIn("video.transform.add",[e["type"] for e in json.loads(document)["commands"]])
        self.assertEqual(json.loads(document)["schema_version"],3)
        status,_,raw=self.post("/api/command",{
            "revision":changed["project_revision"],"type":"history.undo","payload":{}
        })
        self.assertEqual(status,200)
        self.assertEqual(json.loads(raw)["video_fx"],[])

    def test_import_analyze_review_approve_export_download(self):
        original = self.import_clip()
        status, headers, bytes_ = self.request("GET", "/api/media", headers={"Range": "bytes=0-99"})
        self.assertEqual(status, 206)
        self.assertEqual(len(bytes_), 100)
        self.assertIn("Content-Range", headers)
        self.assertEqual(bytes_, original[:100])

        status, _, _ = self.post("/api/jobs", {"kind": "analyze"})
        self.assertEqual(status, 202)
        state = self.await_job("analyze")
        self.assertIsNotNone(state["plan"])
        self.assertFalse(state["approved"])
        self.assertTrue(state["plan"]["segments"])

        status, _, data = self.post("/api/jobs", {"kind": "render"})
        self.assertEqual(status, 400)
        self.assertIn("Conferma", json.loads(data)["error"])
        status, _, _ = self.post("/api/plan", {"segments": [
            {"start_ms": 0, "end_ms": 1000},
            {"start_ms": 900, "end_ms": 1400},
        ]})
        self.assertEqual(status, 400)
        self.assertEqual(self.get_state()["plan"], state["plan"])

        status, _, data = self.post("/api/approve", {})
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(data)["approved"])
        status, _, data = self.post("/api/jobs", {"kind": "render"})
        self.assertEqual(status, 202)
        state = self.await_job("render")
        self.assertTrue(state["export_ready"])
        status, headers, video = self.request("GET", "/api/export", headers={"Range":"bytes=0-99"})
        self.assertEqual(status, 206)
        self.assertEqual(len(video), 100)
        self.assertIn("attachment", headers["Content-Disposition"])
        self.assertNotEqual(video, original[:100])

        status, _, updated = self.post("/api/plan", {"segments": [{
            "start_ms": 0, "end_ms": state["media"]["duration_ms"]
        }]})
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(updated)["approved"])
        self.assertFalse(json.loads(updated)["export_ready"])
        self.assertEqual(self.request("GET", "/api/export")[0], 404)

    def test_waveform_is_real_pcm_envelope_not_visual_placeholder(self):
        self.import_clip()
        for _ in range(150):
            state=self.get_state()
            if state["waveform_status"] in {"ready","failed"}:
                break
            time.sleep(0.1)
        self.assertEqual(state["waveform_status"],"ready",state["waveform_error"])
        status, headers, payload=self.request("GET","/api/waveform")
        self.assertEqual(status,200)
        data=json.loads(payload)
        self.assertEqual(data["media_id"],state["media_id"])
        self.assertEqual(len(data["values"]),900)
        self.assertTrue(any(value>0 for value in data["values"]))
        self.assertTrue(all(0<=value<=1000 for value in data["values"]))
        self.assertEqual(data["duration_ms"],state["media"]["duration_ms"])

    def test_ffmpeg_draft_preview_without_approval_and_invalidation(self):
        self.import_clip()
        # Before making any edit proposal, preview cannot run.
        status, _, data=self.post("/api/jobs",{"kind":"preview"})
        self.assertEqual(status,400)
        self.assertIn("montaggio",json.loads(data)["error"])
        self.assertEqual(self.request("GET","/api/preview")[0],404)
        status, _, data=self.post("/api/jobs",{"kind":"analyze"})
        self.assertEqual(status,202,data)
        analyzed=self.await_job("analyze")
        self.assertFalse(analyzed["approved"])
        status, _, data=self.post("/api/jobs",{"kind":"preview"})
        self.assertEqual(status,202,data)
        ready=self.await_job("preview")
        self.assertTrue(ready["preview_ready"])
        self.assertFalse(ready["approved"])
        status, headers, chunk=self.request("GET","/api/preview",headers={"Range":"bytes=0-99"})
        self.assertEqual(status,206)
        self.assertEqual(len(chunk),100)
        self.assertEqual(headers["Content-Type"],"video/mp4")
        self.assertEqual(self.request("HEAD","/api/preview")[0],200)
        preview_file=self.workspace.directory / "preview.mp4"
        self.assertTrue(preview_file.exists())
        info=probe(preview_file)
        self.assertEqual((info.width,info.height),(540,960))
        source_info=ready["media"]
        self.assertFalse(ready["export_ready"])
        self.assertEqual(ready["project_revision"],1)

        status, _, modified=self.post("/api/command",{
            "revision":1,"type":"timeline.keep_all","payload":{},
        })
        self.assertEqual(status,200,modified)
        self.assertFalse(json.loads(modified)["preview_ready"])
        self.assertEqual(self.request("GET","/api/preview")[0],404)
        self.assertFalse(preview_file.exists())
        self.assertEqual(source_info["duration_ms"],self.workspace.info.duration_ms)

    def test_project_commands_export_import_and_media_binding(self):
        self.import_clip()
        status, _, response = self.post("/api/jobs", {"kind": "analyze"})
        self.assertEqual(status, 202, response)
        analyzed = self.await_job("analyze")
        self.assertEqual(analyzed["project_revision"], 1)
        self.assertEqual(analyzed["last_command"], "analysis.propose")
        first = analyzed["editor_segments"][0]
        self.assertEqual(len(first["id"]), 32)

        status, _, response = self.post("/api/command", {
            "revision": 1, "type": "segment.update",
            "payload": {
                "segment_id": first["id"],
                "start_ms": first["start_ms"],
                "end_ms": first["end_ms"] - 100,
            }
        })
        self.assertEqual(status, 200, response)
        edited = json.loads(response)
        self.assertEqual(edited["project_revision"], 2)
        self.assertFalse(edited["approved"])

        status, _, response = self.post("/api/command", {
            "revision": 1, "type": "timeline.keep_all", "payload": {},
        })
        self.assertEqual(status, 409)
        self.assertIn("Versione", json.loads(response)["error"])

        status, _, response = self.post("/api/command", {
            "revision": 2, "type": "timeline.approve", "payload": {},
        })
        self.assertEqual(status, 200, response)
        approved = json.loads(response)
        self.assertTrue(approved["approved"])

        status, headers, serialized = self.request("GET", "/api/project/export")
        self.assertEqual(status, 200)
        self.assertIn(".pausio.json", headers["Content-Disposition"])
        document = json.loads(serialized)
        self.assertEqual(document["schema_version"], 3)
        self.assertEqual(
            [item["type"] for item in document["commands"]],
            ["analysis.propose", "segment.update", "timeline.approve"],
        )
        self.assertEqual(document["media"]["sha256"], self.workspace.media_sha256)
        self.assertNotIn(str(self.workspace.source), serialized.decode("utf-8"))

        status, _, response = self.post("/api/command", {
            "revision": 3, "type": "timeline.keep_all", "payload": {},
        })
        self.assertEqual(status, 200, response)
        self.assertFalse(json.loads(response)["approved"])

        # The imported *instructions*, not a cached snapshot, recreate state.
        status, _, response = self.post("/api/project/import", document)
        self.assertEqual(status, 200, response)
        replayed = json.loads(response)
        self.assertEqual(replayed["plan"], approved["plan"])
        self.assertEqual(replayed["editor_segments"], approved["editor_segments"])
        self.assertEqual(replayed["project_revision"], 3)
        self.assertTrue(replayed["approved"])
        self.assertFalse(replayed["export_ready"])

        wrong = json.loads(json.dumps(document))
        wrong["media"]["sha256"] = "f" * 64
        for bad in (wrong, {**document, "schema_version": 4},
                    {**document, "commands": [{"id": "0" * 32,
                                              "type": "execute.code", "payload": {}}]}):
            status, _, _ = self.post("/api/project/import", bad)
            self.assertEqual(status, 400)
            self.assertEqual(self.get_state()["project_revision"], 3)
            self.assertEqual(self.get_state()["editor_segments"], approved["editor_segments"])

    def test_undo_redo_v2_import_and_new_edit_branches(self):
        self.import_clip()
        status, _, _ = self.post("/api/jobs", {"kind": "analyze"})
        self.assertEqual(status, 202)
        analyzed = self.await_job("analyze")
        self.assertEqual(analyzed["project_revision"], 1)
        original = analyzed["editor_segments"]

        status, _, data = self.post("/api/command", {
            "revision": 1, "type": "timeline.keep_all", "payload": {}
        })
        self.assertEqual(status, 200, data)
        all_keep = json.loads(data)
        self.assertTrue(all_keep["can_undo"])
        self.assertFalse(all_keep["can_redo"])
        self.assertEqual(all_keep["project_revision"], 2)

        status, _, data = self.post("/api/command", {
            "revision": 2, "type": "history.undo", "payload": {}
        })
        self.assertEqual(status, 200, data)
        undone = json.loads(data)
        self.assertEqual(undone["editor_segments"], original)
        self.assertEqual(undone["history_cursor"], 1)
        self.assertEqual(undone["project_revision"], 3)
        self.assertTrue(undone["can_redo"])

        portable = json.loads(self.request("GET", "/api/project/export")[2])
        self.assertEqual(portable["schema_version"], 3)
        self.assertEqual(portable["history_cursor"], 1)
        self.assertEqual(len(portable["commands"]), 2)
        self.assertEqual(portable["revision"], 3)

        status, _, data = self.post("/api/command", {
            "revision": 3, "type": "history.redo", "payload": {}
        })
        self.assertEqual(status, 200, data)
        redone = json.loads(data)
        self.assertEqual(redone["editor_segments"], all_keep["editor_segments"])
        self.assertEqual(redone["project_revision"], 4)

        status, _, data = self.post("/api/project/import", portable)
        self.assertEqual(status, 200, data)
        restored = json.loads(data)
        self.assertEqual(restored["editor_segments"], original)
        self.assertTrue(restored["can_redo"])
        self.assertEqual(restored["project_revision"], 3)

        status, _, data = self.post("/api/command", {
            "revision": 3, "type": "timeline.keep_all", "payload": {}
        })
        self.assertEqual(status, 200, data)
        forked = json.loads(data)
        self.assertFalse(forked["can_redo"])
        self.assertEqual(forked["command_count"], 2)
        self.assertEqual(forked["project_revision"], 4)

        status, _, data = self.post("/api/command", {
            "revision": 3, "type": "history.undo", "payload": {}
        })
        self.assertEqual(status, 409)
        self.assertIn("Versione", json.loads(data)["error"])

    def test_subtitle_generation_edit_and_real_burned_in_preview(self):
        self.import_clip()
        result = {
            "provider":"pausio-local","model":"mlx-community/whisper-large-v3-turbo",
            "text":"CIAO MONDO","word_timestamps_available":True,
            "segments":[{"start_ms":100,"end_ms":1400,"text":"CIAO MONDO",
                         "words":[
                             {"start_ms":100,"end_ms":600,"text":"CIAO"},
                             {"start_ms":650,"end_ms":1400,"text":"MONDO"}]}]
        }
        with patch("pausio.studio.transcribe_video_local", return_value=result):
            status, _, _ = self.post("/api/jobs", {"kind":"transcribe"})
            self.assertEqual(status,202)
            self.await_job("transcribe")
        state = self.get_state()
        status,_,data=self.post("/api/captions/generate",{
            "revision":state["project_revision"],"style":"social"
        })
        self.assertEqual(status,200,data)
        state=json.loads(data)
        self.assertEqual(len(state["captions"]),1)
        self.assertEqual(state["captions"][0]["text"],"CIAO MONDO")
        self.assertFalse(state["approved"])
        cue_id=state["captions"][0]["id"]
        status,_,data=self.post("/api/command",{
            "revision":state["project_revision"],"type":"caption.correct",
            "payload":{"caption_id":cue_id,"text":"CIAO MONDO!"}
        })
        self.assertEqual(status,200,data)
        corrected=json.loads(data)
        self.assertEqual(corrected["captions"][0]["text"],"CIAO MONDO!")
        # Config is a typed command, with an actual ASS change in the rendered MP4.
        settings={**corrected["caption_presets"]["social"],
                  "preset":"custom","x_pct":62,"y_pct":56,
                  "font_size":86,"font_family":"Georgia"}
        status,_,data=self.post("/api/command",{
            "revision":corrected["project_revision"],"type":"caption.configure",
            "payload":{"config":settings}
        })
        self.assertEqual(status,200,data)
        configured=json.loads(data)
        self.assertEqual(configured["caption_config"],settings)
        self.assertEqual(configured["caption_config"]["font_family"],"Georgia")
        self.assertFalse(configured["approved"])
        # Preview requires an edit plan, and the same captions as final export.
        status,_,data=self.post("/api/jobs",{"kind":"analyze"})
        self.assertEqual(status,202,data)
        planned=self.await_job("analyze")
        self.assertGreater(len(planned["output_captions"]),0)
        status,_,data=self.post("/api/jobs",{"kind":"preview"})
        self.assertEqual(status,202,data)
        preview=self.await_job("preview")
        self.assertTrue(preview["preview_ready"])
        file_path=self.workspace.directory/"preview.mp4"
        self.assertTrue(file_path.is_file())
        # Verify actual white caption pixels on a blue synthetic frame.
        capture=subprocess.run([
            "ffmpeg","-hide_banner","-loglevel","error","-ss","0.4",
            "-i",str(file_path),"-frames:v","1","-f","rawvideo",
            "-pix_fmt","rgb24","-"
        ],capture_output=True,timeout=40,check=True)
        pixels=capture.stdout
        self.assertGreater(sum(1 for i in range(0,len(pixels),3)
            if pixels[i]>190 and pixels[i+1]>190 and pixels[i+2]>190),100)
        exported=json.loads(self.request("GET","/api/project/export")[2])
        self.assertIn("caption.correct",[c["type"] for c in exported["commands"]])
        self.assertIn("caption.configure",[c["type"] for c in exported["commands"]])
        self.assertEqual(
            [c["text"] for c in self.workspace.tape.view.captions],["CIAO MONDO!"])
        # Imported caption edits do not depend on a persisted ASR transcript.
        self.workspace.transcript=None
        status,_,data=self.post("/api/project/import",exported)
        self.assertEqual(status,200,data)
        self.assertEqual(json.loads(data)["captions"][0]["text"],"CIAO MONDO!")
        self.assertEqual(json.loads(data)["caption_config"],settings)
        self.assertEqual(self.request("GET","/api/captions/generate")[0],404)

    def test_export_requires_matching_uploaded_video(self):
        status, _, response = self.request("GET", "/api/project/export")
        self.assertEqual(status, 400)
        self.assertIn("Importa", json.loads(response)["error"])

    def test_transcription_uses_pausio_internal_asr_without_external_server(self):
        self.import_clip()
        result = {
            "provider": "pausio-local", "backend": "mlx-whisper",
            "text": "Ciao", "segments": [{"start_ms": 0, "end_ms": 900, "text": "Ciao"}],
            "word_timestamps_available": False
        }
        options = {"model": "mlx-community/whisper-large-v3-turbo",
                   "language": "it", "allow_model_download": False}
        with patch("pausio.studio.transcribe_video_local", return_value=result) as runner:
            status, _, body = self.post("/api/jobs", {"kind": "transcribe", "asr": options})
            self.assertEqual(status, 202, body)
            state = self.await_job("transcribe")
            self.assertEqual(state["transcript"]["text"], "Ciao")
            runner.assert_called_once()
            self.assertEqual(runner.call_args.kwargs, options)
        status, _, body = self.post("/api/jobs", {"kind": "transcribe", "asr": {
            **options, "allow_model_download": 1
        }})
        self.assertEqual(status, 400, body)
        status, _, body = self.post("/api/jobs", {"kind": "analyze", "asr": options})
        self.assertEqual(status, 400, body)


class StudioStaticCodeTests(unittest.TestCase):
    def test_frontend_is_packaged_and_semantically_named(self):
        for name in ("index.html", "styles.css", "app.js"):
            self.assertTrue((STATIC_DIR / name).is_file())
        css = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        self.assertIn("prefers-reduced-motion", css)
        self.assertIn(":focus-visible", css)
        self.assertIn('aria-live="polite"', html)
        self.assertIn('id="timeline-track"', html)
        self.assertIn('id="waveform-canvas"', html)
        self.assertIn('id="preview-action"', html)
        self.assertIn('"trim-handle "+side', (STATIC_DIR / "app.js").read_text(encoding="utf-8"))
        self.assertNotIn("https://", html)

    @unittest.skipUnless(shutil.which("node"), "Node unavailable for JS syntax check")
    def test_browser_js_is_syntactically_valid(self):
        command = subprocess.run(
            ["node", "--check", str(STATIC_DIR / "app.js")],
            capture_output=True, text=True,
        )
        self.assertEqual(command.returncode, 0, command.stderr)


if __name__ == "__main__":
    unittest.main()
