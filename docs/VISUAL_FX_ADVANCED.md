# Advanced Video FX — Pausio local Studio

Status: **merged into `main` in PR #52 (2026-11-13)**; **not included in the historical v0.1.0 release wheel**. Do not describe Face Crop as live tracking or Dip as xfade. The PR head passed Python 3.11–3.13 CI and Playwright; real-phone QA remains pending.

## Creator workflow

1. In **Tagli → Video FX**, select a KEEP segment and choose an effect:
   - **Punch-in:** instant constant crop.
   - **Zoom progressivo:** linear zoom from initial to final.
   - **Zoom morbido (ease):** bounded cubic smoothstep acceleration/deceleration, no overshoot.
   - **Ratchet · 3 scatti:** three fixed zoom steps; total interval must last at least 1.2 seconds. No flashing, shake or arbitrary scripts.
2. For configurable technical proposals, choose **Personalizzato** and set maximum FX per minute (1–10), minimum time between effects (2.5–12s), punch scale (105–125%), slow push scale (105–120%) and duration (1.2–4s). Optional waveform-rise evidence is computed strictly from the imported original's local PCM envelope (900 bins) when available. It does **not** infer semantic importance or emotions.
3. Every automatic proposal displays source time and evidence and is **not applied until accepted**. Once accepted, effects use a typed `video.transform.add/update/remove` event. No automatic final export.
4. **Transizioni tra tagli** lets you choose a valid adjacent KEEP pair and add a **Dip to black** (200–600ms); half of the visual fade is applied on each existing side. Output duration and **voice audio remain unchanged**, with no duplicated syllables. This is not a dissolve/crossfade with overlapping pictures or audio; use it sparingly. The boundary must have at least 1.2 seconds of KEEP content on each side.
5. **Centra il volto** (optional): select a current Video FX and click **Analizza volto sul Mac**. With separately installed OpenCV, Pausio samples five local 360×640 frames and checks for a single, stable face and safe crop containment. If ambiguous/moving/missing, no center is proposed. An explicitly approved candidate becomes a normal `video.transform.update` source-bound anchor. **This is fixed reframing, not temporal face tracking**. Pausio never identifies people or saves face images or measurements.
6. Click **Genera preview con effetti**, view the actual 540×960 FFmpeg composition, and confirm the cut plan before exporting 1080×1920. Move/undo edits and preview again as necessary. The built-in player cannot show moving zooms without rendering first.

### Optional local face dependency

The existing Pausio install runs without OpenCV. If you choose face-aware reframing, separately install into the same virtualenv:

```bash
python -m pip install opencv-python-headless
```

OpenCV's bundled Haar cascade is used; Pausio does not download model weights, upload media, or require an LLM API. Precision varies by lighting, pose and video quality. Check all suggestions manually, especially with glasses, profile faces, or multiple people. No guarantee of successful face detection.

## Portable project contract

- `pausio.project` JSON Schema **v4** supports legacy v1/v2/v3 imports, canonical history + revision + source SHA-256 binding, source-ID anchored effects, and typed `video.transition.add/update/remove`.
- Motion and transitions are bounded types compiled into numerical FFmpeg filters. No arbitrary shell expressions or externally supplied filtergraph segments. Undo/Redo, autosave, portable export/import remain the same.
- Static face detection and custom proposal settings are *read-only research settings*, not an untracked output modification. Only accepted `video.transform.update` or `video.transition.*` commands impact the final video.

## QA and known gaps

- Pure replay, invalid inputs, duration/count limits, old format import, actual FFmpeg synthetic MP4 and optional face proposal tests are in GitHub CI. Browser Playwright tests include custom settings, dip transition addition/preview/undo, face approval, editing + project export.
- Still required: **human playback of a private real A56/iPhone VFR/rotation fixture**, vertical and horizontal crop comparisons, sound continuity at every transition, caption safe zones and real face-detection acceptance. Do not commit private source videos to GitHub.
- Not yet implemented: arbitrary editable multi-keyframe curves, live preview of unrendered transforms, continuous face tracking with temporal smoothing, genuine image xfade with validated A/V handles, offline scene detection and semantic/prosodic classification, cinematic motion templates or kinetic captions. These are separate engineering stages; **do not present the current Dip as xfade**.
