"""Real Chromium smoke test for three review-only Style Packs in Pausio Studio."""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import threading
import unittest
import uuid

from playwright.sync_api import sync_playwright

from pausio.media import probe
from pausio.project_commands import ProjectTape
from pausio.studio import StudioWorkspace, create_server


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg required for real browser test")
class StylePackBrowserTests(unittest.TestCase):
    def test_three_storyboards_select_apply_one_caption_preset_only(self):
        ws = StudioWorkspace()
        server = None
        thread = None
        try:
            source = ws.directory / "synthetic-style.mp4"
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-nostdin", "-y",
                "-f", "lavfi", "-i", "color=c=0x202937:s=180x320:r=30:d=9",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=9",
                "-shortest", "-c:v", "mpeg4", "-c:a", "aac", str(source),
            ], check=True, timeout=40)
            info = probe(source)
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            media = {
                "filename": source.name, "sha256": digest,
                "duration_ms": info.duration_ms, "has_audio": info.has_audio,
            }
            tape = ProjectTape(media).append("timeline.keep_all", {})
            tape = tape.append("caption.set", {
                "style": "social",
                "cues": [{
                    "id": "c" * 32,
                    "text": "Controlla il file settings.local.json",
                    "start_ms": 1000, "end_ms": 3400,
                }],
            })
            ws.source = source
            ws.filename = source.name
            ws.media_id = uuid.uuid4().hex
            ws.media_sha256 = digest
            ws.info = info
            ws._install_tape(tape)
            original = ws.tape.as_dict()
            server = create_server(port=0, workspace=ws)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    headless=True, args=["--no-sandbox"],
                )
                try:
                    page = browser.new_page(viewport={"width": 1340, "height": 900})
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(base, wait_until="networkidle")
                    page.locator('[data-workspace-nav="visual"]').click()
                    button = page.locator("#style-pack-generate")
                    self.assertTrue(button.is_enabled())
                    self.assertEqual(page.locator("#style-pack-choices button").count(), 3)
                    button.click()
                    page.wait_for_function(
                        "() => document.getElementById('style-pack-status')"
                        ".textContent.includes('Tre regie calcolate')"
                    )
                    self.assertEqual(original, ws.tape.as_dict())
                    # Selection changes the proposal, not the underlying tape.
                    first = page.locator("#style-pack-choices button").nth(0)
                    first.click()
                    self.assertEqual(first.get_attribute("aria-pressed"), "true")
                    self.assertEqual(original, ws.tape.as_dict())
                    # A chosen caption style is a single, reversible command.
                    page.locator("#style-pack-caption").click()
                    page.wait_for_function(
                        "() => document.getElementById('style-pack-status')"
                        ".textContent.includes('Preset sottotitoli applicato')"
                    )
                    self.assertEqual(ws.tape.view.caption_style, "minimal")
                    self.assertEqual(ws.tape.revision, tape.revision + 1)
                    self.assertFalse(ws.tape.view.approved)
                    self.assertFalse(errors, errors)
                finally:
                    browser.close()
        finally:
            if server is not None:
                server.shutdown()
                server.server_close()
            if thread is not None:
                thread.join(timeout=3)
            ws.close()


if __name__ == "__main__":
    unittest.main()
