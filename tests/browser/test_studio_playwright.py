"""Playwright Studio UI audit with real Chromium and synthetic FFmpeg footage."""
from __future__ import annotations
import json, math, os, struct, subprocess, tempfile, threading, time, unittest, wave
from pathlib import Path
from playwright.sync_api import sync_playwright
from pausio.studio import StudioWorkspace, create_server

ARTIFACTS=Path(os.environ.get("PAUSIO_UI_ARTIFACTS","/tmp/pausio-ui-audit"))

def sample_video(folder):
    wav=folder/"audio.wav"
    rate=22050
    with wave.open(str(wav),"wb") as out:
        out.setnchannels(1);out.setsampwidth(2);out.setframerate(rate)
        data=bytearray()
        for i in range(rate*4):
            t=i/rate
            sample=0 if 1.1<=t<2.2 else int(10000*math.sin(2*math.pi*440*t))
            data.extend(struct.pack("<h",sample))
        out.writeframes(data)
    target=folder/"audit-video.mp4"
    subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-nostdin","-y",
       "-f","lavfi","-i","color=c=blue:s=360x640:r=24:d=4","-i",str(wav),
       "-shortest","-c:v","libx264","-preset","ultrafast","-pix_fmt","yuv420p",
       "-c:a","aac","-b:a","96k","-movflags","+faststart",str(target)],
       check=True,timeout=45)
    return target

def metrics(page):
    return page.evaluate("""() => {
      const rect = selector => {
        let n=document.querySelector(selector);
        if(!n)return null;
        let r=n.getBoundingClientRect(),s=getComputedStyle(n);
        return {x:r.x,y:r.y,w:r.width,h:r.height,right:r.right,bottom:r.bottom,
                visible:s.display!=='none'&&s.visibility!=='hidden'};
      };
      return {width:innerWidth,height:innerHeight,
        scrollWidth:document.documentElement.scrollWidth,
        rail:rect('.rail'),stage:rect('.stage'),
        inspector:rect('.inspector'),timeline:rect('.timeline-panel'),
        timelineActions:rect('.timeline-actions'),video:rect('#video-workspace'),
        empty:rect('#empty-state'),import:rect('#import-action'),
        preview:rect('#preview-action'),export:rect('#export-action'),
        track:rect('#timeline-track'),trim:rect('.trim-handle.end'),
        approve:rect('#approve-action')};
    }""")

