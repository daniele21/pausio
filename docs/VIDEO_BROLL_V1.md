# Video B-roll v1 — local-first native cutaways

**Implementation scope:** `daniele/social-broll-video-v1` (proposed for merge).
This document describes implemented v1 functionality, not automated stock search.

## Creator workflow

1. Import the original talking-head recording and prepare the KEEP timeline.
2. Open **B-roll → Clip video B-roll** and place the playhead on the intended beat.
3. Import a **local MP4, MOV, MKV or WebM** up to 256 MiB. The uploaded clip
   stays in Studio's private local directory. Pausio probes its video stream,
   stores an SHA-256-addressed copy, and creates one reversible
   `video.broll.add` event on the **edited output** timeline.
4. Select the B-roll in the timeline or inspector and edit:
   output start/duration, source-media in-point, fullscreen/PIP layout,
   and PIP width/position. Changes are `video.broll.update` events.
   Removal is `video.broll.remove`. Undo/redo and project import/export
   replay exactly the same commands.
5. Render **FFmpeg preview** or a short timeline range. Approve the video
   separately in Studio before requesting a local final MP4.

**Audio rule:** the original speaker's audio remains the soundtrack.
The imported B-roll's audio is never mapped or mixed. Imported music/SFX
continue according to the project's separate audio instructions.

## Invariants

- The source video and external B-roll bytes are never included in the
  portable `.pausio.json` file; only SHA-256 and a safe display name.
  After importing a project on another Mac, relink the original asset.
- `ProjectTape` version 11 adds the three `video.broll.*` event types
  while accepting legacy v1–v10 projects.
- V1 allows **six non-overlapping video cutaways**, each 0.4–20 seconds,
  with source-in and edited-output placement validated independently.
  Images can still be layered over the video B-roll. The renderer uses a
  single FFmpeg graph for both preview and export.
- Import is limited to 256 MiB per video; the decoded source may be at
  most 3840×2160. The incoming file is probed and its SHA is checked
  again before rendering; symlinks and URLs are refused.
- Edits remain user-approved; this feature **does not** automatically
  download third-party footage or infer the best visual.

## Open-source references and adoption decisions

- [AutoBroll](https://github.com/andriidrok1/autobroll):
  adopt the edited-timeline B-roll mapping and multi-track UX concept,
  not Remotion as a parallel editing runtime.
- [FableCut](https://github.com/ronak-create/FableCut):
  reference for upcoming keyframe-based motion and audio ducking,
  not a mandatory JavaScript engine.

Native implementation is Python + FFmpeg, retaining the existing
`ProjectTape`, Studio and safety/approval boundaries.

## Verification

- `tests/test_video_broll.py`: validator rejects unknown or unsafe
  fields, overlapping clips, stale cut lengths, tampered digest; FFmpeg
  synthetic cutaway changes pixels only in its edited-output interval
  while retaining voice audio.
- `tests/test_video_broll_studio.py`: real local HTTP import + malformed
  upload, Studio revision enforcement, FFmpeg preview, event update,
  export portability, and delete-local-data cleanup.
- CI runs Python 3.11, 3.12 and 3.13 on Linux. **Mac Studio visual/audio
  review on a real talking-head recording is still required**, in
  particular variable-frame-rate footage, crops, safe zones and UI
  performance.

## Next milestones (not implemented in v1)

- Source catalogue with duplication/relink/thumbnail, provenance/licensing,
  manual sorting and audio fade/ducking.
- Motion presets with true in/out keyframes for B-roll, images and graphic
  cards; preview controls and selection/resize.
- AI planning that proposes B-roll shots from transcript + verified media
  assets, but never downloads or applies modifications without review.
