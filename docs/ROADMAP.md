# Pausio development roadmap

## Phase 0 — Foundation (this commit)

- [x] Python 3.11+ installable package and CLI.
- [x] ffprobe metadata; FFmpeg signal-based silence analysis.
- [x] Conservative AI_NATURAL editing policy.
- [x] Validated, human-editable JSON keep timeline.
- [x] FFmpeg 1080x1920 H.264/AAC export (aspect-ratio preserving padded canvas).
- [x] Unit tests and synthetic real-media smoke test; matrix CI.
- [ ] Real Samsung A56 sample tests for VFR, rotation, cut boundaries and audio sync.

## Phase 1 — Speech-aware editing

- [x] Standalone Pausio MLX Whisper transcription without running ClosedRoom; local-only model resolution and optional explicit weight download.
- [ ] Test real MLX inference with Italian Samsung A56 footage, VFR audio offsets, model latency and resource usage on Apple Silicon.
- [ ] Evaluate VAD/ASR quality controls inspired by ClosedRoom, retaining strict no-silent-speech-removal policy.
- [ ] Integrate Pausio transcript with reviewable edit proposals without automatically removing speech.
- [ ] Detect suspected repeats and fillers as **review prompts**, never silent deletion.
- [x] Editable burned-in subtitles using actual Pausio ASR word timestamps or segment fallback; source-to-output remapping, social/minimal/boxed presets, custom position/font/color/outline/background, drag/key editing, FFmpeg preview/export, and typed portable commands.
- [ ] Verify platform-specific safe areas and font fallback on real A56 footage and social uploads.
- [ ] Test natural pacing vs aggressive auto cuts using three real clips.

## Studio UI testing milestone

- [x] Local web UI via `pausio studio` with video import, preview and graphical KEEP timeline.
- [x] Studio editing presets (Natural/Balanced/Dynamic/Custom), advanced FFmpeg thresholds, reanalysis, diagnostics and portable versioned settings; real-media suitability still needs validation.
- [x] Editable source-time ranges, restore decisions, original vs edited simulated preview, explicit approval and MP4 export.
- [x] Optional Pausio local transcription panel with model/language controls and explicit download approval.
- [x] Four tailored Studio UX/UI Agent Skills and automated HTTP/workflow tests.
- [x] Playwright Chromium browser audit on Linux with synthetic FFmpeg media: 320/390/768/1024/1440 viewport screenshots, complete editing/export, keyboard + pointer trim, responsive regression checks and JSON project round-trip.
- [x] Playwright-found responsive fixes: 320px horizontal overflow, desktop timeline below fold, hidden approval control, waveform status refresh and mobile timeline order.
- [ ] Validate Safari/macOS browser behavior, screen readers and real Samsung A56 video/UX with human testers.
- [ ] Run real Samsung A56 videos through the full preview and export; inspect VFR, rotation, codec and A/V sync.
- [x] Asynchronous waveform from actual FFmpeg-decoded audio (not a visual placeholder); source-time alignment, bounded to ≤15-minute clips.
- [x] Precise range trim interactions on the timeline (pointer + accessible keyboard) issuing existing typed `segment.update` commands, not UI-only state.
- [x] Rendered 540×960 draft preview using **the same FFmpeg trim/concat pipeline** as full-resolution export, without requiring approval; invalidated by changes.
- [x] Timeline zoom 1×/2×/4×/8× and source-time ruler with scroll sync.
- [ ] Browser/visual testing on macOS and Samsung A56 recordings; validate color, rotation, VFR, preview latency and audio sync.
- [ ] Audio continuity across jump cuts, fades and future word-level semantic editing.

## Portable instruction-driven editing

