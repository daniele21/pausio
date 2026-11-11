# Pausio Studio — desktop-first editor UX

## Product goal and scope

The three desktop mockups describe **views of one editor**, not three separate
documents. Selecting Media, Tagli AI, Trascrizione, Sottotitoli or Audio must
preserve playback position, the authoritative edit timeline, unsaved input
drafts and playback mode. This implementation is intentionally incremental:
all media decisions still pass through the current validated project commands;
no video/audio transformation is calculated by the visual shell.

The mockups are aspirational. In particular, multiple independent media tracks,
music libraries, arbitrary clip speed, fades, EQ, filmstrip thumbnails and
individually movable subtitle cues **are not claimed to exist** in v0.1.0.

## Implemented in the first P0 increment

- Desktop-only workspace navigation with six modes. Tool sections appear
  contextually while retaining the original mobile/tablet layout.
- Preview, approval and export remain accessible within one viewport at
  common desktop sizes; desktop header actions delegate to the existing
  functional actions and mirror their enabled/disabled states.
- Timeline and mixer share the bottom editing dock. The timeline height is
  keyboard/pointer adjustable and remembered locally.
- The existing FX inspector controls are reused in the Audio workspace,
  without cloning the controls or creating divergent audio state.
- Captions/Transcription modes open the existing transcript/caption inspector.
- UI preferences (`pausio-studio-workspace`,
  `pausio-studio-dock-height`) are saved in browser localStorage; they do
  **not** enter `.pausio.json` and do not alter the export revision.

### States and interaction contract

- Import: primary action remains visible from the Media workspace, including
  the `Analizza le pause` next action; all modes remain navigable.
- Cuts: presets plus analysis action in left pane, same validated intervals and
  trims in the inspector/timeline.
- Transcript: ASR settings and action left; existing transcript/captions right.
- Captions: the existing caption inspector and preview drag still perform
  `caption.configure` / `caption.update` commands. This P0 shell **does
  not** introduce an independent editable subtitle track.
- Audio: FX clips remain editable and share source-time ruler with video.
  Mixer and original waveform remain bound to the same project state.
- Approval/export: changing video/audio/caption data invalidates approval as
  before. The desktop actions are delegates, not a second rendering pipeline.
- Tablet/mobile: legacy content ordering is retained; at 390px and 320px the
  timeline must remain after the preview and before inspector. Navigation rail
  and drag-resize affordance are desktop-only.

## Next milestones

### P1 — clip-centric timeline and contextual inspector

- Add a single ephemeral `EditorSelection` model (clip ID/type, source/output
  time, no shadow authoritative media timeline).
- Click on a KEEP segment or FX clip selects it; inspector shows its real,
  supported properties, with keyboard selection and clear focus.
- Improve track headers and use a compact per-track mixer control without
  adding multiple competing volume sliders.
- Add better ruler ticks, playhead-centered zoom and timecode inspection;
  verify source-vs-output mapping when excluded regions are present.
- If a proposed edit needs a new command type, add reducer, schema, migration,
  replay, Undo/Redo, FFmpeg export and tests before enabling the UI control.

### P2 — text and subtitles workspace

- Build a list of transcript/caption blocks with selected-cue focus and
  synchronized seek; keep caption word timestamps from local ASR.
- Expose existing caption commands, font/preset/position, and live preview
  with social platform safe-area overlay.
- Add a real subtitle cue track only after its source/edited time semantics
  and keyboard/dragging contract are designed and tested.
- Avoid fake controls for media speed, fades, per-word animation, SRT export.

### P3 — QA and polish

- Automated Playwright: empty and edited 1920x1080, 1440x900, 1280x720,
  1024x768, 768x900, 390x844, 320x700.
- Keyboard: navigation, trim ±100ms, space playback, undo/redo,
  full tab focus, dock resize via arrow keys, 200% zoom; screen reader roles.
- Persistence: reload view/dock and keep media/revision unchanged; import/export
  `.pausio.json` and verify typed command replay.
- E2E with synthetic media: import, analyze, select/edit, preview FFmpeg,
  approval, export, direct download. Separate real media acceptance checks
  for audio continuity, safe subtitle zone and codec compatibility.

## Branch/dependency strategy

The first implementation is on `daniele/desktop-editor-ux`, **based on**
`daniele/audio-fx-import` (PR #18) because the screenshot layouts include the
audio FX mixer from that branch. Create a stacked PR targeting the audio branch.
When the audio branch lands on `main`, rebase/retarget after CI and conflict
resolution. Do not push directly to `main`.

## Review requirements

Screenshots from Playwright artifacts are mandatory for final UX acceptance,
as well as green Python/Playwright workflows; the change is not considered
production-ready merely because static HTML/CSS review passes. Avoid new
third-party JS/CSS/CDN dependencies. Keep original videos immutable.
