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
        self.assertGreater(info.width, 0)
        self.assertGreater(info.height, 0)
        self.assertTrue(page.locator("#result-video").is_visible())
        self.assertFalse(page.locator("#prompter").is_visible())
        self.assertEqual(self.errors, [])

    def test_rehearsal_without_camera_on_small_screen(self):
        page=self.page
        page.set_viewport_size({"width":320,"height":700})
        page.locator("#edit-gobbo").click()
        page.locator("#script-input").fill("Test del gobbo senza fotocamera. " * 75)
        self.assertTrue(page.locator("#rehearsal-toggle").is_visible())
        self.assertTrue(page.locator("#rehearsal-restart").is_hidden())
        self.assertTrue(page.locator("#record-stop").is_hidden())
        self.assertFalse(page.evaluate(
            "() => !!document.querySelector('#camera-video').srcObject"))
        page.locator("#rehearsal-toggle").click()
        self.assertTrue(page.locator("#prompter").is_visible())
        self.assertTrue(page.locator("#camera-placeholder").is_hidden())
        self.assertTrue(page.locator("#rehearsal-hint").is_visible())
        self.assertIn("Nessun video registrato",page.locator("#rehearsal-hint").inner_text())
        ARTIFACTS.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(ARTIFACTS/"capture-rehearsal-mobile-320.png"),full_page=True)
        page.wait_for_timeout(900)
        diagnostic=page.evaluate("""() => {
            const el=document.querySelector('#prompter-scroll');
            return {top:el.scrollTop,scrollHeight:el.scrollHeight,
              clientHeight:el.clientHeight,clientWidth:el.clientWidth,
              state:document.querySelector('#capture-state').textContent,
              timer:document.querySelector('#timer-text').textContent,
              visible:getComputedStyle(el).visibility,
              raf:document.visibilityState};
        }""")
        self.assertGreater(diagnostic["top"],0,
                           f"Rehearsal must scroll: {diagnostic}; errors={self.errors}")
        self.assertTrue(page.locator("#download-panel").is_hidden())
        self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"),320)
        page.locator("#rehearsal-toggle").click()
        self.assertEqual(page.locator("#rehearsal-toggle").get_attribute("aria-pressed"),"false")
        page.locator("#rehearsal-restart").click()
        self.assertEqual(page.locator("#rehearsal-toggle").get_attribute("aria-pressed"),"true")
        self.assertFalse(self.errors,self.errors)

    def test_merged_camera_activation_shows_preview_even_when_play_promise_never_resolves(self):
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

    def test_merged_full_camera_frame_and_larger_prompter_at_390px(self):
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

    def test_merged_landscape_camera_source_produces_portrait_preview_and_video(self):
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
        self.assertFalse(page.locator("#gobbo-settings").evaluate("(el)=>el.open"))
        page.locator("#edit-gobbo").click()
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

    def test_rehearsal_live_speed_pause_resume_and_take_reset(self):
        page=self.page
        # Wrap MediaRecorder to prove that the practice mode cannot create a
        # recording, even when it is running and the speed is adjusted.
        page.evaluate("""() => {
          window.__recorderCalls=0;
          window.MediaRecorder=new Proxy(window.MediaRecorder,{
            construct(target,args){
              window.__recorderCalls++;
              return Reflect.construct(target,args);
            }
          });
        }""")
        page.locator("#script-input").fill(
            "Questa è una prova della velocità del gobbo. " * 95
        )
        page.locator("#speed").evaluate("""(el)=>{
          el.value="50";el.dispatchEvent(new Event("input",{bubbles:true}));
        }""")
        self.assertEqual(page.locator("#speed-value").inner_text(),"50 parole/min")
        page.locator("#rehearsal-toggle").click()
        self.assertTrue(page.locator("#prompter").is_visible())
        self.assertTrue(page.locator("#rehearsal-restart").is_visible())
        self.assertTrue(page.locator("#rehearsal-hint").is_visible())
        self.assertEqual(page.locator("#capture-state").inner_text(),"PROVA GOBBO")
        self.assertTrue(page.locator("#rehearsal-toggle").get_attribute("aria-pressed")=="true")
        self.assertEqual(page.evaluate("window.__recorderCalls"),0)
        page.wait_for_timeout(1100)
        scroll=page.locator("#prompter-scroll")
        before=scroll.evaluate("(el)=>el.scrollTop")
        diagnostic=page.evaluate("""() => {
            const el=document.querySelector('#prompter-scroll');
            return {top:el.scrollTop,scrollHeight:el.scrollHeight,
              clientHeight:el.clientHeight,clientWidth:el.clientWidth,
              state:document.querySelector('#capture-state').textContent,
              timer:document.querySelector('#timer-text').textContent,
              raf:document.visibilityState};
        }""")
        self.assertGreater(before,3,
                           f"Rehearsal must advance: {diagnostic}; errors={self.errors}")
        page.locator("#speed").evaluate("""(el)=>{
          el.value="220";el.dispatchEvent(new Event("input",{bubbles:true}));
        }""")
        self.assertEqual(page.locator("#speed-value").inner_text(),"220 parole/min")
        self.assertGreater(scroll.evaluate("(el)=>el.scrollTop"),before-1,
                           "Changing WPM must preserve the current script position")
        page.wait_for_timeout(600)
        self.assertGreater(scroll.evaluate("(el)=>el.scrollTop"),before+12)
        page.locator("#rehearsal-toggle").click()
        self.assertEqual(page.locator("#capture-state").inner_text(),"PROVA IN PAUSA")
        paused=scroll.evaluate("(el)=>el.scrollTop")
        page.wait_for_timeout(450)
        self.assertAlmostEqual(scroll.evaluate("(el)=>el.scrollTop"),paused,delta=1)
        page.locator("#rehearsal-toggle").click()
        page.wait_for_timeout(400)
        self.assertGreater(scroll.evaluate("(el)=>el.scrollTop"),paused+3)
        page.locator("#rehearsal-restart").click()
        self.assertLess(scroll.evaluate("(el)=>el.scrollTop"),6,
                        "Restart must return to the first line")
        self.assertEqual(page.evaluate("window.__recorderCalls"),0)
        self.assertTrue(page.locator("#record-stop").is_hidden())
        ARTIFACTS.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(ARTIFACTS/"capture-rehearsal-desktop-1440.png"),full_page=True)
        # Activate a fake camera while rehearsing: the rehearsal is reset
        # without any recording, then the real REC flow still works.
        page.locator("#activate-camera").click()
        page.locator("#record-start").wait_for(state="visible",timeout=20000)
        self.assertEqual(page.locator("#rehearsal-toggle").get_attribute("aria-pressed"),"false")
        self.assertEqual(page.evaluate("window.__recorderCalls"),0)
        page.locator("#rehearsal-toggle").click()
        page.wait_for_timeout(400)
        self.assertGreater(scroll.evaluate("(el)=>el.scrollTop"),0)
        page.locator("#record-start").click()
        self.assertTrue(page.locator("#rehearsal-toggle").is_hidden())
        self.assertEqual(scroll.evaluate("(el)=>el.scrollTop"),0)
        page.locator("#record-stop").wait_for(state="visible",timeout=15000)
        self.assertEqual(page.evaluate("window.__recorderCalls"),1,
                         "Only an explicit Registra click may create a recorder")
        page.wait_for_timeout(900)
        page.locator("#record-stop").click()
        page.locator("#download-panel").wait_for(state="visible",timeout=20000)
        self.assertTrue(page.locator("#rehearsal-toggle").is_hidden())
        self.assertFalse(self.errors,self.errors)

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
            if width==950:
                for axis in ("x","y","zoom"):
                    group=page.locator(".crop-setting").filter(
                        has=page.locator(f"#crop-{axis}")).bounding_box()
                    label=page.locator(f"#crop-{axis}-value").bounding_box()
                    slider=page.locator(f"#crop-{axis}").bounding_box()
                    self.assertGreater(slider["y"],label["y"],
                                       f"Crop {axis} slider should sit below its label")
                    self.assertGreaterEqual(slider["x"],group["x"]-1)
                    self.assertLessEqual(slider["right"] if "right" in slider else
                                         slider["x"]+slider["width"],
                                         group["x"]+group["width"]+1)
            if width in (950,390,320):
                ARTIFACTS.mkdir(parents=True,exist_ok=True)
                page.screenshot(path=str(ARTIFACTS/f"capture-responsive-{width}.png"),full_page=True)
        self.assertEqual(self.errors,[])
