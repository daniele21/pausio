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

## ADR 007 — Reuse ClosedRoom transcription

**Decision:** ClosedRoom (`daniele21/closedroom`, `dev`) is Pausio's sole transcription implementation. Pausio uses the existing local `POST /v1/audio/transcriptions/path` endpoint with `response_format=verbose_json` and `asr_provider=local` over loopback. It extracts a temporary audio track from video, normalizes segment/word timestamps into source-time milliseconds and saves a reviewable sidecar; MLX Whisper, Nemotron, model settings, cache and VAD remain owned by ClosedRoom. No copied/forked ASR code and no secondary Pausio ASR runtime.

**Future:** if local API distribution is unsuitable, extract a reusable library **inside ClosedRoom** and version it for both consumers. Pin and contract-test any stable version before distributing. Live compatibility and source timing have not yet been verified with real A56 video.

## ADR 008 — Typed edit commands are Pausio's canonical project format

**Decision:** all output-affecting Studio changes are represented as validated, deterministic, ordered operations in `src/pausio/project_commands.py`. The UI sends specific commands; Python replays them to derive the FFmpeg `EditPlan`. The portable `.pausio.json` document contains schema version, SHA-256 media binding and the command history without raw media or absolute paths. Import validates atomically and rejects unknown operations, versions and source mismatches.

**Consequences:** stable segment IDs; `timeline.replace` bridge for legacy clients; approval as an event, invalidated by subsequent editing. Reopening a project reconstructs cuts without rerunning ASR or silence analysis. Future prompt edits, subtitles, crop, gain and export settings must use new typed/versioned instructions. See [project format](PROJECT_FORMAT.md).

**Not delivered yet:** subtitle or audio effect commands, CapCut/OTIO importers, video embedding or byte-identical output across FFmpeg versions.

## ADR 009 — History cursor and recoverable private session

**Decision:** portable `.pausio.json` schema v2 adds `history_cursor` and monotonic `revision`. Undo/Redo are validated structured API operations that move the cursor over replayable events without adding synthetic inverses. Editing after Undo forks by dropping the redo tail. Import supports v1 and upgrades in memory while preserving event IDs. Rendering uses only the active prefix.

**Decision:** Studio's default runtime maintains one private, local, autosaved session on disk (including imported media) separately from the portable project. It commits a validated JSON snapshot atomically before exposing a UI change; retains one previous checkpoint for corruption fallback; verifies original-media SHA-256; and uses a single-process lock. On recoverability failure, do not silently delete the user's stored media. A deliberate UI action deletes managed local media and checkpoints. Users can select `--data-dir` for storage location.

**Limitations:** autosave covers active project, media and history; it does not restore ClosedRoom transcript, unfinished renders, or multiple project workspaces. The exported portable file remains media-free.

## Unresolved

- Choose Pausio repository license intentionally before inviting source reuse.
- Validate ClosedRoom adapter and model/weight distribution policy; engine choice stays in ClosedRoom.
- Determine UI technology (web local vs packaged desktop), safe-area templates and subtitles format.
- Quantify performance on real Samsung video, VFR, rotation and audio drift.
