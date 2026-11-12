"""Simulated mobile camera E2E: actual MediaRecorder video download in Chromium."""
from __future__ import annotations

import os
import tempfile
import threading
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright

from pausio.studio import StudioWorkspace, create_server
from pausio.media import probe

ARTIFACTS=Path(os.environ.get("PAUSIO_UI_ARTIFACTS","/tmp/pausio-ui-audit"))


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
        # A real media parser must accept the downloaded bytes as a Pausio input.
        info = probe(path)
        self.assertGreater(info.duration_ms, 700)
        self.assertTrue(info.has_audio, "Recorded take must retain microphone audio")
        self.assertGreater(info.width, 0)
        self.assertGreater(info.height, 0)
        self.assertTrue(page.locator("#result-video").is_visible())
        self.assertFalse(page.locator("#prompter").is_visible())
        self.assertEqual(self.errors, [])

    def test_camera_preview_is_responsive_at_320px(self):
        page = self.page
        page.set_viewport_size({"width":320,"height":700})
        self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), 320)
        self.assertTrue(page.locator("#activate-camera").is_visible())
        self.assertTrue(page.locator("#script-input").is_visible())

class DesktopCapturePlaywrightTests(unittest.TestCase):
    """Desktop webcam often delivers 16:9; downloaded bytes must be 9:16."""

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.workspace=StudioWorkspace()
        self.server=create_server(port=0,workspace=self.workspace)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.pw=sync_playwright().start()
        self.browser=self.pw.chromium.launch(headless=True,args=[
            "--no-sandbox","--use-fake-device-for-media-stream","--use-fake-ui-for-media-stream",
        ])
        self.context=self.browser.new_context(
            viewport={"width":1440,"height":900},
            permissions=["camera","microphone"],
            accept_downloads=True,
        )
        self.page=self.context.new_page()
        self.errors=[]
        self.page.on("pageerror",lambda error:self.errors.append(str(error)))
        self.page.goto(f"http://127.0.0.1:{self.server.server_port}/capture",
                       wait_until="networkidle")

    def tearDown(self):
        self.context.close();self.browser.close();self.pw.stop()
        self.server.shutdown();self.server.server_close()
        self.thread.join(timeout=3)
        self.workspace.close();self.temp.cleanup()

    def test_desktop_portrait_crop_microphone_and_direct_studio_import(self):
        page=self.page
        self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"),1440)
        self.assertTrue(page.locator(".device-settings").is_visible())
        self.assertTrue(page.locator("#capture-quality").is_visible())
        page.locator("#script-input").fill("Prova desktop 9:16 con webcam e microfono.")
        page.locator("#activate-camera").click()
        page.locator("#record-start").wait_for(state="visible",timeout=20000)
        self.assertTrue(page.locator("#portrait-canvas").is_visible())
        self.assertTrue(page.locator("#camera-frame").evaluate(
            "(el)=>el.classList.contains('is-composing')"))
        dimensions=page.locator("#portrait-canvas").evaluate(
            "(canvas)=>[canvas.width,canvas.height]")
        self.assertEqual(dimensions,[720,1280])
        ARTIFACTS.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(ARTIFACTS/"capture-desktop-portrait-1440.png"),full_page=True)
        self.assertTrue(page.locator("#capture-tech-info").inner_text().count("9:16"))
        self.assertGreaterEqual(page.locator("#video-device option").count(),2)
        self.assertGreaterEqual(page.locator("#audio-device option").count(),2)
        page.locator("#crop-x").evaluate("""el=>{
          el.value="85";el.dispatchEvent(new Event("input",{bubbles:true}));
        }""")
        self.assertEqual(page.locator("#crop-x-value").inner_text(),"85%")
        page.locator("#crop-reset").click()
        self.assertEqual(page.locator("#crop-x-value").inner_text(),"50%")
        page.locator("#record-start").click()
        page.locator("#record-stop").wait_for(state="visible",timeout=15000)
        self.assertTrue(page.locator("#video-device").is_disabled())
        self.assertTrue(page.locator("#capture-quality").is_disabled())
        page.wait_for_timeout(2000)
        page.locator("#record-stop").click()
        page.locator("#download-panel").wait_for(state="visible",timeout=20000)
        self.assertTrue(page.locator("#open-in-studio").is_visible())
        page.screenshot(path=str(ARTIFACTS/"capture-desktop-take-ready-1440.png"),full_page=True)
        self.assertFalse(page.locator("#portrait-canvas").is_visible())
        with page.expect_download(timeout=20000) as info:
            page.locator("#download-video").click()
        download=info.value
        target=Path(self.temp.name)/download.suggested_filename
        download.save_as(target)
        self.assertGreater(target.stat().st_size,1000)
        media=probe(target)
        self.assertEqual((media.width,media.height),(720,1280),
                         "The exported file, not just the UI, must be portrait")
        self.assertTrue(media.has_audio,
                        "Canvas video must be muxed with the original microphone")
        self.assertGreater(media.duration_ms,1000)
        page.locator("#open-in-studio").click()
        page.wait_for_url(f"http://127.0.0.1:{self.server.server_port}/",timeout=25000)
        state=page.evaluate("() => fetch('/api/state').then(r=>r.json())")
        self.assertIn("pausio-take-",state["file"])
        self.assertEqual((state["media"]["width"],state["media"]["height"]),
                         (720,1280)) if "width" in state.get("media",{}) else None
        self.assertEqual(self.errors,[])

    def test_desktop_capture_layout_responsive_tablet(self):
        page=self.page
        for width in (1100,950,860,768,390,320):
            page.set_viewport_size({"width":width,"height":900})
            page.wait_for_timeout(70)
            overflow=page.evaluate("document.documentElement.scrollWidth")
            self.assertLessEqual(overflow,width+2,
                                 f"Capture layout overflow at {width}: {overflow}")
            self.assertTrue(page.locator("#activate-camera").is_visible())
            self.assertTrue(page.locator("#video-device").is_visible())
            if width in (950,390,320):
                ARTIFACTS.mkdir(parents=True,exist_ok=True)
                page.screenshot(path=str(ARTIFACTS/f"capture-responsive-{width}.png"),full_page=True)
        self.assertEqual(self.errors,[])
