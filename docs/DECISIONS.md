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

## ADR 007 — Pausio-owned standalone transcription (supersedes ClosedRoom API adapter)

**Decision:** Pausio directly implements an **independent** optional MLX Whisper ASR adapter in `src/pausio/local_asr.py`, using ClosedRoom `dev` as a design/reference, not an operational dependency. Users never need to open ClosedRoom, launch its HTTP service, or install it alongside Pausio. The local pipeline uses FFmpeg to extract temporary 16 kHz mono WAV, MLX Whisper to transcribe, and strict source-time timestamp normalization to produce a separate reviewable transcript.

**Security/runtime:** No model download by default. Resolve installed/cached local weight snapshots and pass only a local model path into MLX; allow a Hugging Face model download only after explicit consent in Studio or `--allow-model-download` on CLI. Audio is never uploaded. The core install stays dependency-light; use `pip install -e '.[asr]'` for optional Apple Silicon MLX packages.

**Limitations:** This first migration implements local Whisper, not full feature parity with ClosedRoom (Nemotron, diarization, VAD optimizations and persistent ASR jobs are out of scope). Model quality, A56 timing and Python 3.15 need validation on actual hardware. See [local ASR](LOCAL_ASR.md).

## ADR 008 — Typed edit commands are Pausio's canonical project format

**Decision:** all output-affecting Studio changes are represented as validated, deterministic, ordered operations in `src/pausio/project_commands.py`. The UI sends specific commands; Python replays them to derive the FFmpeg `EditPlan`. The portable `.pausio.json` document contains schema version, SHA-256 media binding and the command history without raw media or absolute paths. Import validates atomically and rejects unknown operations, versions and source mismatches.

**Consequences:** stable segment IDs; `timeline.replace` bridge for legacy clients; approval as an event, invalidated by subsequent editing. Reopening a project reconstructs cuts without rerunning ASR or silence analysis. Future prompt edits, subtitles, crop, gain and export settings must use new typed/versioned instructions. See [project format](PROJECT_FORMAT.md).

**Not delivered yet:** subtitle or audio effect commands, CapCut/OTIO importers, video embedding or byte-identical output across FFmpeg versions.

## ADR 009 — History cursor and recoverable private session

**Decision:** portable `.pausio.json` schema v2 adds `history_cursor` and monotonic `revision`. Undo/Redo are validated structured API operations that move the cursor over replayable events without adding synthetic inverses. Editing after Undo forks by dropping the redo tail. Import supports v1 and upgrades in memory while preserving event IDs. Rendering uses only the active prefix.

**Decision:** Studio's default runtime maintains one private, local, autosaved session on disk (including imported media) separately from the portable project. It commits a validated JSON snapshot atomically before exposing a UI change; retains one previous checkpoint for corruption fallback; verifies original-media SHA-256; and uses a single-process lock. On recoverability failure, do not silently delete the user's stored media. A deliberate UI action deletes managed local media and checkpoints. Users can select `--data-dir` for storage location.

**Limitations:** autosave covers active project, media and history; it does not restore in-memory Pausio transcript, unfinished renders, or multiple project workspaces. The exported portable file remains media-free.

## Unresolved

- Choose Pausio repository license intentionally before inviting source reuse.
- Validate Pausio MLX runtime and model/weight licensing, download UX and memory requirements with real Apple Silicon footage.
- Determine UI technology (web local vs packaged desktop), safe-area templates and subtitles format.
- Quantify performance on real Samsung video, VFR, rotation and audio drift.

## ADR 010 — Captions are portable source-time edit commands

**Decision:** `caption.set` records reviewed source-time subtitle cues (stable IDs, exact text, timestamps, style) as bounded v2 project events, not an entire raw ASR transcript. `caption.correct`, `caption.style`, and `caption.clear` are replayable/undoable. Subtitle edits invalidate approval and stale previews/exports.

