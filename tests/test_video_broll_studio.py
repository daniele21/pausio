"""Studio HTTP B-roll smoke test: local assets, edits and FFmpeg preview."""
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

from pausio.studio import StudioWorkspace, create_server


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                     "FFmpeg/ffprobe required")
class VideoBrollStudioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = StudioWorkspace(data_dir=Path(self.temp.name))
        self.server = create_server(port=0, workspace=self.workspace)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:" + str(self.server.server_port)
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.workspace.close()
        self.temp.cleanup()

    def request(self, path, body=None, *, headers=None):
        request = urllib.request.Request(
            self.base + path,
            data=body,
            method="POST" if body is not None else "GET",
            headers=headers or {},
        )
        try:
            with self.opener.open(request, timeout=60) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def post_json(self, path, payload):
        return self.request(path, json.dumps(payload).encode(), headers={
            "Content-Type": "application/json", "X-Pausio-Client": "studio",
            "Origin": self.base,
        })

    def await_job(self, name):
        for _ in range(300):
            state = json.loads(self.request("/api/state")[1])
            if state["job"]["status"] in {"completed", "failed"}:
                self.assertEqual(state["job"]["kind"], name)
                self.assertEqual(state["job"]["status"], "completed", state["job"]["error"])
                return state
            time.sleep(.1)
        self.fail("Job did not finish")

    @staticmethod
    def clip(path, color, frequency):
        subprocess.run([
            "ffmpeg", "-hide_banner", "-nostdin", "-v", "error", "-y",
            "-f", "lavfi", "-i", f"color=c={color}:s=180x320:r=30:d=2",
            "-f", "lavfi", "-i", f"sine=frequency={frequency}:duration=2",
            "-c:v", "mpeg4", "-c:a", "aac", "-shortest", str(path),
        ], check=True, timeout=50)

    def test_upload_edit_preview_relink_and_clear_session(self):
        source = Path(self.temp.name) / "source.mp4"
        roll = Path(self.temp.name) / "cutaway.mp4"
        self.clip(source, "blue", 440)
        self.clip(roll, "red", 880)
        original = source.read_bytes()
        headers = {
            "Content-Type": "application/octet-stream",
            "X-Pausio-Client": "studio", "Origin": self.base,
            "X-Filename": "source.mp4",
        }
        status, _ = self.request("/api/import", original, headers=headers)
        self.assertEqual(status, 200)
        self.assertEqual(self.post_json("/api/jobs", {"kind": "analyze"})[0], 202)
        prepared = self.await_job("analyze")
        revision = prepared["project_revision"]

        upload = {
            **headers, "X-Filename": "../bad.mov",
            "X-Pausio-Revision": str(revision),
            "X-Pausio-Start-Ms": "200",
        }
        status, _ = self.request("/api/video-broll/import", roll.read_bytes(), headers=upload)
        self.assertEqual(status, 400)
        self.assertEqual(self.workspace.tape.revision, revision)

        upload["X-Filename"] = "cutaway.mp4"
        status, data = self.request("/api/video-broll/import", roll.read_bytes(), headers=upload)
        self.assertEqual(status, 200, data[:200])
        state = json.loads(data)
        self.assertEqual(len(state["video_broll"]), 1)
        row = state["video_broll"][0]
        self.assertTrue(row["available"])
        self.assertEqual(row["mode"], "fullscreen")
        self.assertFalse(state["approved"])
        self.assertEqual(state["project_revision"], revision + 1)
        self.assertEqual(self.post_json("/api/jobs", {"kind": "preview"})[0], 202)
        preview = self.await_job("preview")
        self.assertTrue(preview["preview_ready"])
        self.assertEqual(self.request("/api/preview")[0], 200)

        revised = {key: value for key, value in row.items() if key != "available"}
        revised.update(mode="pip", x_pct=80, width_pct=40)
        status, data = self.post_json("/api/command", {
            "revision": state["project_revision"],
            "type": "video.broll.update", "payload": {"video": revised},
        })
        self.assertEqual(status, 200, data[:200])
        self.assertFalse(json.loads(data)["preview_ready"])
        portable = json.loads(self.request("/api/project/export")[1])
        self.assertEqual(portable["schema_version"], 15)
        self.assertNotIn(str(roll), json.dumps(portable))

        digest = row["asset_sha256"]
        stored = self.workspace._video_path(digest, row["filename"])
        self.assertTrue(stored.exists())
        self.assertEqual(self.post_json("/api/session/clear", {})[0], 200)
        self.assertFalse(stored.exists())
