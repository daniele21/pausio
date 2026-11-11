# Pausio architecture

## Goal

video.mp4 → inspect → analyze → propose **editable** timeline → review → render 9:16 MP4. Preserve natural voice and don't introduce undisclosed automatic decisions.

## Modules (v0.1)

- domain.py: Interval and EditPlan (schema_version=1, integer milliseconds, validated, portable serialisation).
- planner.py: deterministic AI_NATURAL pause policy, completely independent of any ASR/vendor and unit-testable.
- media.py: FFprobe adapter (metadata), FFmpeg silencedetect adapter, bounded PCM waveform envelope and FFmpeg filter-based renderer with common temporal pipeline for full and draft preview profiles.
- local_asr.py: standalone on-device MLX Whisper adapter with explicit model download opt-in; normalized source-time transcript sidecar (independent of edit planning).
- cli.py: CLI entrypoint, including `pausio studio`.
- project_commands.py: pure deterministic event reducer, versioned `.pausio.json` v2 tape with active history cursor, monotonic revision, v1 import migration, media fingerprint binding and state reconstruction. **Canonical source of truth** for UI edits.
- studio_persistence.py: private persistent local workspace, media fingerprint verification, process lock, atomic checkpoint with previous-state fallback and explicit privacy cleanup (separate from portable project JSON).
- studio.py: local HTTP server, private autosaved workspace, restart recovery and asynchronous jobs; every edit and Undo/Redo is a validated command or cursor transition, not an untracked UI state mutation. Delegates to existing modules.
- studio_static/: offline HTML/CSS/JS workspace with extracted audio waveform, source-time timeline zoom/trim handles (typed commands), simulated or FFmpeg-rendered preview, Pausio local transcript, and MP4 download. Python remains the plan's source of truth.

## Future boundaries

    input media (immutable)
      ├── probe adapter [ffprobe]
      ├── silence detector [ffmpeg; baseline signal-energy heuristic]
      ├── ASR [Pausio local MLX Whisper; optional packages and model cache]
      └── denoise adapter [optional, never destructive]
             ↓
    analysis bundle (timestamps + confidence + provenance)
             ↓
    deterministic editing policy (AI Natural)
             ↓
    versioned edit decision format (segments + subtitles + transitions)
             ↓
    review UI / CLI explicit approval
             ↓
    renderer adapters [FFmpeg] and project exporters [CapCut optional]
             ↓
    master + sidecars + audit log

## Design contracts

1. **Local-first**: source data never leaves machine unless user explicitly activates a future network adapter.
2. **Immutability**: raw source never overwritten and render output requires an explicit path.
3. **Human in control**: proposed edit plan is visible; plan never automatically invokes render.
4. **Deterministic plan**: planner takes milliseconds, intervals and policy; no side effects or model calls.
5. **Stable schema**: reject unknown future schema versions rather than silently reinterpret edits.
6. **Modularity**: dependencies are adapters, not vendored forks; isolate ffmpeg command composition from business policy.
7. **Provenance and reproducibility**: capture binary versions, model settings and decisions in later schema revisions.
8. **Portable integrations**: platform format-specific logic lives in exporters/, not the core plan.

## Practical limitations

V0.1 has one local source video, one audio track at most, and a sequence of kept intervals; no title cards, crossfades, music, subtitles, speaker separation, intelligent crop or semantic edits. Real phone media can have VFR timestamps, rotation metadata, codecs and timing anomalies. E2E tests must be expanded with Android footage before claiming production readiness.
