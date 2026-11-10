# Pausio architecture

## Goal

video.mp4 → inspect → analyze → propose **editable** timeline → review → render 9:16 MP4. Preserve natural voice and don't introduce undisclosed automatic decisions.

## Modules (v0.1)

- domain.py: Interval and EditPlan (schema_version=1, integer milliseconds, validated, portable serialisation).
- planner.py: deterministic AI_NATURAL pause policy, completely independent of any ASR/vendor and unit-testable.
- media.py: FFprobe adapter (metadata), FFmpeg silencedetect adapter, FFmpeg filter-based renderer.
- closedroom_asr.py: localhost adapter to the **existing** ClosedRoom ASR service; source-time transcript sidecar (currently independent of edit planning).
- cli.py: CLI entrypoint, including `pausio studio`.
- project_commands.py: pure deterministic event reducer, versioned `.pausio.json` tape, media fingerprint binding, typed commands and state reconstruction. **Canonical source of truth** for UI edits.
- studio.py: local HTTP server, temporary workspace and asynchronous jobs; editing now dispatches validated project commands rather than overwriting UI-local state. Delegates to existing modules.
- studio_static/: offline HTML/CSS/JS workspace with video preview, graphical timeline, editable KEEP intervals, ClosedRoom transcript, and MP4 download. Python remains the plan's source of truth.

## Future boundaries

    input media (immutable)
      ├── probe adapter [ffprobe]
      ├── silence detector [ffmpeg; baseline signal-energy heuristic]
      ├── ASR/VAD [ClosedRoom local API; existing implementation]
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