- [x] Every implemented Studio edit produces a typed command with stable IDs; replay is authoritative.
- [x] `.pausio.json` v1 export/import, JSON Schema, original-video SHA-256 binding and optimistic revision checks.
- [x] Deterministic replay to FFmpeg `EditPlan`, including concrete AI proposals and explicit approval.
- [x] Pure-domain and HTTP regression tests: replay, reimport, media mismatch and stale edits.
- [x] Undo/Redo via typed history commands and v2 cursor/revision, with v1 project import migration.
- [x] Private autosave of active video + project, atomic checkpoint, previous checkpoint fallback, media SHA-256 validation, single-process lock and explicit delete.
- [ ] Validate visual/keyboard Undo/Redo UX and restart recovery on a real Mac with a Samsung A56 video.
- [x] Persist complete ASR transcripts privately per active session, with atomic recovery, schema v1 migration, media binding, and explicit deletion.
- [ ] Extend autosave to multiple user-managed workspaces and optional separate transcript export.
- [ ] New commands for subtitles, audio effects, crop, export presets and AI prompt editing.
- [ ] Optional export adapters (OpenTimelineIO / CapCut) without changing the canonical format.

## Phase 2 — Quality and UX

- [ ] Optional DeepFilterNet/RNNoise audio-cleanup adapter; voice naturalness A/B tests.
- [ ] Audio continuity across jump cuts; measured loudness and fade policy.
- [ ] Simple review UI: timeline, cut toggles, transcript corrections, before/after player.
- [ ] Auto b-roll hints and screenshot slots, manual confirmation required.
- [ ] Robust workspaces, cancellation, deterministic job state, crash/retry behavior.

## Phase 3 — Exporters and cross-platform workflow

- [ ] CapCut project adapter after compatibility/version/licensing verification.
- [ ] Per-platform title/caption and export profiles without duplicating render core.
- [ ] Asset library and optional chime template with stored licensing metadata.
- [ ] Packaged macOS application once CLI quality and maintenance burden justify it.

## Quality gates

- **Correctness**: no missing syllables; no drift > 100 ms in tested preview clips; no unexpected overwrite.
- **Usefulness**: reviewer approves >= 80% of suggested cuts and can undo 100% of them.
- **Audio**: no clicks or abrupt noise floor changes at edits; listening review obligatory.
- **Time saved**: net manual effort (recording excluded) improves vs baseline CapCut by >= 30% on 3 clips.
- **Portability**: an input and plan generated on macOS can be processed on Linux after source relocation.

These are proposed acceptance criteria, not measured product performance.

## Phase 4 — Agent-ready Studio (planned; subscription-based chat, no Pausio LLM)

See [detailed agentic editing execution plan](AGENTIC_EDITING_PLAN.md) for dependencies, work packages, UX/API contracts, acceptance criteria and risk gates.

- [ ] WP0: reconcile pending desktop capture / mobile portrait PR stack (#26–#28) with merged #22; independently prove MCP tool write from ChatGPT and Claude Chat in actually supported accounts/clients.
- [ ] WP1: command schema v3, validated atomic instruction batches, revision checks, asset manifest and import/export migration.
- [ ] WP2: text/statistic/code/image/video overlays on source-time timeline and the same deterministic FFmpeg preview/final path.
- [ ] WP3: real integrated LUFS/LRA/true-peak measurement, configurable two-pass normalization and final AAC verification.
- [ ] WP4: private music/riser/media library with asset hashes, licensing metadata, audition, gain/ducking/fades and agent-readable search.
- [ ] WP5: optional transcription dispatch to a private self-hosted GitHub Actions runner using Pausio's existing ASR engine, never agent shell commands.
- [ ] WP6: storyboard/frame/timecode/diagnostics observations for ChatGPT/Claude Chat to perform the creative video analysis.
- [ ] WP7: scoped MCP tools and authenticated connector boundary; UI and agent share one command/render engine.
- [ ] WP8: end-to-end talking-head pilot: GPT/Claude Chat analyzes video, edits Pausio, reviews preview, corrects, requests approval and delivers editable project + MP4.

**Non-goal:** do not call GPT/Claude inference APIs from Pausio or recreate the creative analysis inside Pausio. Chat clients' file/tool support is an explicit MVP feasibility gate, not an assumed feature.
