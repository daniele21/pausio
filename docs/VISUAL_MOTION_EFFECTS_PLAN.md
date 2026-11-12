# Pausio — Visual motion, punch-ins and transitions

Status: **PROPOSED — not implemented** (12 November 2026). This document expands WP2 of [AGENTIC_EDITING_PLAN.md](AGENTIC_EDITING_PLAN.md) with deterministic, source-aware motion editing and conservative automatic suggestions.

## Product goal

Let a creator make engaging talking-head shorts without moving to another editor for basic visual rhythm. Support manual editing first, then a non-destructive **Suggest visual effects** action, and later ChatGPT/Claude Chat choosing/revising those suggestions through the exact same Pausio commands. The chat model stays responsible for creative judgment; Pausio local analysis proposes effects only from objective cues.

### Observed reference clip

User-provided 11.23 s screen recording (552x672, H.264, **no audio track**) of a social talking-head video on 2026-11-12. Visual observations: alternating wider and tighter crop, prominent close-up around 5.5 s and 9 s, word-level animated captions and occasional hard edits. Because the screen recording has no audio, **cannot** validate beat/accent-based timing from this reference. Do not commit the original clip or frame extracts to Git.

## Automatic editing: versioned profiles and open-source implementation references

The companion [open-source research and automation design](VISUAL_FX_AUTOMATION_RESEARCH.md) checks actual implementation details from auto-editor, add-zooms, talking-head-jumpcut-zoom, ai-video-reframing, autobroll, PySceneDetect and clipcast. Use this before designing the automatic suggestion engine, rather than assuming any repository can be copied directly.

The four first-class UI choices are **Naturale** (default; max 3 FX/min, min gap 8s, peak 1.16x, hard cuts), **Educativo** (max 6/min, min gap 4.5s, peak 1.22x, contextual dissolve), **Dinamico** (opt-in; max 10/min, min gap 2.8s, peak 1.28x, rare contextual dissolve/dip) and **Personalizzato** (editable copy of Educativo with hard safety bounds). All are maximum budgets, never obligations to fill the timeline.

The future **Suggerisci effetti** action produces a proposal, not an edit; `preview_auto` may render a temporary before/after without authorizing export, and `off` disables suggestion generation. Every accepted effect becomes a specific typed event with exact keyframes and source ID. The config contract is [configs/visual_fx_presets_v1.json](../configs/visual_fx_presets_v1.json), bounded by [JSON Schema v1](../schemas/pausio-visual-fx-presets-v1.schema.json) and [stdlib CI validator](../scripts/validate_visual_fx_presets.py). **These presets are design data; no automatic generator or runtime controls are implemented yet.**

The detection pipeline reuses Pausio's KEEP plan, actual ASR timestamps and optional audio energy, later face/scene observations. It must renormalize weight only over actually available signals (never invent prosody when audio is absent); apply deterministic sorting, cap frequency, enforce spacing/cut guards and protect manual edits/rejections when regenerating suggestions.

## Effects vocabulary: do not conflate

| Name | Render behavior | When useful | First phase |
| --- | --- | --- | --- |
| Hard cut | Adjacent KEEP spans, no optical blending | Most conversational jump cuts; default | Already basic |
| Punch-in / punch-out | Abrupt crop/scale change exactly on an existing cut or editorial beat; short optional eased ramp | Emphasis; example clip | **MVP** |
| Animated zoom / pan | Per-frame transform from deterministic scale/center keyframes with easing and hold | Gentle push-in to a key idea, follow moving subject | **MVP** |
| Smart reframe | Track optional face/subject anchor and smooth transforms; bounded zoom; center fallback | Keeps face inside 9:16 safe region | Phase B |
| Cut transition | Controlled cross-dissolve, dip-to-black, wipe or slide across adjacent segments, with explicit duration and trim handles | B-roll/context change, intro/outro; usually NOT each talking-head jump cut | MVP: dissolve/dip only |
| Kinetic caption | Text styling/scale/highlight keyed to verified ASR word timing | Highlight important phrases | Existing captions architecture → Phase B |
| Speed ramp / motion blur / shake/glitch | Nonlinear time remapping or additional filter processing | Occasional stylistic edit, not default | Later, opt-in |

For social speech, default to **hard cuts and selective punch-ins**, not transition effects after every pause. Presets must have an explicit intensity switch: `none`, `subtle`, `balanced`, `dynamic`; default `subtle`. No hallucinated claims about algorithmic detection of viewer attention.

## Data model / replay contract (WP1 prerequisite)

**Every effect must be an explicit versioned typed command**, playable from UI, portable JSON, future MCP and deterministic FFmpeg renderer; do not directly inject browser CSS/JS state or arbitrary FFmpeg filter strings.

