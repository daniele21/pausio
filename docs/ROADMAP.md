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

- [x] Consume ClosedRoom's existing localhost ASR path endpoint with local-only provider; produce timestamped JSON sidecar.
- [ ] E2E compatibility verification with running ClosedRoom `dev`, A56 footage, VFR audio offset and actual model output.
- [ ] Reuse ClosedRoom's speech/VAD evidence via an upstream shared contract; do **not** create another Silero/Whisper stack.
- [ ] Integrate ClosedRoom transcript with reviewable edit proposals without automatically removing speech.
- [ ] Detect suspected repeats and fillers as **review prompts**, never silent deletion.
- [ ] Editable subtitles using **actual** ClosedRoom word timestamps when available, otherwise segment-level review; safe-area previews.
- [ ] Test natural pacing vs aggressive auto cuts using three real clips.

## Studio UI testing milestone

- [x] Local web UI via `pausio studio` with video import, preview and graphical KEEP timeline.
- [x] Editable source-time ranges, restore decisions, original vs edited simulated preview, explicit approval and MP4 export.
- [x] Optional ClosedRoom transcript panel; existing ASR stack remains upstream.
- [x] Four tailored Studio UX/UI Agent Skills and automated HTTP/workflow tests.
- [ ] Validate real browser UX and accessibility on macOS at desktop/tablet/mobile widths.
- [ ] Run real Samsung A56 videos through the full preview and export; inspect VFR, rotation, codec and A/V sync.
- [ ] Add waveform extraction, frame-accurate edited preview and audio transitions.

## Portable instruction-driven editing

- [x] Every implemented Studio edit produces a typed command with stable IDs; replay is authoritative.
- [x] `.pausio.json` v1 export/import, JSON Schema, original-video SHA-256 binding and optimistic revision checks.
- [x] Deterministic replay to FFmpeg `EditPlan`, including concrete AI proposals and explicit approval.
- [x] Pure-domain and HTTP regression tests: replay, reimport, media mismatch and stale edits.
- [ ] Undo/redo and optional autosave based on a history cursor/checkpoints.
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
