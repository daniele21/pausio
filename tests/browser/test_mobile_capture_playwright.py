"""Simulated mobile camera E2E: actual MediaRecorder video download in Chromium."""
from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright

from pausio.studio import StudioWorkspace, create_server
from pausio.media import probe


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
        page.locator("#edit-gobbo").click()
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
        # A real media parser must accept the downloaded bytes as a Pausio input.
        info = probe(path)
        self.assertGreater(info.duration_ms, 700)
        self.assertTrue(info.has_audio, "Recorded take must retain microphone audio")
        self.assertEqual((info.width, info.height), (720, 1280),
                         "Downloaded video must be portrait regardless of camera source")
        self.assertTrue(page.locator("#result-video").is_visible())
        self.assertIn("720×1280 verticale", page.locator("#file-details").inner_text())
        self.assertTrue(page.locator("#gobbo-settings").count() == 1)
        self.assertIn("Il tuo copione", page.locator("#gobbo-settings").inner_text())
        self.assertFalse(page.locator("#prompter").is_visible())
        self.assertEqual(self.errors, [])

    def test_camera_activation_shows_preview_even_when_play_promise_never_resolves(self):
        """Regression: mobile Safari may defer play() until the video becomes visible."""
        page = self.page
        page.add_init_script("""
            HTMLMediaElement.prototype.play = function() {
                return new Promise(() => {});
            };
        """)
        page.reload(wait_until="networkidle")
        self.assertIn("Pagina pronta", page.locator("#status").inner_text())
        page.locator("#activate-camera").click()
        page.locator("#record-start").wait_for(state="visible", timeout=12000)
        self.assertTrue(page.evaluate("""() => {
            const video = document.getElementById('camera-video');
            return !video.hidden && !!video.srcObject && video.srcObject.active;
        }"""))
        self.assertEqual(page.locator("#capture-state").inner_text(), "CAMERA ATTIVA")
        self.assertEqual(self.errors, [])

    def test_full_camera_frame_and_larger_prompter_at_390px(self):
        page = self.page
        self.assertEqual(page.locator("#framing-mode").input_value(), "wide")
        self.assertFalse(page.locator("#gobbo-settings").evaluate("(element) => element.open"))
        self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), 390)
        page.locator("#activate-camera").click()
        page.locator("#record-start").wait_for(state="visible", timeout=15000)
        geometry = page.evaluate("""() => {
            const frame = document.querySelector('#camera-frame').getBoundingClientRect();
            const prompter = document.querySelector('#prompter-scroll').getBoundingClientRect();
            const video = document.querySelector('#camera-video');
            return {frameWidth:frame.width, frameHeight:frame.height,
                    prompterHeight:prompter.height,
                    fit:getComputedStyle(video).objectFit,
                    hasCamera:!!video.srcObject};
        }""")
        self.assertGreaterEqual(geometry["frameWidth"], 340, geometry)
        self.assertGreaterEqual(geometry["frameHeight"], 620, geometry)
        self.assertGreaterEqual(geometry["prompterHeight"], 150, geometry)
        self.assertEqual(geometry["fit"], "contain", geometry)
        self.assertTrue(geometry["hasCamera"])
        self.assertTrue(page.locator("#portrait-canvas").is_visible())
        self.assertEqual(page.locator("#portrait-canvas").evaluate(
            "(el) => [el.width, el.height]"), [720, 1280])
        self.assertTrue(page.locator("#camera-frame").evaluate(
            "(el) => el.classList.contains('composited')"))
        page.locator("#edit-gobbo").click()
        self.assertTrue(page.locator("#gobbo-settings").evaluate("(element) => element.open"))
        self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), 390)
        previous = page.locator("#prompter-scroll").evaluate("(element) => element.clientHeight")
        page.locator("#gobbo-lines").focus()
        page.locator("#gobbo-lines").press("End")
        extended = page.locator("#prompter-scroll").evaluate("(element) => element.clientHeight")
        self.assertGreater(extended, previous)
        page.locator("#framing-mode").select_option("social")
        page.locator("#record-start").wait_for(state="visible", timeout=15000)
        self.assertEqual(page.locator("#framing-mode").input_value(), "social")
        self.assertIn("video verticale con ritaglio", page.locator("#status").inner_text())
        self.assertEqual(self.errors, [])

    def test_landscape_camera_source_produces_portrait_preview_and_video(self):
        """Use a forced 640×480 camera to reproduce the user's 1920×1080 issue."""
        page = self.page
        page.add_init_script("""
          const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
          navigator.mediaDevices.getUserMedia = (options) =>
            original({video: {width: {exact: 640}, height: {exact: 480}},
                      audio: options.audio});
        """)
        page.reload(wait_until="networkidle")
        page.locator("#activate-camera").click()
        page.locator("#record-start").wait_for(state="visible", timeout=15000)
        raw = page.evaluate("""() => {
            const settings = document.querySelector("#camera-video")
              .srcObject.getVideoTracks()[0].getSettings();
            return [settings.width, settings.height];
        }""")
        self.assertEqual(raw, [640, 480])
        self.assertEqual(page.locator("#portrait-canvas").evaluate(
            "(el) => [el.width, el.height]"), [720, 1280])
        page.locator("#record-start").click()
        page.locator("#record-stop").wait_for(state="visible", timeout=15000)
        page.wait_for_timeout(1300)
        page.locator("#record-stop").click()
        page.locator("#download-panel").wait_for(state="visible", timeout=15000)
        with page.expect_download(timeout=15000) as captured:
            page.locator("#download-video").click()
        artifact = Path(self.temp.name) / captured.value.suggested_filename
        captured.value.save_as(artifact)
        info = probe(artifact)
        self.assertEqual((info.width, info.height), (720, 1280))
        self.assertTrue(info.has_audio)
        self.assertIn("verticale", page.locator("#file-details").inner_text())
        self.assertEqual(self.errors, [])

    def test_camera_preview_is_responsive_at_320px(self):
        page = self.page
        page.set_viewport_size({"width":320,"height":700})
        self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), 320)
        self.assertTrue(page.locator("#activate-camera").is_visible())
        size = page.locator("#camera-frame").bounding_box()
        self.assertGreaterEqual(size["height"], 480)
        self.assertFalse(page.locator("#gobbo-settings").evaluate("(element) => element.open"))
        page.locator("#edit-gobbo").click()
        self.assertTrue(page.locator("#script-input").is_visible())
        self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), 320)
