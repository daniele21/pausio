# Engineering decisions / ADRs

## ADR 001 — One repo, modular adapters

**Decision:** build an original, small Python codebase that orchestrates FFmpeg and optional later engines. Do not merge or copy multiple upstream repositories. This reduces GPL/AGPL contamination risk, upgrade costs and coupling.

## ADR 002 — Plans before destructive automation

**Decision:** machine proposes segments (what to keep); user inspects/edits JSON and separately invokes render. The source remains immutable. Next UI can visualize the same schema.

## ADR 003 — Silence is not speech

**Decision:** initial signal-level silence detection offers conservative suggestions only. Never claim to cut mistakes, filler words or repeated sentences without ASR/VAD and human review.

## ADR 004 — FFmpeg as external binary

**Decision:** invoke FFmpeg and FFprobe through subprocess with argument arrays (never shell=True). Do not bundle a binary in v0.1. End users install their own build. Distribution packaging and FFmpeg compile flags/licenses need separate analysis before any release.

## ADR 005 — Keep dependencies thin

**Decision:** Python standard library for runtime; FFmpeg executables are optional until a media command is invoked. Limit dependency management complexities and allow fast tests.

## ADR 006 — Vendor-neutral project format

**Decision:** versioned JSON in integer milliseconds, source references relative to plan directory or absolute. Future CapCut export will be a translator layer, not the primary storage format.

## Unresolved

- Choose Pausio repository license intentionally before inviting source reuse.
- Pick ASR backend and model distribution/weights license; benchmark on Italian clips.
- Determine UI technology (web local vs packaged desktop), safe-area templates and subtitles format.
- Quantify performance on real Samsung video, VFR, rotation and audio drift.
