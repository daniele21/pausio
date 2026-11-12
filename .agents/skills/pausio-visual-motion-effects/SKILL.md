---
name: pausio-visual-motion-effects
description: Use for Pausio punch-in/out, animated zoom, crop/pan keyframes, camera reframing, scene transitions, xfade, kinetic captions and automatic visual-effect suggestions. Require source-time precision, deterministic video rendering, no uncontrolled effect spam, security and visual QA.
---

# Pausio visual rhythm — deliberate motion with deterministic effects

Load this skill when implementing or modifying video FX, transition timing, reframing, keyframe interpolation, auto-suggested zoom, or kinetic captions. First read [visual motion plan](../../../docs/VISUAL_MOTION_EFFECTS_PLAN.md) and the existing project/event contract. Pair with `pausio-edit-command-schema`, `pausio-media-ffmpeg`, `pausio-video-interaction-ux`, `pausio-test-engineering` and `pausio-input-media-defense` where relevant.

## Non-negotiable engineering rules

1. Differentiate: **hard cut**, **punch-in** (instant change in crop), **animated zoom/pan** (keyframes), **transition** between adjacent source segments (`xfade`), and **kinetic captions**. Each requires its own precise validated event; never hide it in the rendering filter string or untracked browser-only state.
2. Effects operate against a known media SHA, current project revision, segment ID, source ms and explicit timebase. Transition boundaries require two adjacent KEEP segment IDs and validated media handles. Deterministic replay, export/import, undo/redo and autosave must work before shipping.
3. Render from one canonical projection: input KEEP segments -> per-segment transforms -> boundary transition -> caption/overlay composition -> audio mix -> output. Do **not** let captions zoom with the face. Draft and final must use the same motion semantics.
4. Use only fixed preapproved filter families generated from typed numeric values. No user/agent-controlled raw FFmpeg expressions, arbitrary shell, remote media URLs, unsanitized SVG or unbounded effects. Set CPU/time/memory budgets and keep source media immutable.
5. Auto suggestions are **proposals**, not facts or user approvals. Candidate evidence: cuts, pauses, ASR word timestamps (if present), speech energy and optional local face boxes. Never claim a detected emotional/creative importance unless explicitly provided by a chat agent/user.
6. Default to subtle effects on talking-head clips: selective zoom, hard cuts, sparse transitions; avoid seizure-prone flashing, distracting shakes and constant zooms. Offer creator presets and reject/adjust per suggestion.
7. Optional face tracking is local/offline, license-reviewed and bounded. No face or multiple faces -> center fallback or skip; motion smoothing and safe-area/face containment required.
8. UI exposes editable FX lane with timings, strength, position, keyframes and transition markers. Every edit must go through the validated reducer, including drag gestures.
9. Effect priority: keep natural voice and captions readable. Transition overlaps must not duplicate syllables or shift caption/source time silently. Cut changes must invalidate/reconcile affected FX deterministically.
10. ChatGPT/Claude Chat may decide creative choices via MCP after feature support, without model API keys in Pausio. MCP tool never bypasses the same project revision, security or human-approval gate.

## Required tests

- Two source-time KEEP intervals with fast punch, continuous zoom and optional dissolve; compare exact resulting geometry in draft/final and on each side of boundary.
- Changing or undoing a trim must not attach effect to unrelated source or break duration; portable reimport/replay matches view.
- VFR inputs, vertical and horizontal sources, face off-center, low-resolution source, missing face, high motion, short segments, cut with no handles.
- 320/390/1440 px Playwright UI, safe zones, keyboard undo/redo and real preview controls; verify no changes limited to CSS.
- Negative: invalid keyframe order, out-of-bounds centers/scales, conflicting overlapping effects, injected filter content, oversized effect count and missing media SHA.
- Auditory and visual human review: no loss of speech, distracting fast motion or caption obstruction.

See [effect acceptance matrix](references/effect-qa.md).
