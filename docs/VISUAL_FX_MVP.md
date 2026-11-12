# Video FX v1 — first working Pausio Studio slice

Status: **developed and integration-tested in the daniele/* feature pipeline**. Not included in the historical `v0.1.0` wheel. Verify the integration PR and main CI before claiming a shipped GitHub release. This documentation describes the intended UX implemented in PR #46, not advanced effects planned in prior research.

## Creator flow

1. Start `pausio studio`, import the video, and generate/review the KEEP cut plan.
2. In **Tagli**, scroll to **Video FX**. To add a manual effect, position the playhead on a kept source segment, choose `Punch-in` or `Zoom progressivo`, choose maximum zoom and click **Aggiungi effetto**.
3. To get automatic suggestions, choose **Naturale**, **Educativo**, **Dinamico**, or **Personalizzato** and click **Suggerisci effetti**. The heuristic uses only removed-pause/cut boundaries and *real source ASR phrase timestamps* when available. It reports missing prosody/face/scene evidence rather than inventing confidence.
4. Proposals show their source timestamp and reason. Click **Accetta** or **Ignora** individually. Suggestions alone never change the project. Accepting runs one canonical, revision-checked `video.transform.add` command and recomputes candidates; no auto-export.
5. Applied events appear in a dedicated **Video FX** source-time track. Edit start/end time, zoom level, crop center and effect type, or remove from the card. Every operation is a typed v3 project command; keyframe semantics are resolved by the renderer.
6. Click **Genera preview con effetti** (or the existing preview action) for the actual FFmpeg 540×960 render. Review the face crop, subtitle readability and naturalness, then confirm the cut plan and export 1080×1920 as usual.
7. Project export is **v3** JSON with effect commands/history. Source media remains private and immutable. V1/V2 projects are still readable and are exported as v3.

## What v1 actually implements

- Manual punch (constant zoom for a bounded source-time interval) and linear slow push (from 1.00× to bounded chosen zoom).
- Fixed 9:16 size, 30 fps in visual FX rendering pipeline; captions composited after camera movement to avoid zooming text.
- Zoom scale 1.00–1.30×, center X/Y 0–100%, 250ms–60s per effect, maximum 18 effects, no overlaps on the same segment. Effects must remain fully within one source KEEP segment. Cutting away a source portion that contains an existing effect fails explicitly so editing never silently moves it to unrelated speech.
- Four prototype suggestion profiles with distinct density, spacing and amplitude limits. Suggested effects are only *proposals* until accepted, keyed to current project revision + source SHA. Ignore history is held in browser local storage for that media session.
- Undo/Redo and portable import/export via the shared Pausio command reducer. The UI's project toolbar may be hidden in the desktop Cut workspace; the global **Cmd/Ctrl+Z** and **Cmd/Ctrl+Shift+Z** shortcuts remain supported outside text input fields.

## Not yet included

- Multi-keyframe free-form animated motion/easing curves, ratchet moves, subject/face-tracked reframing, scene detection, B-roll/advanced overlays, actual `xfade`/audio transitions, automated music ducking, ChatGPT/Claude video analysis, or a remote/public MCP gateway.
- Automatically applying all candidates, autonomous final export or generating effects without any timing evidence. No external model API keys and no public Pausio backend.
- A high-quality local live motion preview on the original video player: use **FFmpeg preview** to see the authoritative moving zooms. Rendering may be slower than the normal unchanged-video path.
- VFR/rotation/HDR and very-low-resolution footage need further visual verification on real Android/iPhone files. Output frame-rate normalization is a deliberate MVP choice, not a complete color/rotation pipeline.

## QA and safety

- Pure Python tests: source-time validation, stale revision, v1/v2 migration, duplicate/overlap rejection, deterministic proposals and zero-change read-only suggestion endpoint.
- FFmpeg E2E: actual video frames differ during zoom; output geometry correct; audio unchanged; no user-supplied raw filter expressions.
- Studio HTTP E2E: real local import -> analyze -> propose -> add -> preview -> export portable event -> undo.
- Playwright UI: real Chromium tests for suggestion review and effects, 320/390/768/1440 layouts, plus screenshots. Smartphone Safari/Android and creator visual review still required.
- Security: no added public listeners, user assets never leave local workspace, Host/Origin and request bounds inherited from Studio. Do not expose the server through tunnels. Source sha/revision are checked on imported project/edits.