Proposed event families (names for design, not yet available):
- `video.transform.add`, `video.transform.update`, `video.transform.remove`: target segment ID, source-start/end integer ms, ordered keyframes, zoom scale, normalized center X/Y, easing, preset version, priority, stable effect ID.
- `video.transition.set`, `video.transition.remove`: neighboring KEEP segment IDs, named allowlisted kind (`hard_cut`, `dissolve`, `dip_black`), duration ms, easing, stable transition ID, source-handle policy.
- `video.effects.proposal.add` / optional explicit acceptance record: propose deterministic candidate list with evidence and generator version/seed. Approval replays concrete commands, not a regenerated algorithm.

Source-time anchors bind to a KEEP interval or segment ID. A transition is **boundary-anchored** to the two adjacent segment IDs, because a crossfade overlaps output time while using frames outside the two KEEP spans where safe handles exist. If changing a cut invalidates an effect, reject or mark it for review; never silently attach it to unrelated content. Keyframes are evaluated in output frame timestamps *after* mapping from their source intervals. Never run transform interpolation across an omitted gap. Sync audio across overlapped transitions with validated crossfade policy, or leave hard-cut audio when a crossfade is inappropriate. Preserve source SHA-256 and revision checks.

Illustrative proposal (NOT an implemented schema):

~~~json
{
  "type": "video.transform.add",
  "payload": {
    "effect_id": "stable-id",
    "segment_id": "segment-id",
    "start_source_ms": 12000,
    "end_source_ms": 14500,
    "mode": "punch_in",
    "keyframes": [
      {"offset_ms": 0, "scale": 1.0, "cx_norm": 0.5, "cy_norm": 0.43},
      {"offset_ms": 220, "scale": 1.18, "cx_norm": 0.5, "cy_norm": 0.43}
    ],
    "easing": "ease_out_cubic",
    "preset": "social-subtle-v1"
  }
}
~~~

Transform values must have explicit schema limits and admission rules. Initial design range: `1.0 <= scale <= 1.3` for *automated* effects, normalized centers within the valid crop window, 2–16 keyframes per clip effect, 150–600 ms ramp and no unsupported keyframe interpolation. Manual controls can later allow wider bounded ranges after quality tests.

## Automatic effect suggestions: local signal engine

This is similar to pause detection **in that it generates timestamped proposals**, but unlike silence thresholds there is no objective artistic ground truth. Treat scores and confidence as review hints, not automatic approval.

1. **Inputs**: already-approved or proposed KEEP segments, verified word timestamps/segment text, pause/cut candidates, speech energy and prosody (if audio exists), frame sample metadata, optional local face bounding boxes and source resolution.
2. **Candidate points**: after a major jump cut, at a meaningful phrase boundary, after an emphatic word (ASR + speech energy), or at a user-identified moment. Motion and audio are evidence; do not infer semantic importance from loudness alone.
3. **Optional safe face tracking**: sparse frames processed on-device via a separately approved face detector/tracker (e.g. MediaPipe), smoothed with dead zone, maximum speed and acceleration. No face or multiple faces? fall back to center or skip. Prevent crop crossing chin/forehead, hands or captions. No external vision API.
4. **Deterministic selection**: rank candidates, apply min spacing (e.g. 3–5 s between punch-ins, configurable), cap count per minute (e.g. 4–8 for subtle), do not stack conflicting transforms. Avoid starts/ends very near cuts, transitions or overlays, and prevent 1.3x upscaling on weak-resolution input if output looks visibly soft.
5. **Proposal stage**: preview each suggested effect and show why (`cut_boundary`, `speech_emphasis`, `face_position`, `manual_prompt`), confidence and exact source ms. Generate no irreversible changes; creator can accept all, accept one, alter, or reject.
6. **Chat agent layer**: ChatGPT/Claude Chat sees real storyboard/transcript and can ask for `suggest_visual_effects`, then select/revise precise commands via MCP once supported. This does **not** use provider model API keys inside Pausio.
7. **Pilot**: talking-head with 3 cuts, 2 selective punch-ins and 1 intentional B-roll dissolve. Compare no-effects vs suggested effects for readability, distracting motion, timing, and time saved.

Suggested initial heuristic profile (to validate, NOT a universal best practice): hold shot 3–6 seconds; scale 1.10–1.22; ramp 180–300 ms with ease-out, hold for phrase; zoom-out at a topic boundary; hard cut default; optional dissolve only across a contextual change with valid handles. A fast 1.0→1.3 jump may feel aggressive; avoid default screen shakes/glitches.

## Rendering architecture: preview and final must match