class StudioPlaywrightAudit(unittest.TestCase):
    def setUp(self):
        ARTIFACTS.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.workspace=StudioWorkspace()
        self.server=create_server(port=0,workspace=self.workspace)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.pw=sync_playwright().start()
        self.browser=self.pw.chromium.launch(headless=True,args=["--no-sandbox"])
        self.context=self.browser.new_context(viewport={"width":1440,"height":900},accept_downloads=True)
        self.page=self.context.new_page()
        self.errors=[]
        self.page.on("pageerror",lambda err:self.errors.append(str(err)))
        self.page.on("console",lambda msg:self.errors.append("console: "+msg.text) if msg.type=="error" else None)
        self.page.goto(f"http://127.0.0.1:{self.server.server_port}/",wait_until="networkidle")

    def tearDown(self):
        try:
            self.shot(self._testMethodName+"-final")
            (ARTIFACTS/(self._testMethodName+"-errors.json")).write_text(
                json.dumps(self.errors,indent=2),encoding="utf-8")
        finally:
            self.context.close();self.browser.close();self.pw.stop()
            self.server.shutdown();self.server.server_close()
            self.thread.join(timeout=3);self.workspace.close();self.temp.cleanup()

    def shot(self,name):
        self.page.screenshot(path=str(ARTIFACTS/(name+".png")),full_page=True)

    def record(self,name,data):
        print("UI_AUDIT "+name+" "+json.dumps(data,ensure_ascii=False),flush=True)
        (ARTIFACTS/(name+".json")).write_text(json.dumps(data,indent=2),encoding="utf-8")

    def state(self):
        return self.page.evaluate("() => fetch('/api/state').then(r=>r.json())")

    def wait_condition(self,predicate,timeout=30000):
        deadline=time.monotonic()+timeout/1000
        while time.monotonic()<deadline:
            if predicate():
                return
            self.page.wait_for_timeout(120)
        self.fail("Timeout waiting for UI condition; state="+repr(self.state())+
                  "; browser errors="+repr(self.errors))

    def wait_state(self,kind,value,timeout=90000):
        def ok():
            state=self.state()
            if kind=="revision": return state["project_revision"]>=value
            if kind=="waveform": return state["waveform_status"]==value
            return state["job"]["kind"]==kind and state["job"]["status"]==value
        self.wait_condition(ok,timeout=timeout)
        return self.state()

    def upload_analyze(self):
        self.page.locator("#file-input").set_input_files(str(sample_video(self.root)))
        self.wait_condition(
            lambda: "audit-video.mp4" in self.page.locator("#project-title").inner_text(),
            timeout=30000)
        self.wait_state("waveform","ready",timeout=30000)
        self.wait_condition(lambda: "Waveform" in self.page.locator("#waveform-state").inner_text(),
                            timeout=12000)
        self.assertEqual(self.page.locator("#cut-preset").input_value(),"natural")
        self.page.locator("#analyze-action").click()
        result=self.wait_state("analyze","completed")
        self.wait_condition(lambda: self.page.locator(".segment-card").count()>=2,
                            timeout=30000)
        return result

    def test_layout_across_five_viewports(self):
        results={}
        for width,height in [(1440,900),(1024,768),(768,900),(390,844),(320,700)]:
            self.page.set_viewport_size({"width":width,"height":height})
            self.page.wait_for_timeout(250)
            key=f"empty-{width}x{height}"
            results[key]=metrics(self.page)
            self.shot(key)
        self.record("empty-layout",results)
        self.assertFalse(self.errors,self.errors)
        for name,item in results.items():
            self.assertLessEqual(item["scrollWidth"],item["width"]+3,
                                 "horizontal overflow "+name+": "+str(item))
        self.assertLessEqual(results["empty-1440x900"]["timeline"]["bottom"],902,
                             "Desktop timeline should remain visible with player")
        self.assertTrue(self.page.locator("#empty-import").is_visible())
        self.assertTrue(self.page.locator("#export-action").is_disabled())

    def test_real_edit_preview_export_and_project_commands(self):
        initial=self.upload_analyze()
        self.assertGreaterEqual(len(initial["editor_segments"]),2)
        for width,height in [(1440,900),(1024,768),(390,844),(320,700)]:
            self.page.set_viewport_size({"width":width,"height":height})
            self.page.wait_for_timeout(250)
            key=f"analyzed-{width}x{height}"
            info=metrics(self.page)
            self.record(key,info);self.shot(key)
            self.assertLessEqual(info["scrollWidth"],width+3,
                                 f"Editing overflow at {width}px: {info}")
            if width>=1024:
                self.assertLessEqual(info["timeline"]["bottom"],height+2,
                                     "Timeline must stay with desktop video")
                self.assertLessEqual(info["approve"]["bottom"],height+2,
                                     "Approval must stay visible on desktop")
            if width<=390:
                self.assertTrue(self.page.locator(".rail-intro").is_hidden(),
                                "After importing, the mobile workflow introduction must collapse")
                self.assertLessEqual(info["timeline"]["bottom"],info["inspector"]["y"]+2,
                                     "Mobile timeline should precede inspector")
        self.page.set_viewport_size({"width":1440,"height":900})
        self.page.locator("#timeline-zoom").select_option("4")
        sizes=self.page.evaluate("""() => ({
           track:document.querySelector('#timeline-track').getBoundingClientRect().width,
           surface:document.querySelector('#timeline-surface').getBoundingClientRect().width
        })""")
        self.assertGreater(sizes["track"],sizes["surface"]*2.5,sizes)
        first=self.state()
        old_end=first["editor_segments"][0]["end_ms"]
        handle=self.page.locator(".trim-handle.end").first
        handle.focus();handle.press("ArrowLeft")
        changed=self.wait_state("revision",first["project_revision"]+1)
        self.assertEqual(changed["editor_segments"][0]["end_ms"],old_end-100)
        self.page.locator("#undo-action").click()
        undone=self.wait_state("revision",changed["project_revision"]+1)
        self.assertEqual(undone["editor_segments"][0]["end_ms"],old_end)
        self.page.locator("#redo-action").click()
        redone=self.wait_state("revision",undone["project_revision"]+1)
        self.assertEqual(redone["editor_segments"][0]["end_ms"],old_end-100)
        with self.page.expect_download() as download:
            self.page.locator("#project-export").click()
        saved=self.root/"project.pausio.json";download.value.save_as(saved)
        data=json.loads(saved.read_text())
        self.assertEqual(data["schema_version"],2)
        self.assertIn("segment.update",[c["type"] for c in data["commands"]])

        self.page.locator("#preview-action").click()
        draft=self.wait_state("preview","completed",timeout=120000)
        self.assertTrue(draft["preview_ready"])
        self.wait_condition(lambda: "FFmpeg" in self.page.locator("#canvas-badge").inner_text(),
                            timeout=30000)
        self.shot("rendered-draft")
        self.page.locator("#approve-action").click()
        approved=self.wait_state("revision",redone["project_revision"]+1)
        self.assertTrue(approved["approved"])
        self.page.locator("#export-action").click()
        final=self.wait_state("render","completed",timeout=120000)
        self.assertTrue(final["export_ready"])
        self.wait_condition(lambda: self.page.locator("#download-action").is_visible(),
                            timeout=30000)
        self.shot("export-ready")
        self.record("editing-flow",{
          "source_ms":initial["media"]["duration_ms"],
          "segments":len(initial["editor_segments"]),
          "revision":final["project_revision"],
          "preview_ready":draft["preview_ready"],
          "export_ready":final["export_ready"],
          "errors":self.errors})
        self.assertFalse(self.errors,self.errors)

    def test_preset_selection_reanalysis_and_mobile_layout(self):
        initial=self.upload_analyze()
        self.assertEqual(initial["analysis_settings"]["preset"],"natural")
        self.page.locator("#cut-preset").select_option("dynamic")
        self.assertEqual(self.page.locator("#cut-preset").input_value(),"dynamic")
        self.assertEqual(self.page.locator('[data-cut-setting="min_silence_ms"]').input_value(),"350")
        self.page.locator("#analyze-action").click()
        state=self.wait_state("revision",initial["project_revision"]+1)
        self.assertEqual(state["analysis_settings"]["preset"],"dynamic")
        self.wait_condition(lambda: self.page.locator("#cut-preset").input_value()=="dynamic")
        self.wait_condition(lambda: "rilevate" in self.page.locator("#cut-result").inner_text())
        self.page.locator("#cut-advanced summary").click()
        self.page.locator('[data-cut-setting="noise_db"]').fill("-23")
        self.page.locator('[data-cut-setting="noise_db"]').press("Tab")
        self.assertEqual(self.page.locator("#cut-preset").input_value(),"custom")
        self.page.locator("#analyze-action").click()
        changed=self.wait_state("revision",state["project_revision"]+1)
        self.assertEqual(changed["analysis_settings"]["preset"],"custom")
        self.assertEqual(changed["analysis_settings"]["noise_db"],-23)
        for width,height in [(1440,900),(390,844),(320,700)]:
            self.page.set_viewport_size({"width":width,"height":height})
            self.page.wait_for_timeout(120)
            self.assertLessEqual(metrics(self.page)["scrollWidth"],width+3)
            self.shot("cut-presets-"+str(width))
        self.assertFalse(self.errors,self.errors)

    def test_simulation_skips_short_cut_and_resumes_at_next_keep(self):
        """A 150 ms gap can fall entirely between two timeupdate events."""
        initial=self.upload_analyze()
        self.assertEqual(len(initial["editor_segments"]),2)
        # Create a valid short exclusion between two kept clips using the UI.
        end_input=self.page.locator(".segment-card").nth(0).locator(".end-input")
        end_input.fill("1.70")
        end_input.press("Tab")
        revised=self.wait_state("revision",initial["project_revision"]+1)
        start_input=self.page.locator(".segment-card").nth(1).locator(".start-input")
        start_input.fill("1.85")
        start_input.press("Tab")
        revised=self.wait_state("revision",revised["project_revision"]+1)
        self.assertEqual(revised["editor_segments"][0]["end_ms"],1700)
        self.assertEqual(revised["editor_segments"][1]["start_ms"],1850)
        self.page.locator('[data-mode="edited"]').click()
        self.assertEqual(self.page.locator('[data-mode="edited"]').get_attribute("aria-pressed"),"true")
        self.page.evaluate("""() => {
          window.__simSeeks=[];
          let v=document.querySelector('#preview-video');
          v.currentTime=1.60;
          v.addEventListener('seeking',()=>window.__simSeeks.push(v.currentTime));
        }""")
        self.wait_condition(lambda: self.page.evaluate("""() => {
          let v=document.querySelector('#preview-video');
          return !v.seeking && Math.abs(v.currentTime-1.60)<0.04;
        }"""))
        self.page.locator("#play-pause").click()
        self.wait_condition(lambda: self.page.evaluate(
            "() => window.__simSeeks.some(t => t>=1.84 && t<=1.90)"),timeout=7000)
        self.assertGreaterEqual(self.page.evaluate(
            "() => document.querySelector('#preview-video').currentTime"),1.84)
        self.page.locator("#play-pause").click()
        # Scrubbing into a discarded gap must continue at the next kept clip,
        # not restart the entire video from the beginning.
        self.page.evaluate("() => document.querySelector('#preview-video').currentTime=1.75")
        self.wait_condition(lambda: self.page.evaluate(
            "() => !document.querySelector('#preview-video').seeking"))
        self.page.locator("#play-pause").click()
        self.wait_condition(lambda: self.page.evaluate(
            "() => document.querySelector('#preview-video').currentTime>=1.85"))
        self.assertFalse(self.errors,self.errors)

    def test_pointer_trim_is_single_edit(self):
        self.upload_analyze()
        self.page.locator("#timeline-zoom").select_option("2")
        self.page.wait_for_timeout(300)
        before=self.state()
        b=self.page.locator(".trim-handle.end").first.bounding_box()
        self.assertIsNotNone(b)
        x=b["x"]+b["width"]/2;y=b["y"]+b["height"]/2
        self.page.mouse.move(x,y);self.page.mouse.down()
        self.page.mouse.move(x-18,y,steps=8);self.page.mouse.up()
        changed=self.wait_state("revision",before["project_revision"]+1,timeout=30000)
        self.assertEqual(changed["project_revision"],before["project_revision"]+1)
        self.assertEqual(changed["last_command"],"segment.update")
        self.assertLess(changed["editor_segments"][0]["end_ms"],
                        before["editor_segments"][0]["end_ms"])
        self.shot("pointer-trim")
        self.record("pointer-trim",{
          "old_end":before["editor_segments"][0]["end_ms"],
          "new_end":changed["editor_segments"][0]["end_ms"],
          "revision":changed["project_revision"],"errors":self.errors})
        self.assertFalse(self.errors,self.errors)
