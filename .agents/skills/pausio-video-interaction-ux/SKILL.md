---
name: pausio-video-interaction-ux
description: Use when implementing Pausio video preview, source-vs-edit playback, seek/scrubbing, timeline keep/exclude regions, range editing, keyboard shortcuts, AV sync or export-review interactions.
---

# Editing interactions: video truth first

## Mental model
Source-time intervals are KEEP decisions in milliseconds. The **original** uses original source time; the **montaggio preview** skips excluded spans and shows estimated output-time duration. Never mutate the source video.

## Procedure
1. Read `src/pausio/domain.py`, `studio.py`, `studio_static/app.js` and `docs/STUDIO_UI.md` before adding controls.
2. Timeline regions and inspector cards must represent the same validated edit plan; no parallel client-only source of truth. Send every edit via `POST /api/command` with stable segment ID and revision; see `pausio-edit-command-schema`.
3. Make scrubbing direct and responsive; support pointer and keyboard. Read out times with tabular numerals and distinguish original/output time.
4. Prevent invalid edits (negative, inverted, overlaps, end beyond duration) at the server boundary; show a recoverable error in UI and preserve prior plan.
5. Browser seek simulation may skip/jitter due to keyframes; explicitly label it **Simulazione**, not final-render proof. Provide a separate low-resolution FFmpeg-rendered preview using the same temporal pipeline as final export. Changes must invalidate its cache; compare actual audio cuts in the preview and full export.
6. Playback controls: visible play/pause, ±5s, original/montaggio switch, seek, transcript segment click. No overloaded ambiguous icons without names.
7. Explicit "Conferma montaggio" must gate exporting; any edit removes approval. Busy jobs disable conflicting actions.
8. Keep waveform tied to **source timestamps**, not edited-output time; it is evidence derived from the local source PCM, not an editable audio asset. For trim handles, keyboard ±100ms / Shift ±500ms and pointer dragging must generate the same typed `segment.update` command with a stable ID and revision. Ensure non-overlap and min trim length. Include FFmpeg synthetic media tests and verify visually when a browser is available.

See [timeline interaction contract](references/timeline-contract.md).
