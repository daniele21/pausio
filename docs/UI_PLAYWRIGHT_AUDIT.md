# Pausio Studio — Playwright UX/UI audit

**Test setup:** actual headless Chromium on GitHub Actions Ubuntu with FFmpeg and the Pausio Python localhost server. A generated 360×640, 4-second H.264/AAC portrait clip contains audible signal, a 1.1-second silence, then signal. The tests use no user media, cloud ASR or paid models.

**Implementation:** `tests/browser/test_studio_playwright.py` with workflow `.github/workflows/playwright-ui.yml`. Screenshots and JSON layout metrics are stored under the `pausio-playwright-ui-audit` Actions artifact. Run locally with:

```bash
python -m pip install -e .
python -m pip install "playwright>=1.55,<2"
python -m playwright install chromium
python -m unittest discover -s tests/browser -v
```

## What was exercised

- Empty-state, labels and disabled actions at **1440×900, 1024×768, 768×900, 390×844, 320×700**.
- Video imported into the real server and actual FFmpeg silence analysis returning two retained intervals.
- Waveform extracted from real decoded audio and displayed by the browser (not decorative placeholder).
- Timeline **4× zoom**, keyboard trim of 100ms, Undo/Redo, exact `segment.update` history and portable `.pausio.json` v2 download.
- Pointer drag of a trim handle; one editing action must produce exactly one revision/command.
- FFmpeg low-resolution draft preview, explicit approval and final MP4 render/download.
- Loaded editor viewport metrics and screenshots at 1440×900, 1024×768, 390×844 and 320×700.
- Browser page errors, console errors, horizontal document overflow, visible approval and mobile timeline-inspector visual ordering.

## Findings and fixes

| Severity | Playwright observation | Correction |
| --- | --- | --- |
| P1 | At 320px the page scrolled horizontally **342px** | Three preview modes get a separate full-width mobile toolbar row; playback controls follow below |
| P1 | On 1440×900 the timeline began at approximately **y=1117px**, below the viewport | Constrain desktop workbench to available viewport height and allow independently scrolling side panels; timeline now **y=690–900px** |
| P1 | **Conferma montaggio** was hidden inside the inspector's scrollable segment list; mobile overflow made it hard to discover | Promote approval to a persistent inspector footer on desktop; remove the clipped nested scroll on mobile |
| P2 | At 390px the timeline followed the full inspector and required excessive scrolling | Move timeline immediately after the player at the mobile breakpoint, with matching DOM and keyboard navigation order |
| P2 | If waveform extraction completed later than import and no other job ran, UI status could remain stale | Poll state while waveform is running and repaint when results arrive |

Results after correction: **0 horizontal overflow** on the tested empty-state widths; desktop 1440×900 now contains the player, review approval and timeline in one viewport; the full real-browser editing flow passes without page-level JavaScript errors.

## UX issues still open

- The **390px mobile view remains a long scrolling document** (roughly 2.2k px when showing an analyzed project). It is usable, but this is not an ideal touch-first editor. A later design iteration should consider a compact project rail and more direct navigation between preview, timeline and inspector.
- The desktop inspector scrolls internally as intended for longer projects. For many segments, confirm that the number inputs and segment cards remain comfortable to review.
- Browser timeline simulation is intentionally approximate. The FFmpeg-rendered preview uses the same cut timing/concat filter as the final export, but **human listening is still required** to judge naturalness.
- These tests do **not** validate macOS Safari, Samsung A56 HEVC/variable-frame-rate videos, audio drift on long recordings, screen reader announcements, touch-drag on actual phones, keyboard focus traps or visual regression pixel diffs.
- The generated test clip is intentionally simple; its pass status does not prove production quality of speech or edits.

## Developer QA rule

Any future UI change affecting panel placement, timeline gestures, new preview modes, import/export or actionable controls must rerun this Playwright suite and inspect the uploaded screenshots. Keep every output-affecting gesture connected to the canonical Pausio command schema and verify revision/history changes.
