"""Simulated mobile camera E2E: actual MediaRecorder video download in Chromium."""
from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright

from pausio.studio import StudioWorkspace, create_server


class MobileCapturePlaywrightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = StudioWorkspace()
        self.server = create_server(port=0, workspace=self.workspace)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch(headless=True, args=[
            "--no-sandbox", "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream",
        ])
        self.context = self.browser.new_context(
            viewport={"width":390, "height":844},
            permissions=["camera", "microphone"], accept_downloads=True,
        )
        self.page = self.context.new_page()
        self.errors = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.goto(f"http://127.0.0.1:{self.server.server_port}/capture",
                       wait_until="networkidle")

    def tearDown(self):
        self.context.close()
        self.browser.close()
        self.pw.stop()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.workspace.close()
        self.temp.cleanup()

    def test_record_preview_and_download(self):
        page = self.page
        page.locator("#script-input").fill("Questo è un take di prova. Il gobbo è solo un overlay.")
        self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"),
                             390)
        page.locator("#activate-camera").click()
        page.locator("#record-start").wait_for(state="visible", timeout=15000)
        self.assertTrue(page.evaluate(
            "() => !!document.querySelector('#camera-video').srcObject"
        ))
        page.locator("#record-start").click()
        page.locator("#record-stop").wait_for(state="visible", timeout=15000)
        page.wait_for_timeout(1800)
        page.locator("#record-stop").click()
        page.locator("#download-panel").wait_for(state="visible", timeout=20000)
        self.assertTrue(page.evaluate(
            "() => document.querySelector('#download-video').href.startsWith('blob:')"
        ))
        with page.expect_download(timeout=15000) as download_info:
            page.locator("#download-video").click()
        download = download_info.value
        path = Path(self.temp.name) / download.suggested_filename
        download.save_as(path)
        self.assertGreater(path.stat().st_size, 1000)
        self.assertIn(path.suffix, (".mp4", ".webm"))
        self.assertTrue(page.locator("#result-video").is_visible())
        self.assertFalse(page.locator("#prompter").is_visible())
        self.assertEqual(self.errors, [])

    def test_camera_preview_is_responsive_at_320px(self):
        page = self.page
        page.set_viewport_size({"width":320,"height":700})
        self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), 320)
        self.assertTrue(page.locator("#activate-camera").is_visible())
        self.assertTrue(page.locator("#script-input").is_visible())
