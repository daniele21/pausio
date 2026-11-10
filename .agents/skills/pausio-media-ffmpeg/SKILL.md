---
name: pausio-media-ffmpeg
description: Use for Pausio FFmpeg or FFprobe work, trimming, concatenation, encoding, audio/video synchronization, PTS/DTS, phone VFR footage, rotation metadata, color and 9:16 output. Require executable media tests and conservative quality checks.
---

# FFmpeg & media engineering for Pausio

## Procedure
1. Inspect real source streams with `ffprobe` (duration, time_base, avg_frame_rate, r_frame_rate, rotation/display matrix, stream start_time, sample rate and channel layout). Do not assume phone MP4 is constant frame rate.
2. State the target for both **source time** (edit-plan milliseconds) and **output time** (concatenated timeline). Preserve boundaries, audio sync and natural cadence.
3. Keep FFmpeg commands as argument arrays with `subprocess.run`, no `shell=True`, `-nostdin`, explicit stream maps, errors and timeouts. Paths may contain spaces/unicode.
4. Validate filtergraphs for no-audio inputs, multiple keep segments, first/last boundaries, tiny segments, VFR, portrait rotation and mismatched stream start times.
5. Re-encode safely, stage outputs and publish atomically after success; source and prior exports must not be corrupted by an encoder failure.
6. If changing resizing, report whether export pads, crops or smart-reframes. Today it **pads preserving aspect ratio**, 1080x1920 / 30 fps.
7. Add synthetic FFmpeg E2E tests; where quality depends on perception, request human playback/listening with a real smartphone fixture. Never infer A/V sync from output duration alone.

## Quality gates
- Video/audio streams and output dimensions correct, playable and aligned at beginning/middle/end.
- No missing phonemes, clicks, unintended hard shifts in ambience, or dropped final frames in human review.
- Repeated renders deterministic under the same binary version/settings.
- Failures leave source untouched.

See [media checks](references/media-checks.md) for reproducible probes and corner cases.