Pausio currently renders a concatenated selection of source segments and subtitles/audio with FFmpeg. Add a single intermediate **per-KEEP visual transform stage**, then optional **boundary transition stage**, then captions/overlays, audio mix and export. All video streams must have compatible geometry, pixel format, frame rate and timebase for `xfade`. VFR phone footage must be normalized to CFR output while preserving real source timestamps; filtergraph should not leak source resolution discrepancies across segments.

- **Zoom/pan**: use a validated FFmpeg zoompan/crop/scale expression generated entirely by Pausio from typed bounded keyframes. For sharp punch-in, crop/scale from an exact frame boundary. Easing must produce the same trajectory in draft and final at their respective sizes.
- **Transitions**: `xfade` for cross-dissolve (plus optional `acrossfade` or controlled audio edit), or a fixed black dip. Demand sufficient source handles, otherwise reject with a clear reason and fall back only after user approval.
- **Captions/overlays**: apply after camera motion, in final output coordinates, so subtitles stay stable and do not zoom/move with the speaker. Respect face and platform safe areas; animated kinetic text uses its own typed event channel.
- **Performance**: offer lower-resolution draft, bounded preview duration/FFmpeg timeout and cache by media SHA + full typed project revision + render profile. Do not run GPU-heavy tracking on each UI scrub. No arbitrary agent-written filtergraphs.
- **Geometry**: deterministic pixel rounding, pixel aspect ratio, rotation metadata, HDR/color considerations, upscaling quality and VFR input. Prefer modest zoom to avoid visible resolution loss.

### UI

- A `Video FX` lane below cuts and captions, with typed effect chips and transition badges at segment boundaries.
- Clicking a chip opens inspector: effect, start/end source time, strength, anchor X/Y, ramp ms, easing, delete and copy.
- Keyframe indicators or simple start/hold/end handles; direct preview drag/zoom generates validated commands, not CSS-only state.
- `Suggerisci effetti` button offers preset **Leggero / Bilanciato / Dinamico**, proposal review with side-by-side before/after, approve/reject per effect. No random application by default.
- Agent and manual edits share identical command history, Undo/Redo, project export/import and restart autosave.

## Engineering sequence and security gates

**FX0 — Spec and synthetic fixtures (P0)**: codec/rotation/VFR test videos, acceptance screenshots, event JSON schema, timing/anchor policy, overlap conflicts; no new external dependencies by default.

**FX1 — Manual punch-in & animated zoom (P0)**: reducer events, keyframes, FFmpeg draft/final, UI lane + inspector, export/reimport/undo/redo and real-browser QA. This creates the essential effect seen in the reference.

**FX2 — Automatic suggestion engine (P1)**: simple local cut/ASR cadence heuristics and optional speech energy; every suggestion evidence-backed; approval required. Test no excessive effect spam.

**FX3 — Face reframe + transition primitives (P1)**: optional private CPU tracker and real `xfade`/audio boundary policy; avoid arbitrary codec/generative dependencies.

**FX4 — Agent MCP control and kinetic captions (P1/P2)**: observe candidates, request preview, apply/revise using strict typed commands; only after MCP permissions and authenticated remote gateway security gates. Advanced wipes/shakes/speed ramps later.

Acceptance checks:
- [ ] Every visual edit is typed, validated, reversible, portable and restored after restart.
- [ ] Pixel positioning agrees between 540x960 draft and 1080x1920 final, within agreed geometry tolerances; captions remain stationary when camera zooms.
- [ ] Automated candidates can be rejected independently; never add unreviewed effects at every cut.
- [ ] Source/trim boundaries safe for fast punch and xfade; no duplicated syllables, black frames, poor A/V sync, or face clipping.
- [ ] Video quality tested on at least 3 real phone clips incl. landscape input, portrait input, VFR, head motion and a multi-person case.
- [ ] Security: no shell/filter-expression injection, no arbitrary remote URLs; bounds on asset resolution, number of keyframes/effects and render time; local-first face detections, no uploads.
- [ ] Human review for creative quality and accessibility (avoid aggressive flashes/strobes or fast zoom by default).

## Prior art (review for design, don't copy implementation blindly)

- FFmpeg filter docs: https://ffmpeg.org/ffmpeg-filters.html (zoompan, crop/scale, xfade, acrossfade)
- auto-editor actions/animations: https://github.com/WyattBlue/auto-editor/tree/master/skills (zoom keyframes, ramps/easing, transition concepts)
- PySceneDetect: https://www.scenedetect.com/docs/latest/ (scene/cut detection, not creative choice)
- MediaPipe Face Detector: https://ai.google.dev/edge/api/mediapipe/python/mp/tasks/vision/FaceDetector (video-timestamped face boxes)
- Respect licenses; inspiration only. This plan does not install or include external code.
