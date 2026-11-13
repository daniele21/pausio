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
        self.http_errors=[]
        self.page.on("response",lambda response:self.http_errors.append(
            f"{response.status} {response.url}") if response.status >= 400 else None)
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

    def test_ffmpeg_preview_disabled_state_and_persistent_failure_recovery(self):
        """A failed render must not leave the disabled preview unexplained."""
        from unittest.mock import patch
        from pausio.media import MediaError

        self.upload_analyze()
        self.page.locator('[data-workspace-nav="cuts"]').click()
        self.assertTrue(self.page.locator('[data-mode="rendered"]').is_disabled())
        self.assertIn("Genera preview",self.page.locator("#preview-state-note").inner_text())

        with patch("pausio.studio.render",side_effect=MediaError(
            "ffmpeg failed (exit 8): No such filter: 'ass'")):
            self.page.locator("#preview-action").click()
            failed=self.wait_state("preview","failed",timeout=30000)
            self.assertFalse(failed["preview_ready"])
            self.wait_condition(lambda: "No such filter" in
                                self.page.locator("#preview-state-note").inner_text())
            self.assertTrue(self.page.locator('[data-mode="rendered"]').is_disabled())
            self.assertTrue(self.page.locator("#preview-action").is_enabled())

        # Error stays visible after a refresh; it must not be a 6-second toast.
        self.page.reload(wait_until="networkidle")
        self.assertIn("No such filter",self.page.locator("#preview-state-note").inner_text())
        self.page.locator("#preview-action").click()
        ready=self.wait_state("preview","completed",timeout=120000)
        self.assertTrue(ready["preview_ready"])
        self.wait_condition(lambda: self.page.locator('[data-mode="rendered"]').is_enabled())
        self.assertTrue(self.page.locator("#preview-state-note").is_hidden())
        self.assertFalse(self.errors,self.errors)

    def test_five_second_quick_preview_in_modal_and_invalidation(self):
        initial=self.upload_analyze()
        self.assertTrue(self.page.locator("#quick-preview-action").is_disabled())
        self.page.locator("#preview-action").click()
        ready=self.wait_state("preview","completed",timeout=120000)
        self.assertTrue(ready["preview_ready"])
        self.wait_condition(lambda:self.page.locator("#quick-preview-action").is_enabled())
        self.page.locator("#quick-preview-action").click()
        clipped=self.wait_state("preview_range","completed",timeout=60000)
        self.assertTrue(clipped["preview_range_ready"],clipped["job"])
        self.wait_condition(lambda:self.page.locator("#quick-preview-dialog").is_visible())
        self.assertTrue(self.page.locator("#quick-preview-video").is_visible())
        self.shot("quick-preview-dialog")
        self.page.locator("#quick-preview-close").click()
        self.assertFalse(self.page.locator("#quick-preview-dialog").is_visible())
        self.page.keyboard.press("Control+z")
        self.wait_state("revision",initial["project_revision"]+1)
        self.assertTrue(self.page.locator("#quick-preview-action").is_disabled())
        self.assertFalse(self.errors,self.errors)

    def test_visual_fx_has_dedicated_workspace_without_cut_card_scrolling(self):
        self.upload_analyze()
        self.page.locator('[data-workspace-nav="visual"]').click()
        self.assertEqual(self.page.locator("#app").get_attribute("data-workspace"),"visual")
        self.assertTrue(self.page.locator("#visual-fx-panel").is_visible())
        self.assertTrue(self.page.locator("#visual-fx-suggest").is_visible())
        self.assertTrue(self.page.locator("#visual-transition-panel").is_visible())
        self.assertFalse(self.page.locator("#segment-list").is_visible())
        self.assertTrue(self.page.locator("#visual-fx-preview").is_enabled())
        self.shot("video-fx-workspace")
        self.page.locator("#visual-fx-kind").select_option("ease_push")
        self.page.locator("#visual-fx-add").click()
        self.wait_condition(lambda: self.page.locator(".visual-fx-mark").count()==1)
        self.assertEqual(self.state()["video_fx"][0]["kind"],"ease_push")
        self.assertFalse(self.errors,self.errors)

    def test_local_image_pip_import_typed_edit_and_real_ffmpeg_preview(self):
        initial=self.upload_analyze()
        self.page.locator('[data-workspace-nav="visual"]').click()
        self.assertTrue(self.page.locator("#pip-image-import").is_enabled())
        image=self.root/"screen.png"
        subprocess.run([
            "ffmpeg","-hide_banner","-nostdin","-v","error","-y",
            "-f","lavfi","-i","color=c=red:s=140x80:r=1:d=1",
            "-frames:v","1","-threads:v","1",str(image)
        ],check=True,timeout=35)
        self.page.locator("#pip-image-input").set_input_files(str(image))
        added=self.wait_state("revision",initial["project_revision"]+1)
        self.assertEqual(len(added["image_overlays"]),1)
        self.assertTrue(added["image_overlays"][0]["available"])
        self.assertTrue(self.page.locator("[data-pip-id]").is_visible())
        item=self.page.locator("[data-pip-id]").first
        item.locator('input[aria-label="Larghezza (%) immagine PIP"]').fill("60")
        item.get_by_role("button",name="Salva posizione").click()
        revised=self.wait_state("revision",added["project_revision"]+1)
        self.assertEqual(revised["image_overlays"][0]["width_pct"],60)
        self.assertEqual(revised["image_overlays"][0]["asset_sha256"],
                         added["image_overlays"][0]["asset_sha256"])
        self.page.locator("#pip-image-preview").click()
        ready=self.wait_state("preview","completed",timeout=120000)
        self.assertTrue(ready["preview_ready"],ready["job"])
        self.wait_condition(lambda:self.page.locator('[data-mode="rendered"]').is_enabled())
        self.shot("image-pip-rendered-preview")
        self.page.keyboard.press("Control+z")
        undone=self.wait_state("revision",revised["project_revision"]+1)
        self.assertEqual(undone["image_overlays"][0]["width_pct"],55)
        self.page.keyboard.press("Control+z")
        gone=self.wait_state("revision",undone["project_revision"]+1)
        self.assertEqual(gone["image_overlays"],[])
        self.assertFalse(self.errors,self.errors)

    def test_graphic_overlay_typed_edit_and_real_ffmpeg_preview(self):
        """Add source-bound graphic card, render actual ASS and undo/import."""
        initial=self.upload_analyze()
        self.page.locator('[data-workspace-nav="cuts"]').click()
        start=initial["editor_segments"][0]["start_ms"]/1000
        self.page.evaluate("(at)=>{document.querySelector('#preview-video').currentTime=at}",start+0.15)
        self.page.locator("#graphic-text").fill("1.379 segreti")
        self.page.locator("#graphic-kind").select_option("stat")
        self.page.locator("#graphic-animation").select_option("slide")
        self.assertTrue(self.page.locator("#graphic-add").is_enabled())
        self.page.locator("#graphic-add").click()
        added=self.wait_state("revision",initial["project_revision"]+1)
        self.assertEqual(len(added["graphic_overlays"]),1)
        self.assertEqual(added["graphic_overlays"][0]["text"],"1.379 segreti")
        item=self.page.locator("[data-graphic-id]").first
        item.locator('select[aria-label="Stile grafica"]').select_option("code")
        item.locator('select[aria-label="Animazione grafica"]').select_option("pop")
        item.locator('input[aria-label="Colore grafica"]').fill("#00ccff")
        item.locator('input[aria-label="Durata grafica (ms)"]').fill("400")
        item.get_by_role("button",name="Salva modifiche").click()
        updated=self.wait_state("revision",added["project_revision"]+1)
        self.assertEqual(updated["graphic_overlays"][0]["kind"],"code")
        self.assertEqual(updated["graphic_overlays"][0]["animation"],"pop")
        self.assertEqual(updated["graphic_overlays"][0]["color"],"#00CCFF")
        self.assertEqual(updated["graphic_overlays"][0]["end_ms"]-
                         updated["graphic_overlays"][0]["start_ms"],400)
        self.page.locator("#graphic-preview").click()
        preview=self.wait_state("preview","completed",timeout=120000)
        self.assertTrue(preview["preview_ready"])
        self.wait_condition(lambda: self.page.locator('[data-mode="rendered"]').is_enabled())
        self.shot("graphic-overlay-preview")
        # The dedicated Video FX workspace hides the legacy left project rail.
        # Use its supported global Undo shortcut, as creators do on desktop.
        self.page.keyboard.press("Control+z")
        undone=self.wait_state("revision",updated["project_revision"]+1)
        self.assertEqual(undone["graphic_overlays"][0]["kind"],"stat")
        self.page.keyboard.press("Control+z")
        empty=self.wait_state("revision",undone["project_revision"]+1)
        self.assertEqual(empty["graphic_overlays"],[])
        self.assertFalse(self.errors,self.errors)

    def test_pulse_and_sweep_can_be_added_and_rendered_in_video_fx_workspace(self):
        initial=self.upload_analyze()
        self.page.locator("#restore-all").click()
        changed=self.wait_state("revision",initial["project_revision"]+1)
        self.page.locator('[data-workspace-nav="visual"]').click()
        for kind,at in (("pulse",0.12),("sweep",2.05)):
            self.page.evaluate(
                "(at)=>{document.querySelector('#preview-video').currentTime=at}",at)
            self.page.locator("#visual-fx-kind").select_option(kind)
            self.page.locator("#visual-fx-add").click()
            expected=changed["project_revision"]+1
            changed=self.wait_state("revision",expected)
        self.assertEqual([fx["kind"] for fx in changed["video_fx"]],
                         ["pulse","sweep"])
        self.assertEqual(changed["video_fx"][1]["anchor_x_pct"],63)
        self.page.locator("#visual-fx-preview").click()
        ready=self.wait_state("preview","completed",timeout=120000)
        self.assertTrue(ready["preview_ready"],ready["job"])
        self.wait_condition(lambda: self.page.locator('[data-mode="rendered"]').is_enabled())
        self.shot("pulse-sweep-rendered-preview")
        self.assertFalse(self.errors,self.errors)

    def test_video_fx_manual_automatic_review_and_real_preview(self):
        """Visible 9:16 zoom editing + evidence-only suggestion + undo/export."""
        initial=self.upload_analyze()
        self.page.locator('[data-workspace-nav="cuts"]').click()
        self.assertTrue(self.page.locator("#visual-fx-panel").is_visible())
        self.assertEqual(self.page.locator("#visual-fx-preset").input_value(),"naturale")
        revision=initial["project_revision"]
        self.page.locator("#visual-fx-suggest").click()
        self.wait_condition(lambda: "proposti" in self.page.locator(
            "#visual-fx-suggest-status").inner_text())
        # A suggestion MUST NOT mutate the project. All proposals have exact
        # source timestamps, and none are silently approved.
        self.assertEqual(self.state()["project_revision"], revision)
        self.assertEqual(self.state()["video_fx"], [])
        self.assertGreaterEqual(self.page.locator(".visual-fx-entry.is-suggested").count(),1)
        self.page.locator(".visual-fx-entry.is-suggested button").first.click()
        added=self.wait_state("revision", revision+1)
        self.assertEqual(len(added["video_fx"]),1)
        fx=added["video_fx"][0]
        self.assertEqual(fx["kind"],"punch")
        self.assertFalse(added["approved"])
        self.wait_condition(lambda: self.page.locator(".visual-fx-mark").count()==1)
        self.assertTrue(self.page.locator(".visual-fx-entry:not(.is-suggested)").is_visible())
        self.page.locator("#visual-fx-preview").click()
        preview=self.wait_state("preview","completed",timeout=120000)
        self.assertTrue(preview["preview_ready"])
        self.shot("video-fx-rendered-preview")
        # The cut-review workspace deliberately collapses the project rail;
        # keyboard history shortcuts must remain usable across workspaces.
        self.wait_condition(lambda: self.page.locator("#visual-fx-preview").is_enabled())
        self.page.keyboard.press("Control+z")
        undone=self.wait_state("revision",added["project_revision"]+1)
        self.assertEqual(undone["video_fx"],[])
        self.page.keyboard.press("Control+Shift+z")
        redone=self.wait_state("revision",undone["project_revision"]+1)
        self.assertEqual(len(redone["video_fx"]),1)
        self.assertEqual(redone["video_fx"][0],fx)
        # Manual adjustment is a single typed update command.
        self.page.locator(".visual-fx-entry:not(.is-suggested) input[aria-label='Zoom finale (%)']").fill("112")
        self.page.locator(".visual-fx-entry:not(.is-suggested) button",has_text="Salva modifiche").click()
        edited=self.wait_state("revision",redone["project_revision"]+1)
        self.assertEqual(edited["video_fx"][0]["end_scale_pct"],112)
        self.assertEqual(edited["video_fx"][0]["start_scale_pct"],112)
        # Project IO belongs to Media workspace, not focused Cut review.
        self.page.locator('[data-workspace-nav="media"]').click()
        with self.page.expect_download() as download:
            self.page.locator("#project-export").click()
        exported=self.root/"visual-fx.pausio.json"
        download.value.save_as(exported)
        document=json.loads(exported.read_text())
        self.assertEqual(document["schema_version"],7)
        self.assertIn("video.transform.update",[row["type"] for row in document["commands"]])
        self.assertFalse(self.errors,self.errors)

    def test_face_anchor_optional_ui_requires_reviewed_typed_edit(self):
        from unittest.mock import patch
        state=self.upload_analyze()
        self.page.locator('[data-workspace-nav="cuts"]').click()
        self.page.evaluate("() => document.getElementById('preview-video').currentTime=2.65")
        before=self.state()["project_revision"]
        self.page.locator("#visual-fx-add").click()
        added=self.wait_state("revision",before+1)
        self.assertEqual(len(added["video_fx"]),1)
        effect=added["video_fx"][0]
        self.assertTrue(self.page.locator("#face-analyze").is_visible())
        with patch("pausio.studio.propose_face_anchor",return_value={
            "status":"ready","anchor_x_pct":77,"anchor_y_pct":49,
            "samples":5,"method":"local-haar-stable-crop-v1"
        }):
            self.page.locator("#face-analyze").click()
            self.wait_condition(lambda:self.page.locator("#face-accept").is_visible())
        # Suggestions never alter the stored event until explicit acceptance.
        self.assertEqual(self.state()["project_revision"],added["project_revision"])
        self.assertEqual(self.state()["video_fx"][0],effect)
        self.page.locator("#face-accept").click()
        changed=self.wait_state("revision",added["project_revision"]+1)
        self.assertEqual(changed["video_fx"][0]["anchor_x_pct"],77)
        self.assertEqual(changed["video_fx"][0]["anchor_y_pct"],49)
        self.assertFalse(self.errors,self.errors)

    def test_custom_fx_profile_is_real_editable_readonly_proposal_ui(self):
        initial=self.upload_analyze()
        self.page.locator('[data-workspace-nav="cuts"]').click()
        self.page.locator("#visual-fx-preset").select_option("personalizzato")
        self.assertTrue(self.page.locator("#visual-fx-custom").is_visible())
        self.page.locator("#visual-fx-max-per-min").fill("8")
        self.page.locator("#visual-fx-punch").fill("121")
        self.page.locator("#visual-fx-audio-energy").check()
        revision=self.state()["project_revision"]
        self.page.locator("#visual-fx-suggest").click()
        self.wait_condition(lambda:"proposti" in self.page.locator(
            "#visual-fx-suggest-status").inner_text())
        self.assertEqual(self.state()["project_revision"],revision)
        self.assertEqual(self.state()["video_fx"],[])
        self.page.locator("#visual-fx-max-per-min").fill("88")
        self.page.locator("#visual-fx-suggest").click()
        self.assertEqual(self.state()["project_revision"],revision)
        self.assertFalse(self.errors,self.errors)

    def test_dip_transition_visual_ui_preview_and_undo(self):
        self.upload_analyze()
        self.page.locator('[data-workspace-nav="cuts"]').click()
        url=f"http://127.0.0.1:{self.server.server_port}/api/plan"
        response=self.page.request.post(url,data=json.dumps({
            "segments":[{"start_ms":0,"end_ms":1450},
                        {"start_ms":2400,"end_ms":3850}]
        }),headers={"Content-Type":"application/json","X-Pausio-Client":"studio",
                   "Origin":f"http://127.0.0.1:{self.server.server_port}"})
        self.assertEqual(response.status,200,response.text())
        self.page.evaluate("refresh()")
        self.wait_condition(lambda:self.page.locator("#transition-boundary option").count()==1)
        before=self.state()["project_revision"]
        self.page.locator("#transition-duration").select_option("400")
        self.page.locator("#transition-add").click()
        changed=self.wait_state("revision",before+1)
        self.assertEqual(len(changed["video_transitions"]),1)
        self.assertEqual(changed["video_transitions"][0]["duration_ms"],400)
        self.wait_condition(lambda:self.page.locator(".transition-mark").count()==1)
        self.page.locator("#preview-action").click()
        preview=self.wait_state("preview","completed",timeout=120000)
        self.assertTrue(preview["preview_ready"])
        self.wait_condition(lambda: "/api/preview" in (
            self.page.locator("#preview-video").get_attribute("src") or ""),timeout=15000)
        self.shot("transition-dip-preview")
        self.page.keyboard.press("Control+z")
        undone=self.wait_state("revision",changed["project_revision"]+1)
        self.assertEqual(undone["video_transitions"],[])
        self.wait_condition(lambda: "/api/media" in (
            self.page.locator("#preview-video").get_attribute("src") or ""),timeout=15000)
        self.assertFalse(self.http_errors,self.http_errors)
        self.assertFalse(self.errors,self.errors)

    def test_custom_audio_fx_import_in_real_browser(self):
        self.upload_analyze()
        self.page.locator('[data-workspace-nav="audio"]').click()
        wav_path = self.root / "personal-riser.wav"
        effect = self.root / "personal-riser.mp3"
        with wave.open(str(wav_path), "wb") as wav:
            wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(22050)
            data = b"".join(struct.pack("<h", int(10000 * (i/13230)
                             * math.sin(2*math.pi*700*i/22050)))
                            for i in range(13230))
            wav.writeframes(data)
        # User-facing regression: imported MP3 risers must play in the browser,
        # not only WAVs produced for synthetic media tests.
        subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y",
            "-i",str(wav_path),"-c:a","libmp3lame","-b:a","160k",str(effect)],
            check=True,timeout=35)
        self.page.evaluate("document.getElementById('preview-video').currentTime=2.5")
        start = self.state()["project_revision"]
        self.page.locator("#fx-input").set_input_files(str(effect))
        self.wait_state("revision", start + 1)
        current = self.state()
        self.assertEqual(len(current["audio_clips"]), 1)
        self.assertTrue(current["audio_clips"][0]["available"])
        self.assertGreaterEqual(current["audio_clips"][0]["start_ms"], 1000)
        self.assertTrue(self.page.locator("#fx-panel").is_visible())
        self.assertTrue(self.page.locator("#workspace-audio-library").is_visible())
        self.assertEqual(self.page.locator(".workspace-audio-item").count(),1)
        self.assertEqual(self.page.locator(".fx-item").count(), 1)
        self.shot("audio-fx-workspace-1440")
        self.assertEqual(self.page.locator(".fx-item audio").count(), 1)
        selected_revision=self.state()["project_revision"]
        self.page.locator(".fx-select").first.click()
        self.assertTrue(self.page.locator("#selection-inspector").is_visible())
        self.assertEqual(self.page.locator(".workspace-audio-item.is-selected").count(),1)
        self.assertEqual(self.page.locator("#app").get_attribute("data-workspace"),"audio")
        input_rect=self.page.locator(".fx-item.is-selected input[aria-label^='Inizio']").bounding_box()
        approve_rect=self.page.locator("#approve-action").bounding_box()
        self.assertLess(input_rect["y"]+input_rect["height"],approve_rect["y"]+2,
                        "Selected FX timing must remain visible above approval")
        self.shot("audio-fx-selected-1440")
        self.assertEqual(self.page.locator(".fx-clip-mark.is-selected").count(),
                         self.page.locator(".fx-clip-mark").count())
        self.assertEqual(self.state()["project_revision"],selected_revision)
        self.page.locator("#selection-goto").click()
        self.assertTrue(self.page.locator(".fx-item.is-selected input").first.evaluate(
            "(node)=>document.activeElement===node"))
        # Regression: FX used to be displayed as a waveform but silent during
        # ordinary video playback. The live monitor must follow the video clock.
        self.assertTrue(self.page.locator("#fx-monitor-toggle").is_visible())
        self.assertEqual(self.page.locator("#fx-monitor-toggle").get_attribute("aria-pressed"),"true")
        clip = current["audio_clips"][0]
        self.page.evaluate("""(at) => {
          document.getElementById('preview-video').currentTime=sourceFromOutput(at);
        }""",(clip["start_ms"]+250)/1000*1000)
        self.wait_condition(lambda: self.page.evaluate("() => !document.getElementById('preview-video').seeking"))
        self.page.locator("#play-pause").click()
        self.wait_condition(lambda: self.page.evaluate("""(id) => {
          const player=liveFxPlayers.get(id);
          return !document.getElementById('preview-video').paused &&
                 !!player && !player.audio.paused;
        }""",clip["id"]),timeout=15000)
        self.page.locator("#play-pause").click()
        self.wait_condition(lambda: self.page.evaluate("""(id) => {
          const player=liveFxPlayers.get(id);
          return document.getElementById('preview-video').paused &&
                 !!player && player.audio.paused;
        }""",clip["id"]))
        self.page.locator("#fx-monitor-toggle").click()
        self.assertEqual(self.page.locator("#fx-monitor-toggle").get_attribute("aria-pressed"),"false")
        self.page.locator("#play-pause").click()
        self.page.wait_for_timeout(160)
        self.assertTrue(self.page.evaluate("""(id) => {
          const player=liveFxPlayers.get(id);
          return !!player && player.audio.paused;
        }""",clip["id"]))
        self.page.locator("#play-pause").click()
        self.page.locator("#fx-monitor-toggle").click()

        # The mixer controls must audibly affect voice and FX, and persist as
        # versioned commands rather than a browser-only setting.
        self.assertTrue(self.page.locator("#audio-mixer").is_visible())
        self.assertEqual(self.page.locator("#voice-gain-label").inner_text(),"100% · 0 dB")
        revision=self.state()["project_revision"]
        self.page.locator("#voice-gain").evaluate("""el=>{
          el.value='-9';el.dispatchEvent(new Event('input',{bubbles:true}));
          el.dispatchEvent(new Event('change',{bubbles:true}));
        }""")
        voiced=self.wait_state("revision",revision+1)
        self.assertEqual(voiced["audio_mix"]["voice_gain_db"],-9)
        self.assertIn("-9 dB",self.page.locator("#voice-gain-label").inner_text())
        self.page.locator("#voice-mute").click()
        muted_voice=self.wait_state("revision",voiced["project_revision"]+1)
        self.assertTrue(muted_voice["audio_mix"]["voice_muted"])
        self.assertEqual(self.page.locator("#voice-mute").get_attribute("aria-pressed"),"true")
        self.page.locator("#voice-reset").click()
        reset_voice=self.wait_state("revision",muted_voice["project_revision"]+1)
        self.assertEqual(reset_voice["audio_mix"]["voice_gain_db"],0)
        self.assertFalse(reset_voice["audio_mix"]["voice_muted"])

        self.page.locator("#fx-gain").evaluate("""el=>{
          el.value='-6';el.dispatchEvent(new Event('input',{bubbles:true}));
          el.dispatchEvent(new Event('change',{bubbles:true}));
        }""")
        fx_set=self.wait_state("revision",reset_voice["project_revision"]+1)
        self.assertEqual(fx_set["audio_mix"]["fx_gain_db"],-6)
        self.page.locator("#fx-mute").click()
        fx_muted=self.wait_state("revision",fx_set["project_revision"]+1)
        self.assertTrue(fx_muted["audio_mix"]["fx_muted"])
        self.page.locator("#fx-reset").click()
        fx_ready=self.wait_state("revision",fx_muted["project_revision"]+1)
        self.assertFalse(fx_ready["audio_mix"]["fx_muted"])
        self.assertEqual(fx_ready["audio_mix"]["fx_gain_db"],0)
        self.assertEqual(self.page.locator("#fx-gain").input_value(),"0")

        self.page.locator(".clip-volume-range").evaluate("""el=>{
          el.value='-15';el.dispatchEvent(new Event('input',{bubbles:true}));
          el.dispatchEvent(new Event('change',{bubbles:true}));
        }""")
        clip_set=self.wait_state("revision",fx_ready["project_revision"]+1)
        self.assertEqual(clip_set["audio_clips"][0]["gain_db"],-15)
        self.page.locator(".clip-mute").click()
        clip_muted=self.wait_state("revision",clip_set["project_revision"]+1)
        self.assertTrue(clip_muted["audio_clips"][0]["muted"])
        self.page.locator(".clip-reset").click()
        clip_ready=self.wait_state("revision",clip_muted["project_revision"]+1)
        self.assertFalse(clip_ready["audio_clips"][0]["muted"])
        self.assertEqual(clip_ready["audio_clips"][0]["gain_db"],-12)
        current=clip_ready

        # FX is inside the SAME scroll/zoom surface as the source waveform.
        geometry = self.page.evaluate("""() => {
          const bounds=id=>{ const b=document.querySelector(id).getBoundingClientRect();
            return {left:b.left,right:b.right,top:b.top,bottom:b.bottom,width:b.width}; };
          return {source:bounds('#timeline-track'),fx:bounds('#timeline-fx-track'),
            playhead:bounds('#playhead')};
        }""")
        self.assertAlmostEqual(geometry["source"]["left"], geometry["fx"]["left"], delta=2)
        self.assertAlmostEqual(geometry["source"]["right"], geometry["fx"]["right"], delta=2)
        self.assertGreater(geometry["fx"]["top"], geometry["source"]["bottom"])
        self.assertGreaterEqual(geometry["playhead"]["bottom"], geometry["fx"]["bottom"]-4)
        # An FX crossing an excluded source range is split on the *source* ruler.
        self.assertGreaterEqual(self.page.locator("#fx-lane .fx-clip-mark").count(), 1)
        self.assertEqual(self.page.locator("#fx-panel #fx-lane").count(), 0)
        # The waveform must come from decoded audio rather than decorative CSS.
        self.wait_condition(lambda: self.page.evaluate("""() => {
          const c=document.querySelector('.fx-clip-waveform');if(!c||!c.width)return false;
          const data=c.getContext('2d').getImageData(0,0,c.width,c.height).data;
          for(let i=3;i<data.length;i+=4)if(data[i]>0)return true;
          return false;
        }"""),timeout=20000)
        # One source-time region per KEEP span when an FX crosses the cuts.
        projection = self.page.evaluate("""() => {
          const fx={start_ms:0,duration_ms:editedDuration()};
          return fxSourcePieces(fx).map(p=>[p.sourceStart,p.sourceEnd]);
        }""")
        self.assertEqual(projection, [
          [s["start_ms"], s["end_ms"]] for s in current["editor_segments"]
        ])
        fx_mark=self.page.locator("#fx-lane .fx-clip-mark").first
        fx_mark.focus();fx_mark.press("ArrowRight")
        moved=self.wait_state("revision",current["project_revision"]+1)
        self.assertEqual(moved["audio_clips"][0]["start_ms"],
                         current["audio_clips"][0]["start_ms"]+100)
        # One scale, one horizontal scroll offset at 4x zoom.
        self.page.locator("#timeline-zoom").select_option("4")
        scale=self.page.evaluate("""() => {
          const s=document.querySelector('#timeline-track').getBoundingClientRect(),
                f=document.querySelector('#timeline-fx-track').getBoundingClientRect();
          return [s.left,f.left,s.width,f.width];
        }""")
        self.assertAlmostEqual(scale[0],scale[1],delta=2)
        self.assertAlmostEqual(scale[2],scale[3],delta=2)
        self.page.evaluate("document.querySelector('#timeline-surface').scrollLeft=140")
        self.wait_condition(lambda: self.page.evaluate("""() =>
          Math.abs(document.querySelector('#timeline-ruler').scrollLeft-
                   document.querySelector('#timeline-surface').scrollLeft)<2"""))
        self.page.locator("#timeline-zoom").select_option("1")
        self.page.evaluate("document.querySelector('#timeline-surface').scrollLeft=0")
        # Make the pointer test independent of source cut boundaries: moving an
        # effect from the end of a KEEP segment can have a legitimately flat
        # source-to-output time mapping through the excluded gap.
        self.page.locator('.fx-item input[aria-label^="Inizio"]').fill("0.100")
        self.page.locator('.fx-item input[aria-label^="Inizio"]').dispatch_event("change")
        positioned=self.wait_state("revision",moved["project_revision"]+1,timeout=12000)
        self.assertEqual(positioned["audio_clips"][0]["start_ms"],100)
        self.wait_condition(lambda: self.state()["waveform_status"]!="running")
        fx_mark=self.page.locator("#fx-lane .fx-clip-mark").first
        fx_mark.scroll_into_view_if_needed()
        self.assertFalse(fx_mark.is_disabled())
        box=fx_mark.bounding_box()
        self.assertIsNotNone(box)
        x,y=box["x"]+box["width"]/2,box["y"]+box["height"]/2
        self.page.mouse.move(x,y);self.page.mouse.down()
        self.page.mouse.move(x+65,y,steps=6);self.page.mouse.up()
        dragged=self.wait_state("revision",positioned["project_revision"]+1,timeout=12000)
        self.assertGreater(dragged["audio_clips"][0]["start_ms"],positioned["audio_clips"][0]["start_ms"])
        revision = dragged["project_revision"]
        self.page.locator('.fx-item input[aria-label^="Volume"]').fill("-18")
        self.page.locator('.fx-item input[aria-label^="Volume"]').dispatch_event("change")
        self.wait_state("revision", revision + 1)
        self.assertEqual(self.state()["audio_clips"][0]["gain_db"], -18)
        self.page.locator("#preview-action").click()
        self.wait_state("preview", "completed")
        self.wait_condition(lambda: self.page.evaluate("() => mode==='rendered'"))
        self.assertTrue(self.page.evaluate("""(id) => {
          const player=liveFxPlayers.get(id);
          return !player||player.audio.paused;
        }""",clip["id"]), "FX monitor must not duplicate rendered FFmpeg sound")
        self.assertTrue(self.page.locator("#fx-monitor-toggle").is_disabled())
        for width in (390, 320):
            self.page.set_viewport_size({"width":width,"height":844})
            self.page.wait_for_timeout(120)
            self.shot(f"fx-import-{width}")
            self.assertLessEqual(metrics(self.page)["scrollWidth"],width+3)
        self.page.locator(".fx-remove").click()
        self.wait_condition(lambda: len(self.state()["audio_clips"])==0)
        self.page.locator("#undo-action").click()
        self.wait_condition(lambda: len(self.state()["audio_clips"])==1)
        self.assertFalse(self.errors,self.errors)



    def test_timeline_selection_updates_existing_inspector_without_edit(self):
        self.upload_analyze()
        revision=self.state()["project_revision"]
        self.assertGreaterEqual(self.page.locator(".region-select").count(),2)
        self.page.locator(".segment-select").first.click()
        self.assertTrue(self.page.locator("#selection-inspector").is_visible())
        self.assertEqual(self.page.locator("#app").get_attribute("data-workspace"),"cuts")
        self.assertEqual(self.page.locator(".segment-card.is-selected").count(),1)
        self.assertEqual(self.page.locator(".timeline-region.is-selected").count(),1)
        input_rect=self.page.locator(".segment-card.is-selected .start-input").bounding_box()
        approve_rect=self.page.locator("#approve-action").bounding_box()
        self.assertLess(input_rect["y"]+input_rect["height"],approve_rect["y"]+2,
                        "Selected cut properties should be visible above approval")
        self.shot("selected-cut-workspace-1440")
        self.assertEqual(self.state()["project_revision"],revision)
        self.page.locator("#selection-goto").click()
        self.assertTrue(self.page.locator(".segment-card.is-selected .start-input").evaluate(
            "(node)=>document.activeElement===node"))
        self.page.locator(".region-select").last.focus()
        self.page.locator(".region-select").last.press("Enter")
        self.assertEqual(self.page.locator(".region-select[aria-pressed='true']").count(),1)
        self.assertTrue(self.page.locator("#selection-title").inner_text().startswith(
            "Intervallo "))
        self.assertEqual(self.state()["project_revision"],revision)
        self.page.locator("#selection-clear").click()
        self.assertFalse(self.page.locator("#selection-inspector").is_visible())
        self.assertEqual(self.page.locator(".timeline-region.is-selected").count(),0)
        self.assertEqual(self.state()["project_revision"],revision)
        self.assertFalse(self.errors,self.errors)


    def test_adaptive_source_ruler_and_zoom_anchor(self):
        self.upload_analyze()
        self.assertGreater(self.page.locator(".timeline-time-tick").count(),4)
        self.page.evaluate("document.getElementById('preview-video').currentTime=1.75")
        self.wait_condition(lambda: not self.page.evaluate(
            "document.getElementById('preview-video').seeking"))
        self.page.locator("#timeline-zoom").select_option("2")
        self.page.locator("#timeline-center-playhead").click()
        def cursor_x():
            return self.page.evaluate("""() => {
              const track=document.getElementById('timeline-track');
              const surface=document.getElementById('timeline-surface');
              const bounds=track.getBoundingClientRect(),viewport=surface.getBoundingClientRect();
              const current=timelineSourceMs();
              return bounds.left+current/project.media.duration_ms*bounds.width-viewport.left;
            }""")
        before=cursor_x()
        before_count=self.page.locator(".timeline-time-tick").count()
        self.page.locator("#timeline-zoom-in").click()
        after=cursor_x()
        self.assertEqual(self.page.locator("#timeline-zoom").input_value(),"4")
        self.assertAlmostEqual(before,after,delta=5,
                               msg="Zoom should preserve the source position under the playhead")
        self.assertGreater(self.page.locator(".timeline-time-tick").count(),before_count)
        self.assertIn("Sorgente 00:01",self.page.locator("#timeline-source-clock").inner_text())
        self.page.locator("#timeline-zoom-out").click()
        self.assertEqual(self.page.locator("#timeline-zoom").input_value(),"2")
        self.assertFalse(self.page.locator("#timeline-center-playhead").is_disabled())
        self.shot("source-ruler-anchored-zoom-1440")
        self.assertFalse(self.errors,self.errors)

    def test_desktop_navigation_and_resizable_timeline(self):
        self.assertTrue(self.page.locator(".studio-navigation").is_visible())
        self.assertTrue(self.page.locator("#analyze-action").is_visible())
        self.page.locator('[data-workspace-nav="cuts"]').click()
        self.assertEqual(self.page.locator("#app").get_attribute("data-workspace"), "cuts")
        self.assertTrue(self.page.locator(".cut-settings").is_visible())
        self.assertTrue(self.page.locator("#cuts-panel").is_visible())
        self.page.locator('[data-workspace-nav="transcript"]').click()
        self.assertTrue(self.page.locator(".asr-settings").is_visible())
        self.assertTrue(self.page.locator("#transcript-panel").is_visible())
        self.page.locator('[data-workspace-nav="captions"]').click()
        self.assertTrue(self.page.locator("#transcript-panel").is_visible())
        self.assertTrue(self.page.locator("#transcript-empty").is_visible())
        self.page.locator('[data-workspace-nav="media"]').click()
        self.assertTrue(self.page.locator("#import-action").is_visible())
        self.upload_analyze()
        revision=self.state()["project_revision"]
        self.page.evaluate("document.getElementById(\'preview-video\').currentTime=1")
        self.page.locator('[data-workspace-nav="audio"]').click()
        self.assertEqual(self.state()["project_revision"],revision)
        self.assertGreaterEqual(self.page.evaluate("document.getElementById(\'preview-video\').currentTime"),.99)
        self.assertTrue(self.page.locator("#fx-panel").is_visible())
        self.assertTrue(self.page.locator("#audio-mixer").is_visible())
        self.assertEqual(self.page.locator("#app").get_attribute("data-workspace"), "audio")
        handle=self.page.locator("#dock-resizer")
        first=int(handle.get_attribute("aria-valuenow"))
        handle.focus()
        handle.press("ArrowUp")
        second=int(handle.get_attribute("aria-valuenow"))
        self.assertGreater(second,first)
        self.assertEqual(self.page.evaluate("localStorage.getItem('pausio-studio-dock-height')"),
                         str(second))
        self.assertEqual(self.page.locator("#desktop-approve-action").is_disabled(),
                         self.page.locator("#approve-action").is_disabled())
        self.page.reload(wait_until="networkidle")
        self.assertEqual(self.page.locator("#app").get_attribute("data-workspace"), "audio")
        self.assertEqual(int(self.page.locator("#dock-resizer").get_attribute("aria-valuenow")),
                         second)
        for width,height in [(1920,1080),(1440,900),(1280,720),(390,844)]:
            self.page.set_viewport_size({"width":width,"height":height})
            self.page.wait_for_timeout(180)
            info=metrics(self.page)
            self.assertLessEqual(info["scrollWidth"],width+3,
                                 f"Workspace overflow at {width}px: {info}")
            if width>=1001:
                self.assertLessEqual(info["timeline"]["bottom"],height+2)
                self.assertLessEqual(info["approve"]["bottom"],height+2)
            else:
                self.assertFalse(self.page.locator(".studio-navigation").is_visible())
                self.assertLessEqual(info["timeline"]["bottom"],info["inspector"]["y"]+2)
                self.assertEqual(self.page.evaluate("document.getElementById(\'fx-panel\').parentElement.id"),"app")
        self.assertFalse(self.errors,self.errors)

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
        self.assertEqual(data["schema_version"],7)
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
        self.page.locator('[data-workspace-nav="cuts"]').click()
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

    def test_standalone_asr_ui_transcribes_without_closedroom_server(self):
        from unittest.mock import patch
        self.upload_analyze()
        self.page.locator('[data-workspace-nav="transcript"]').click()
        self.assertFalse(self.page.locator("#asr-download").is_checked())
        self.assertEqual(self.page.locator("#asr-language").input_value(),"it")
        self.page.locator("#asr-model").select_option(
            "mlx-community/whisper-large-v3-turbo"
        )
        result={
            "schema_version":1, "provider":"pausio-local", "backend":"mlx-whisper",
            "model":"mlx-community/whisper-large-v3-turbo",
            "language":"it", "text":"Ciao AI", "segments":[
                {"start_ms":100,"end_ms":800,"text":"Ciao AI"}],
            "word_timestamps_available":False, "warnings":["word_alignment_unavailable"]
        }
        with patch("pausio.studio.transcribe_video_local",return_value=result) as run:
            self.page.locator("#transcribe-action").click()
            state=self.wait_state("transcribe","completed")
            self.assertEqual(state["transcript"]["provider"],"pausio-local")
            self.assertFalse(run.call_args.kwargs["allow_model_download"])
            self.assertEqual(run.call_args.kwargs["language"],"it")
        self.wait_condition(lambda:"Pausio ASR" in self.page.locator(
            ".transcript-source").inner_text())
        self.assertTrue(self.page.locator("#transcript-review").is_visible())
        self.assertEqual(self.page.locator(".transcript-item").count(),1)
        revision=state["project_revision"]
        self.page.locator("#transcript-search").fill("ciao")
        self.assertEqual(self.page.locator(".transcript-item").count(),1)
        self.page.locator('[data-mode="edited"]').click()
        self.page.locator("#transcript-next").click()
        self.assertEqual(self.page.locator('[data-mode="original"]').get_attribute("aria-pressed"),"true")
        self.assertAlmostEqual(self.page.evaluate("document.getElementById('preview-video').currentTime"),
                               .1,delta=.12)
        self.assertEqual(self.page.locator(".transcript-item.is-selected").count(),1)
        self.assertTrue(self.page.locator(".transcript-item.is-selected .transcript-seek").evaluate(
            "(node)=>document.activeElement===node"))
        self.assertEqual(self.page.evaluate("transcriptSelectedIndex"),0)
        self.assertEqual(self.state()["project_revision"],revision)
        self.page.locator("#transcript-search").fill("inesistente")
        self.assertEqual(self.page.locator(".transcript-item").count(),0)
        self.assertIn("Nessuna frase",self.page.locator("#transcript-list").inner_text())
        self.page.locator("#transcript-search").fill("")
        self.assertEqual(self.page.locator(".transcript-item").count(),1)
        self.shot("transcript-compact-1440")
        self.assertFalse(self.errors,self.errors)

    def test_generate_edit_and_preview_social_captions_in_browser(self):
        from unittest.mock import patch
        initial=self.upload_analyze()
        self.page.locator('[data-workspace-nav="transcript"]').click()
        transcript={
            "provider":"pausio-local","backend":"mlx-whisper",
            "model":"mlx-community/whisper-large-v3-turbo",
            "language":"it","text":"Tre consigli per creare video.",
            "word_timestamps_available":True,
            "segments":[{
                "start_ms":100,"end_ms":980,"text":"Tre consigli per creare video.",
                "words":[
                    {"start_ms":100,"end_ms":250,"text":"Tre"},
                    {"start_ms":250,"end_ms":400,"text":"consigli"},
                    {"start_ms":400,"end_ms":550,"text":"per"},
                    {"start_ms":550,"end_ms":700,"text":"creare"},
                    {"start_ms":700,"end_ms":980,"text":"video."},
                ],
            }],
        }
        with patch("pausio.studio.transcribe_video_local",return_value=transcript):
            self.page.locator("#transcribe-action").click()
            self.wait_state("transcribe","completed")
        self.wait_condition(lambda:self.page.locator("#caption-generate").is_visible())
        self.page.locator("#caption-generate").click()
        self.wait_condition(lambda:len(self.state()["captions"])>0)
        self.wait_condition(lambda:self.page.locator(".caption-edit-card").count()>0)
        updated=self.state()
        self.assertEqual(updated["last_command"],"caption.set")
        self.assertFalse(updated["approved"])
        self.assertEqual(self.page.locator(".caption-cue-mark").count(),len(updated["captions"]))
        self.assertTrue(self.page.locator("#timeline-caption-track").is_visible())
        cue=updated["captions"][0]
        cue_ratio=self.page.locator(".caption-cue-mark").first.evaluate(
            "(node)=>parseFloat(node.style.left)")
        self.assertAlmostEqual(cue_ratio,100*cue["start_ms"]/updated["media"]["duration_ms"],delta=.02)
        selection_revision=updated["project_revision"]
        self.page.locator(".caption-cue-mark").first.click()
        self.assertEqual(self.page.locator("#app").get_attribute("data-workspace"),"captions")
        self.assertTrue(self.page.locator(".social-safe-guide").is_visible())
        self.assertFalse(self.page.locator("#audio-mixer").is_visible())
        self.assertTrue(self.page.locator("#workspace-caption-library").is_visible())
        self.assertEqual(self.page.locator(".workspace-caption-item").count(),len(updated["captions"]))
        self.assertEqual(self.page.locator(".workspace-caption-item.is-selected").count(),1)
        text_rect=self.page.locator(".caption-edit-card.is-selected textarea").bounding_box()
        approve_rect=self.page.locator("#approve-action").bounding_box()
        self.assertLess(text_rect["y"]+text_rect["height"],approve_rect["y"]+2,
                        "Selected caption text should be accessible above approval")
        self.shot("caption-workspace-1440")
        self.page.locator("#workspace-caption-search").fill("Nessuna frase corrispondente")
        self.assertEqual(self.page.locator(".workspace-caption-item").count(),0)
        self.page.locator("#workspace-caption-search").fill("")
        self.assertEqual(self.page.locator(".workspace-caption-item").count(),len(updated["captions"]))
        self.assertEqual(self.page.locator(".caption-edit-card.is-selected").count(),1)
        self.assertEqual(self.page.locator(".caption-cue-mark[aria-pressed='true']").count(),1)
        self.assertEqual(self.state()["project_revision"],selection_revision)
        self.page.locator("#selection-goto").click()
        self.assertTrue(self.page.locator(".caption-edit-card.is-selected textarea").evaluate(
            "(node)=>document.activeElement===node"))
        self.page.locator("#selection-clear").click()
        self.assertEqual(self.state()["project_revision"],selection_revision)
        # Change a single cue timing in the UI, recorded as a portable event.
        self.page.locator(".caption-time-start").first.fill("0.200")
        self.page.locator(".caption-time-start").first.press("Tab")
        moved=self.wait_state("revision",selection_revision+1)
        self.assertEqual(moved["last_command"],"caption.retime")
        self.assertEqual(moved["captions"][0]["start_ms"],200)
        self.page.locator("#desktop-undo-action").click()
        undone=self.wait_state("revision",moved["project_revision"]+1)
        self.assertEqual(undone["captions"][0]["start_ms"],cue["start_ms"])
        self.page.locator("#desktop-redo-action").click()
        redone=self.wait_state("revision",undone["project_revision"]+1)
        self.assertEqual(redone["captions"][0]["start_ms"],200)
        mark=self.page.locator(".caption-cue-mark").first
        mark.focus();mark.press("ArrowRight")
        keyed=self.wait_state("revision",redone["project_revision"]+1)
        self.assertEqual(keyed["last_command"],"caption.retime")
        self.assertEqual(keyed["captions"][0]["start_ms"],300)
        # The same command is emitted once for a drag on the source ruler.
        mark=self.page.locator(".caption-cue-mark").first
        mark.scroll_into_view_if_needed()
        rect=mark.bounding_box()
        self.assertIsNotNone(rect)
        px,py=rect["x"]+rect["width"]/2,rect["y"]+rect["height"]/2
        self.page.mouse.move(px,py);self.page.mouse.down()
        self.page.mouse.move(px+30,py,steps=6);self.page.mouse.up()
        dragged=self.wait_state("revision",keyed["project_revision"]+1)
        self.assertEqual(dragged["last_command"],"caption.retime")
        self.assertGreater(dragged["captions"][0]["start_ms"],keyed["captions"][0]["start_ms"])
        self.assertEqual(dragged["project_revision"],keyed["project_revision"]+1)
        self.assertEqual(self.page.locator(".caption-edge-handle.start").count(),
                         len(dragged["captions"]))
        self.assertEqual(self.page.locator(".caption-edge-handle.end").count(),
                         len(dragged["captions"]))
        right=self.page.locator(".caption-edge-handle.end").first
        right.scroll_into_view_if_needed()
        rect=right.bounding_box()
        self.assertIsNotNone(rect)
        px,py=rect["x"]+rect["width"]/2,rect["y"]+rect["height"]/2
        self.page.mouse.move(px,py);self.page.mouse.down()
        self.page.mouse.move(px-13,py,steps=6);self.page.mouse.up()
        trimmed=self.wait_state("revision",dragged["project_revision"]+1)
        self.assertEqual(trimmed["last_command"],"caption.retime")
        self.assertEqual(trimmed["project_revision"],dragged["project_revision"]+1)
        self.assertEqual(trimmed["captions"][0]["start_ms"],dragged["captions"][0]["start_ms"])
        self.assertLess(trimmed["captions"][0]["end_ms"],dragged["captions"][0]["end_ms"])
        self.assertGreaterEqual(trimmed["captions"][0]["end_ms"]-trimmed["captions"][0]["start_ms"],80)
        self.assertTrue(self.page.locator("#timeline-snap").is_checked())
        snapped=self.page.evaluate("""() => {
          const cue=project.captions[0],target=segments()[0].end_ms;
          return snapCueTime(target+20,cue,project.media.duration_ms,700,{});
        }""")
        self.assertTrue(snapped["snapped"])
        self.page.locator("#timeline-snap").uncheck()
        unsnapped=self.page.evaluate("""() => {
          const cue=project.captions[0],target=segments()[0].end_ms;
          return snapCueTime(target+20,cue,project.media.duration_ms,700,{});
        }""")
        self.assertFalse(unsnapped["snapped"])
        self.assertEqual(self.page.evaluate("localStorage.getItem('pausio-caption-snap')"),"off")
        self.page.locator("#timeline-snap").check()
        self.shot("caption-trim-handles-1440")
        updated=trimmed
        # Seek inside the retimed cue, not at its former timestamp.
        self.page.evaluate("""(sec) => {
          document.querySelector('#preview-video').currentTime=sec;
        }""",(dragged["captions"][0]["start_ms"]+100)/1000)
        self.wait_condition(lambda:self.page.locator("#caption-overlay").is_visible())
        self.assertIn("Tre",self.page.locator("#caption-overlay").inner_text())
        edit=self.page.locator(".caption-edit-card").first
        edit.locator("textarea").fill("Tre consigli AI!")
        edit.locator("button.text-button").click()
        state=self.wait_state("revision",updated["project_revision"]+1)
        self.assertEqual(state["captions"][0]["text"],"Tre consigli AI!")
        self.page.locator("#caption-style").select_option("minimal")
        changed=self.wait_state("revision",state["project_revision"]+1)
        self.assertEqual(changed["caption_style"],"minimal")
        self.assertEqual(changed["caption_config"]["font_size"],48)
        # Preset Riquadro, then an actual on-stage drag and keyboard adjustment.
        self.page.locator("#caption-style").select_option("boxed")
        box_state=self.wait_state("revision",changed["project_revision"]+1)
        self.assertEqual(box_state["caption_style"],"boxed")
        self.assertTrue(box_state["caption_config"]["background"])
        self.page.locator("#caption-appearance summary").click()
        self.page.locator("#caption-drag-toggle").click()
        self.wait_condition(lambda:self.page.locator("#caption-overlay").get_attribute(
            "role")=="slider")
        frame=self.page.locator(".aspect-canvas").bounding_box()
        label=self.page.locator("#caption-overlay").bounding_box()
        self.assertIsNotNone(frame)
        self.assertIsNotNone(label)
        self.page.mouse.move(label["x"]+label["width"]/2,label["y"]+label["height"]/2)
        self.page.mouse.down()
        self.page.mouse.move(
            frame["x"]+frame["width"]*.64,
            frame["y"]+frame["height"]*.60,steps=5
        )
        self.page.mouse.up()
        dragged=self.wait_state("revision",box_state["project_revision"]+1)
        self.assertEqual(dragged["caption_style"],"custom")
        self.assertAlmostEqual(dragged["caption_config"]["x_pct"],64,delta=3)
        self.assertAlmostEqual(dragged["caption_config"]["y_pct"],60,delta=3)
        self.page.locator("#caption-overlay").focus()
        self.page.locator("#caption-overlay").press("ArrowUp")
        keyed=self.wait_state("revision",dragged["project_revision"]+1)
        self.assertEqual(keyed["caption_config"]["y_pct"],
                         dragged["caption_config"]["y_pct"]-1)
        self.page.locator('[data-caption-setting="text_color"]').fill("#FFCC00")
        recolored=self.wait_state("revision",keyed["project_revision"]+1)
        self.assertEqual(recolored["caption_config"]["text_color"],"#FFCC00")
        self.page.locator("#caption-font-family").select_option("Georgia")
        selected=self.wait_state("revision",recolored["project_revision"]+1)
        self.assertEqual(selected["caption_config"]["font_family"],"Georgia")
        self.assertEqual(selected["caption_style"],"custom")
        self.wait_condition(lambda:"Georgia" in self.page.locator(
            "#caption-overlay").evaluate("(node) => node.style.fontFamily"))
        for width,height in [(1440,900),(390,844),(320,700)]:
            self.page.set_viewport_size({"width":width,"height":height})
            self.page.wait_for_timeout(140)
            self.assertLessEqual(metrics(self.page)["scrollWidth"],width+3)
            self.shot("caption-social-"+str(width))
        self.page.set_viewport_size({"width":1440,"height":900})
        self.page.locator("#preview-action").click()
        draft=self.wait_state("preview","completed",timeout=120000)
        self.assertTrue(draft["preview_ready"])
        self.wait_condition(lambda:self.page.locator('[data-mode="rendered"]').get_attribute(
            "aria-pressed")=="true")
        self.assertTrue(self.page.locator("#caption-overlay").is_hidden())
        self.page.locator('[data-workspace-nav="media"]').click()
        self.assertTrue(self.page.locator("#project-export").is_visible())
        with self.page.expect_download() as download:
            self.page.locator("#project-export").click()
        saved=self.root/"caption-project.pausio.json"
        download.value.save_as(saved)
        commands=json.loads(saved.read_text())["commands"]
        self.assertIn("caption.set",[c["type"] for c in commands])
        self.assertIn("caption.correct",[c["type"] for c in commands])
        self.assertIn("caption.configure",[c["type"] for c in commands])
        self.assertEqual(commands[-1]["payload"]["config"]["text_color"],"#FFCC00")
        self.assertEqual(commands[-1]["payload"]["config"]["font_family"],"Georgia")
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
