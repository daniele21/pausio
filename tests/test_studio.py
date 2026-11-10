"""Local HTTP Studio integration tests; no browser automation or real creator media."""

from __future__ import annotations

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

from pausio.studio import STATIC_DIR, StudioWorkspace, create_server


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
            ("/app.js", b"/api/plan"),
        ):
            status, headers, content = self.request("GET", path)
            self.assertEqual(status, 200)
            self.assertIn(snippet, content)
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.assertEqual(headers["Cross-Origin-Resource-Policy"], "same-origin")
            self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertIn(b'role="tablist"', self.request("GET", "/")[2])
        self.assertIn(b'id="approve-action"', self.request("GET", "/")[2])

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

    def test_transcription_uses_closedroom_adapter_only(self):
        self.import_clip()
        result = {
            "provider": "closedroom-local",
            "text": "Ciao", "segments": [{"start_ms": 0, "end_ms": 900, "text": "Ciao"}],
            "word_timestamps_available": False
        }
        with patch("pausio.studio.transcribe_video_with_closedroom", return_value=result) as call:
            status, _, _ = self.post("/api/jobs", {"kind": "transcribe"})
            self.assertEqual(status, 202)
            state = self.await_job("transcribe")
            self.assertEqual(state["transcript"]["text"], "Ciao")
            call.assert_called_once()


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
