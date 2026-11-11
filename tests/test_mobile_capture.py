"""Static routing and privacy contract for the standalone mobile recorder."""
from __future__ import annotations

import threading
import unittest
import urllib.request

from pausio.studio import StudioWorkspace, create_server


class MobileCaptureServerTests(unittest.TestCase):
    def setUp(self):
        self.workspace = StudioWorkspace()
        self.server = create_server(port=0, workspace=self.workspace)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.workspace.close()

    def fetch(self, path):
        with urllib.request.urlopen(self.base + path, timeout=10) as response:
            return response.headers, response.read().decode("utf-8")

    def test_mobile_assets_and_security(self):
        for path, marker in [
            ("/capture", 'id="download-video"'),
            ("/capture.html", 'id="script-input"'),
            ("/capture.css", ".prompter-scroll"),
            ("/capture.js", "new MediaRecorder(stream"),
        ]:
            with self.subTest(path=path):
                headers, content = self.fetch(path)
                self.assertIn(marker, content)
                self.assertEqual(headers["Cache-Control"], "no-store")
                self.assertIn("default-src 'self'", headers["Content-Security-Policy"])
                self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertIn("blob:", self.fetch("/capture")[0]["Content-Security-Policy"])

    def test_capture_is_not_uploaded_or_mutating_studio(self):
        _, script = self.fetch("/capture.js")
        self.assertNotIn('fetch(', script)
        self.assertNotIn("XMLHttpRequest", script)
        self.assertIn("URL.createObjectURL(output)", script)
        self.assertIn("recorder.start(1000)", script)
        self.assertIn("els.download.download = outputName", script)
        headers, index = self.fetch("/")
        self.assertIn('href="/capture"', index)
        self.assertIn("no-store", headers["Cache-Control"])
