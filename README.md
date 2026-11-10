# Pausio

**Edit the noise. Keep the voice.**

A local-first toolkit for natural-sounding, talking-head social videos. Pausio is designed to make post-production **reviewable**, not fully automatic at the expense of speech or pacing.

> **Status: early foundation (v0.1.0).** The current CLI inspects videos, suggests cuts using FFmpeg's signal-level silence detection, writes a human-editable JSON timeline, and exports a vertical MP4. **It does not yet transcribe speech, identify mistakes semantically, remove filler words, generate subtitles, denoise audio, or export CapCut projects.**

## Why Pausio?

- Preserve breathing space and natural speech instead of eliminating every pause.
- Make every automatic edit inspectable before rendering.
- Keep raw media and processing on your machine; no account or cloud service required.
- Build modular adapters around tools such as FFmpeg, ASR, VAD and subtitle renderers.
- Produce a reusable 9:16 master without binding output to a specific social platform.

## Quickstart

Requires **Python 3.11+** and the **FFmpeg + FFprobe** executables on PATH. On macOS, for example: brew install ffmpeg.

    git clone https://github.com/daniele21/pausio.git
    cd pausio
    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install -e .
    pausio doctor
    pausio inspect /path/to/input.mp4
    pausio plan /path/to/input.mp4 --output /path/to/edit-plan.json
    # OPEN THE JSON and review/adjust its segments before rendering.
    pausio render /path/to/edit-plan.json --output /path/to/edited.mp4

If Pausio is not on your PATH, you can use python -m pausio after installation.

### Reviewable edit plan

The plan is a JSON file with these fields (see examples/edit-plan.example.json):

- schema_version: 1
- source: input file path
- source_duration_ms: source duration in milliseconds
- has_audio: audio track availability
- preset: ai-natural
- segments: ordered, non-overlapping intervals to KEEP, with start_ms and end_ms

You can delete, extend, or adjust segments by hand. Pausio validates ordering, bounds and overlap on load. Relative source paths are interpreted relative to the plan file. Files are never overwritten without --overwrite.

### Early editing policy

The ai-natural policy uses FFmpeg silencedetect to find **low-energy audio**, not to infer speech or narrative intent. It suggests cuts only inside longer silences, leaving some breathing room on either side. Extremely short speech sections are protected. Review is mandatory: quiet words, ambient noise, music, loud pauses and bad microphones can defeat signal-level detection.

Use pausio render edit-plan.json -o export.mp4 --dry-run to inspect the FFmpeg command without exporting.

## Commands

| Command | Purpose |
| --- | --- |
| pausio doctor | Check FFmpeg/FFprobe installation |
| pausio inspect INPUT | Show duration, dimensions, codec and audio presence |
| pausio plan INPUT -o plan.json | Propose editable keep intervals from silence events |
| pausio render plan.json -o video.mp4 | Re-encode approved plan as 1080x1920, 30 fps H.264/AAC MP4 |

## Architecture

A pure-Python domain model and policy (domain.py, planner.py) are independent of FFmpeg (media.py) and CLI (cli.py). Future ASR/VAD/denoise/CapCut adapters plug into the same versioned edit plan. See docs/ARCHITECTURE.md, docs/ROADMAP.md, docs/DECISIONS.md and docs/DEPENDENCIES.md.

## Development

    python -m pip install -e .
    python -m unittest discover -s tests -v

The tests include synthetic video/audio FFmpeg smoke tests (skipped if FFmpeg is missing). CI runs against Python 3.11, 3.12 and 3.13 and installs FFmpeg. No third-party source code is copied into this repository.

## Limitations / safety

- VFR phone footage is re-timed to 30 fps for export; review for audio/video sync on real devices.
- Signal-level silence is not voice activity detection. It may mark whispering as silence or fail in background noise.
- There are no automatic uploads, models, telemetry or remote services.
- Keep private recordings, speech transcripts, assets and model weights out of Git.
- Export currently creates a padded 9:16 canvas rather than smart reframing/cropping.
- Licensing for the Pausio application itself remains to be decided. This public repository does not grant an open-source license yet; see docs/DEPENDENCIES.md.

## Next milestone

Add ASR with accurate Italian transcripts and word timestamps, local speech-aware VAD, a timeline review interface, editable subtitles, voice-aware audio transitions and an optional CapCut export adapter. These are deliberately not part of the basic FFmpeg core.
