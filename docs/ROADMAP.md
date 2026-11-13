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

See [detailed agentic editing execution plan](AGENTIC_EDITING_PLAN.md) for dependencies, work packages, UX/API contracts, acceptance criteria and risk gates. **Current executable component blueprint:** [Social Composition Engine](SOCIAL_COMPOSITION_COMPONENTS.md) (OBS/TIME/LAY/VID/UI/AUD/TMP/TXN/MCP/QA slices; proposed, not yet shipping).

- [ ] WP0: reconcile pending desktop capture / mobile portrait PR stack (#26–#28) with merged #22; independently prove MCP tool write from ChatGPT and Claude Chat in actually supported accounts/clients.
- [ ] WP1: command schema v3, validated atomic instruction batches, revision checks, asset manifest and import/export migration.
- [ ] WP2: text/statistic/code/image/video overlays on source-time timeline and the same deterministic FFmpeg preview/final path.
- [x] WP2 scene-template slice: output-timed full-screen `stat_reveal`, `permission_dialog` (clearly simulated) and `code_highlight`, v8 events, Studio editor, MCP catalog, real libass preview/export; verify actual creator footage before calling visuals production-ready. [Usage](SCENE_TEMPLATES_V1.md).
- [ ] WP2b Visual Motion FX: manual punch-in/out and keyframed zoom/pan (P0), conservative auto suggestions from cuts/ASR evidence (P1), optional offline face reframe and bounded dissolve/dip transitions (P1), kinetic caption animation (P2); all as replayable typed events. See [visual motion effects plan](VISUAL_MOTION_EFFECTS_PLAN.md).
- [x] WP2b/AF0 design only: comparative implementation research, four bounded preset contracts (Naturale/Educativo/Dinamico/Personalizzato), strict JSON Schema, stdlib validator + adversarial tests in CI. See [automation research](VISUAL_FX_AUTOMATION_RESEARCH.md). This does **not** implement zooms or effects.
- [x] WP2b feature selection: [adoption matrix](VISUAL_FX_FEATURE_ADOPTION_MATRIX.md) covers per-project integrate/adapt/defer/reject decisions; S0 (source-time transform events) → S1 (manual punch/zoom/preview) → S2 (cut-driven suggestions) → S3 (quality/scene) → S4 (tracking/transitions) → S5 (agent/B-roll). **Documentation only.**
- [x] WP2b/AF1 baseline: source-bound v3 punch/slow-push commands, actual FFmpeg preview/final, dedicated Video FX timeline/inspector, profile-aware conservative cut/real-ASR proposals with explicit per-item approval, MCP stdio read-only propose + allowlisted FX edits. Python/Playwright E2E verified on integration PR. [Usage & limits](VISUAL_FX_MVP.md).
- [x] WP2b/AF2 safe slice: `ease_push` (cubic smoothstep), three-step `ratchet` >=1.2s, editable bounded `Personalizzato` cadence/amplitude parameters, optional measured local waveform-rise cues, `dip_black` visual-only manual transitions with strict adjacent KEEP contract, opt-in offline stable-face crop proposal requiring review. All are typed/replayable v4 output edits when accepted. [Full guidance](VISUAL_FX_ADVANCED.md).
- [ ] WP2b/AF3–AF4: *genuine* image crossfade `xfade` with validated A/V handles and speech alignment; adjustable arbitrary multi-keyframe curves; temporal multi-frame face tracking; optional scene detection and prosodic features; realtime camera-motion preview; real phone media QA (VFR/rotation/HDR); kinetic subtitles; remote ChatGPT/Claude Chat gateway behind security review.
- [ ] WP3: real integrated LUFS/LRA/true-peak measurement, configurable two-pass normalization and final AAC verification.
- [ ] WP4: private music/riser/media library with asset hashes, licensing metadata, audition, gain/ducking/fades and agent-readable search.
- [ ] WP5: optional transcription dispatch to a private self-hosted GitHub Actions runner using Pausio's existing ASR engine, never agent shell commands.
- [ ] WP6: storyboard/frame/timecode/diagnostics observations for ChatGPT/Claude Chat to perform the creative video analysis.
- [ ] WP7: scoped MCP tools and authenticated connector boundary; UI and agent share one command/render engine.
- [ ] WP8: end-to-end talking-head pilot: GPT/Claude Chat analyzes video, edits Pausio, reviews preview, corrects, requests approval and delivers editable project + MP4.

**Non-goal:** do not call GPT/Claude inference APIs from Pausio or recreate the creative analysis inside Pausio. Chat clients' file/tool support is an explicit MVP feasibility gate, not an assumed feature.

## Security gate for agentic integration (Nov 2026)

- [x] Add Pausio threat-specific skills: `pausio-network-abuse-defense`, `pausio-mcp-trust-boundary`, `pausio-input-media-defense`, `pausio-actions-runner-security`; route via `AGENTS.md` and validate in CI.
- [x] Document Pages vs local Studio vs local MCP vs future Internet-facing gateway trust boundaries in `docs/SECURITY_THREAT_MODEL.md`.
- [x] Limit local HTTP clients, idle time and DNS-rebinding Host, plus negative regression tests (pending PR CI validation).
- [ ] Before public MCP: independent authenticated HTTPS gateway; OAuth/audience/scope/project authorization; per-user + global quotas, edge DDoS/WAF, safe media sharing, incident response, load/security tests. **Do not tunnel the Studio local server**.
- [ ] Before GitHub Actions ASR: private dispatch repository, isolated/restricted self-hosted Mac, no PR code execution, bounded jobs and explicit media consent.
- [ ] Real supported ChatGPT/Claude client interoperability + on-device, manual hardware review.

- [x] **OBS-01 (scoped):** FFmpeg still frames from imported source and current preview (full/range), explicit volatile Studio opt-in, 12/min and 4/call, MCP image output with revision and media binding. [Usage & security](VISUAL_OBSERVATION_V1.md). Audio observation and automatic semantic perception are not yet implemented.

- [x] **AUD-OBS-01 (bounded):** short genuine source and FFmpeg-preview audio via MCP `pausio_get_audio_context`, separate volatile user opt-in, strict revision/timebase, <=6s WAV/4 calls per minute, RMS + peak in dBFS. Transport still requires real ChatGPT tunnel audio smoke test; LUFS/ducking remain open. [Audio observation](AUDIO_OBSERVATION_V1.md).
