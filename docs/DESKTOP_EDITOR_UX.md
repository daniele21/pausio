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

## Additional implemented increments (P1 / first P2 slice)

- **P1 selection:** A single ephemeral `editorSelection` state links actual
  KEEP segment IDs and imported FX clip IDs between timeline and existing
  inspector controls. Selection uses real buttons and keyboard activation,
  highlights the chosen item, seeks to the right source/output timestamp, and
  switches to the relevant workspace.
- **No hidden edit:** Selecting, focusing, changing tabs, or clearing selection
  never invokes a project command or changes project revision. Real edits
  still use validated `segment.update`, `audio.update`, `audio.clip.mix`,
  and `caption.correct` commands as before.
- **P2 caption cue preview:** A new subtitle lane visualizes real caption cue
  timestamps on the **source-time** timeline. Clicking a cue selects the
  corresponding existing caption correction field; the cue layout has no
  independent editable state. Excluded source spans remain visible as source
  references but are omitted by the deterministic final render.
- **QA added:** Playwright regression assertions now cover read-only segment,
  FX and caption selection; time ruler alignment; workspace switching; focus
  targeting and preservation of project revision. Browser QA and screenshots
  must still be executed before merge.

## Next milestones

### P1 — clip-centric timeline and contextual inspector (partly implemented)

- Selection and inspector cross-navigation are implemented (see above).
- Continue consolidating true contextual properties of the selected FX/segment
  without duplicating controls in multiple locations.
- Improve track headers and use a compact per-track mixer control without
  adding multiple competing volume sliders.
- Add better ruler ticks, playhead-centered zoom and timecode inspection;
  verify source-vs-output mapping when excluded regions are present.
- If a proposed edit needs a new command type, add reducer, schema, migration,
  replay, Undo/Redo, FFmpeg export and tests before enabling the UI control.

### P2 — text and subtitles workspace (caption lane preview implemented)

- The existing caption correction list can be selected from the cue track,
  with source-time seek and selected field focus.
- Continue improving fast transcript readability and search/selection across
  recognized words, preserving exact local ASR timestamps.
- Expose existing caption commands, font/preset/position, and live preview
  with social platform safe-area overlay.
- The cue lane is currently **select-only**; before allowing temporal dragging,
  define and implement a dedicated typed cue-time command with reducer,
  schema validation, FFmpeg remapping and undo/replay tests.
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
