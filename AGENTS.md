# Instructions for coding agents working on Pausio

Pausio is a local-first, reviewable editor for natural talking-head videos. Read `README.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md` and `docs/ROADMAP.md` before architectural changes.

## Non-negotiable product contracts

- **UI tests must exercise real behavior:** import, analyze, edit KEEP spans, approve explicitly, render and download—never decorative mock controls. For UI changes, run `tests/browser/` via Playwright; review generated screenshots and 320px/390px layout measurements, not merely Python unit tests.
- **Undo/Redo are typed history operations with an exported active cursor and monotonic revision**; a new edit after Undo must truncate the redo tail, with v1 import compatibility. Tests must cover crash-safe disk writes and session recovery.
- **Every output-affecting UI edit MUST be a typed, deterministic, importable/exportable command** in `project_commands.py`, with stable IDs, integer millisecond units, strict schema validation and replay tests. The UI cannot own an untracked authoritative timeline; unknown command versions must fail closed. Read `docs/PROJECT_FORMAT.md`.
- **Models propose, humans approve, deterministic rendering executes.** Do not automatically render proposed edits without a user-controlled review step.
- Input media is immutable. Do not overwrite raw files; require explicit overwrite for outputs.
- Keep `src/pausio/domain.py` and `src/pausio/planner.py` independent of FFmpeg, ML frameworks, and UI.
- All edit-plan times are integer **milliseconds**. Intervals are half-open [start_ms, end_ms), sorted, non-overlapping, and validated. Preserve the versioned schema or write an explicit migration and tests.
- **ClosedRoom is the source of truth for transcription.** Reuse the working ASR in `daniele21/closedroom` (`dev`) via a narrow adapter. Never implement a parallel Whisper, faster-whisper, WhisperX, Nemotron or Silero ASR/VAD stack inside Pausio. If reusable engine extraction is needed, do it upstream in ClosedRoom.
- Studio binds exclusively to loopback; browser imports are copied into a private persistent local workspace for autosave/recovery. Respect the explicit delete action, 0600/0700 permissions on POSIX, atomic checkpoints, source-hash verification, single-process lock, CSRF safeguards and keyboard accessibility.
- Local-first means no implicit upload, telemetry, remote models or auto-downloading weights. Any network-dependent feature needs user opt-in.
- Do not vendor third-party media/editor code or distribute binaries/weights without documented licensing approval.
- Reject destructive changes, unstated fallback behaviors, silent speech removal and unreviewed AI decisions.

## Relevant local agent skills

Skills follow the [Agent Skills specification](https://agentskills.io/specification). Use the narrowest matching `.agents/skills/*/SKILL.md`; read its references only when needed. Skills are **engineering guidance**, not proof that a feature is implemented.

| Task | Skill |
| --- | --- |
| Python modules, domain contracts, refactoring or CLI | `pausio-python-architecture` |
| FFmpeg, FFprobe, encoding, timestamps or A/V sync | `pausio-media-ffmpeg` |
| Silence policies, jump cuts, creator pacing, human approval | `pausio-natural-editing` |
| ASR, word alignment, VAD, ML inference | `pausio-speech-ai` |
| Caption segmentation, SRT/ASS, visual safe areas | `pausio-subtitles` |
| Test changes, CI, regression fixtures, benchmarks | `pausio-test-engineering` |
| Privacy, dependencies, permissions, licenses, release | `pausio-security-release` |
| Bug diagnosis, code review, PR readiness | `pausio-pr-review` |
| User journey, step flow, review and helpful empty/error states | `pausio-product-ux` |
| Tokens, hierarchy, contrast, responsive layouts | `pausio-ui-design-system` |
| Video preview, scrubbing, jump-cut timeline and keyboard | `pausio-video-interaction-ux` |
| Typed edits, project import/export, replay, schema changes, undo/redo | `pausio-edit-command-schema` |
| Browser QA, accessibility and regressions | `pausio-ui-quality` |

## Workflow and evidence

1. Inspect the current implementation and identify the smallest scope.
2. State expected behavior, edge cases, and the test oracle; prefer a failing regression test for bugs.
3. Make a narrowly scoped change behind stable interfaces. Do not invent a capability absent from the code.
4. Run `python -m unittest discover -s tests -v`, `python -m compileall -q src` and `python scripts/validate_skills.py` where relevant. Run FFmpeg E2E and manual listening/video inspection for media changes.
5. Report exactly what was tested and what remains unverified. No claims of perfect fidelity without real recorded footage.

Use feature branches / PRs for substantive changes. Document architectural decisions in `docs/DECISIONS.md`. No raw video or transcripts in Git.
