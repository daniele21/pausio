# Studio frontend — boundaries and lightweight modules

Pausio uses plain deferred JavaScript served by the loopback-only Studio server.
There is **no npm installation, bundler or framework dependency**.

## What goes where

- `app.js`: shared project state, editing command transport, video player and global workspace coordination. Existing legacy sections should be moved incrementally, not expanded casually.
- `audio_monitor_ui.js`: live voice/FX monitoring, per-bus gain/mute controls, mixer preview. It is loaded **before** app.js so the existing controller can call `setupAudioMixer()`. It never implements a second FFmpeg renderer or a different command history.
- `visual_fx_ui.js`, `visual_transition_ui.js`, `graphic_overlay_ui.js`, `image_overlay_ui.js`, `editorial_ui.js`: individual inspectors, all calling the same validated `/api/command` endpoint.
- `capture.js`: mobile/desktop recording and teleprompter; separate capture page.

## Rules for the next changes

1. Prefer small cohesive files. New effects belong in a focused Python processing module plus their UI inspector, not in new branches of `studio.py`/`app.js` unless wiring is unavoidable.
2. No new runtime package for behavior already supported by Python stdlib, FFmpeg and the browser.
3. Do not introduce duplicate timeline/edit state. Use the project revision and serialized command tape.
4. Move legacy code by *behavioral extraction*: no logic changes in the same PR, verify HTTP static-asset availability and full Playwright editor flows.
5. Next candidates: timeline UI/scrubbing and Studio job orchestration. Do not split purely to chase line counts; explicitly check dependencies and lifecycle first.
