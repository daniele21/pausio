# Pausio

**Edit the noise. Keep the voice.**

A local-first toolkit for natural-sounding, talking-head social videos. Pausio is designed to make post-production **reviewable**, not fully automatic at the expense of speech or pacing.

> **Status: early foundation (v0.1.0).** The current CLI inspects videos, suggests cuts using FFmpeg's signal-level silence detection, writes a human-editable JSON timeline, and exports a vertical 1080x1920 MP4. It **does not yet** transcribe speech, remove filler words, generate subtitles, denoise audio, or export CapCut projects.

## Quickstart

Requires Python 3.11+, FFmpeg and FFprobe executables on PATH (on macOS: `brew install ffmpeg`).

```bash
git clone https://github.com/daniele21/pausio.git
cd pausio
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
pausio doctor
pausio inspect video.mp4
pausio plan video.mp4 -o plan.json
# Review and edit the JSON keep segments first.
pausio render plan.json -o final.mp4
```

The edit plan stores versioned integer-millisecond KEEP intervals. Editing decisions remain reversible; source video is never overwritten. Exports are padded 9:16, 30 fps H.264/AAC MP4. Use `pausio render plan.json -o final.mp4 --dry-run` to inspect the FFmpeg command.

## Project principles

- Preserve natural cadence rather than removing all silence.
- Local-first; no implicit uploads, telemetry or model downloads.
- Keep raw media immutable; inspect the plan before rendering.
- Separate domain/policy from external media and ML adapters.
- Tests and human media review are needed before claiming quality.

## Developer setup

```bash
python -m pip install -e .
python scripts/validate_skills.py
python -m unittest discover -s tests -v
python -m compileall -q src
```

CI tests Python 3.11–3.13 and synthetic FFmpeg E2E cases. Real Galaxy A56 footage, VFR sync, subtitle readability and editorial naturalness still require real-media evaluation.

### Agent skills for contributors

Pausio ships **eight task-specific Agent Skills** under [`.agents/skills/`](.agents/skills/README.md), covering Python architecture, FFmpeg, natural editing, local speech AI, subtitles, test engineering, security/releases and PR review. Read [`AGENTS.md`](AGENTS.md) for repo invariants and [`docs/AGENT_SKILLS.md`](docs/AGENT_SKILLS.md) for task triggers, agent compatibility, source references, validation and evaluation prompts.

These are guidance for coding agents, not runtime features. Adding them does not install WhisperX, Silero VAD or a graphical editor.

## Current modules and documentation

- `src/pausio/domain.py`: validated immutable edit-plan model.
- `src/pausio/planner.py`: deterministic AI Natural cut policy.
- `src/pausio/media.py`: FFprobe / FFmpeg adapters.
- `src/pausio/cli.py`: `doctor`, `inspect`, `plan`, `render`.
- [Architecture](docs/ARCHITECTURE.md) · [Decisions](docs/DECISIONS.md) · [Roadmap](docs/ROADMAP.md) · [Dependencies/licensing](docs/DEPENDENCIES.md).

The source-license decision remains open: public repository visibility does not automatically grant reuse rights. See `docs/DEPENDENCIES.md`.