**Render:** Pure code segments actual word-aligned transcripts into short captions; absent word alignments, it retains real phrase timings without inventing words. Intersect with KEEP intervals and map to output time, splitting cues crossing removed gaps. FFmpeg ASS/libass burns captions into both preview and final 9:16 MP4. HTML preview is only approximate; confirm quality using rendered preview. Font fallback and social safe areas remain real-device QA.

## ADR 011 — Private persisted transcript and portable subtitle appearance

**Local recovery:** A completed Pausio ASR result is validated, stripped of its absolute source path, and atomically saved in the private `pausio.local-session` schema v2 together with a SHA-256 binding to the retained media. Existing schema v1 sessions are recovered and upgraded by the next successful save. Errors never silently commit an unsaved transcript to memory. Clearing the session removes the transcript and media; new video import resets the transcript. Raw speech and word timestamps never enter the portable `.pausio.json` or Git.

**Styling:** Three built-in presets (Social, Minimal, Riquadro) and validated custom typography choices are represented by the typed `caption.configure` command. The config includes normalized percent coordinates bounded to a safe region (15–85% both axes), font size, colors, outline and optional background. The browser shows approximate preview and supports drag/keyboard adjustments; the exact configuration is converted into libass style colors and absolute positioning in the final 1080×1920 coordinate system, scaling for 540×960 preview. Changes invalidate old approvals and renders. No reliance on DOM state alone.

## ADR 012 — Safe, portable caption font family choice

**Decision:** Subtitle typography can select an allowlisted system font family, stored as `caption.configure.config.font_family` and applied to both the source-time browser overlay and FFmpeg ASS `Style: Caption,Fontname,...`. This is a *font family name*, not an uploaded font asset. No font binaries or remote font CDN are required or bundled. Reject arbitrary family strings to prevent ASS delimiter or control-sequence injection.

**Backward compatibility:** Old project v2 `caption.configure` events omit `font_family`; the replay validator accepts only that known omission and defaults to `Arial`. The JSON schema therefore permits the new key but does not require it, preserving historical project imports. New UI edits include it, and every font change invalidates approval and cached preview/render via existing typed-event semantics.

**Limits:** The operating system/libass must have the requested font installed; substitution can differ between the HTML canvas and exported MP4 on another machine. Display a warning and require real FFmpeg preview before delivery. Supporting user-supplied font uploads will need separate validated asset packaging and licensing policy.

## ADR 013 — Audio FX importato e local-first

**Decisione:** traccia FX opzionale per audio personale (riser, whoosh, impact). I comandi versionati `audio.add/update/remove` sono la sola fonte per il rendering, con undo/redo e riferimento al SHA-256 dell'asset privato; nessun percorso assoluto entra nel progetto portabile. Il video sorgente resta immutato. L'anteprima FFmpeg e l'export condividono il mix; la simulazione browser non è un'anteprima audio finale. Nessuna libreria di audio terzi viene vendorizzata senza verifica della licenza.


## ADR 014 — Mobile capture is a separate static, local-first recording surface

**Decision:** mobile teleprompter capture runs in the browser, not through Studio's loopback Python API. `getUserMedia` + `MediaRecorder` record the raw camera/microphone tracks; a DOM overlay scrolls the script strictly in preview, without burning the gobbo into the video. The final mobile action is an explicit download or system share of the recorded take (format depends on browser); users transfer and import it on desktop manually. No implicit networking, cloud processing or local Studio exposure. Source assets are shared between the local Studio `/capture` route and an isolated GitHub Pages static deployment.

**Boundaries:** this is acquisition, not a timeline edit; adjustable script/scroll settings do not alter exported pixels. Local storage contains only script/preferences; completed take blobs are not durable until downloaded. The full editor's command-led import/replay remains unchanged. Native/mobile MP4 transcoding, background recovery, LAN pairing, voice-follow and persistent take library are separate future ADRs. GitHub Pages availability and real Safari/Galaxy verification are deployment gates.

