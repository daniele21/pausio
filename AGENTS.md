# Instructions for coding agents working on Pausio

Pausio is a local-first, reviewable editor for natural talking-head videos. Read `README.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md` and `docs/ROADMAP.md` before architectural changes.

## Non-negotiable product contracts

- **B-roll UX follows one timeline:** images are stored in output milliseconds but source ruler marks must project over KEEP segments without duplicating the command. Use the focused `studio_static/image_overlay_ui.js` + `image_overlay_ui.css`; never simulate a rendered image falsely or create a second renderer.
- **MCP parity is explicit, never assumed:** update `src/pausio/mcp_tool_catalog.py`, `docs/CHATGPT_EDITOR_TRIAL.md` and `tests/test_local_mcp.py` when exposing an existing feature. No ChatGPT client can directly reach the Studio loopback port; never silently approve/export or grant arbitrary file access. Studio remains canonical. Read `pausio-mcp-trust-boundary` and `pausio-network-abuse-defense` skills.
- **Keep frontend code focused:** new audio monitor/mixer functionality belongs in `studio_static/audio_monitor_ui.js`, not the existing `app.js`. Load classic deferred scripts in the declared HTML order; no npm, bundler, global duplicate controllers or second edit state. See `docs/STUDIO_FRONTEND_MODULES.md`.
- **UI tests must exercise real behavior:** import, analyze, edit KEEP spans, approve explicitly, render and download—never decorative mock controls. For UI changes, run `tests/browser/` via Playwright; review generated screenshots and 320px/390px layout measurements, not merely Python unit tests.
- **Undo/Redo are typed history operations with an exported active cursor and monotonic revision**; a new edit after Undo must truncate the redo tail, with v1 import compatibility. Tests must cover crash-safe disk writes and session recovery.
- **Every output-affecting UI edit MUST be a typed, deterministic, importable/exportable command** in `project_commands.py`, with stable IDs, integer millisecond units, strict schema validation and replay tests. The UI cannot own an untracked authoritative timeline; unknown command versions must fail closed. Read `docs/PROJECT_FORMAT.md`.
- **Models propose, humans approve, deterministic rendering executes.** Do not automatically render proposed edits without a user-controlled review step.
- Input media is immutable. Do not overwrite raw files; require explicit overwrite for outputs.
- Keep `src/pausio/domain.py` and `src/pausio/planner.py` independent of FFmpeg, ML frameworks, and UI.
- All edit-plan times are integer **milliseconds**. Intervals are half-open [start_ms, end_ms), sorted, non-overlapping, and validated. Preserve the versioned schema or write an explicit migration and tests.
- **Pausio owns its own standalone local ASR.** Use `daniele21/closedroom` (`dev`) as a *design/reference source only*, not a running service or mandatory dependency. Pausio transcribes directly on-device with its optional MLX Whisper engine (`local_asr.py`) on Apple Silicon. Models are offline-cache-only by default and network weight downloads require explicit user opt-in. Preserve real segment/word timestamps, no fake alignments or speech-derived cuts without review.
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
| Studio HTTP, MCP transport, gateway, traffic limits, DoS/DDoS, DNS rebinding | `pausio-network-abuse-defense` |
| MCP tools, authorization, chat agent permissions, prompt injection and private data | `pausio-mcp-trust-boundary` |
| untrusted media import, codecs, archives, SVG, paths and upload validation | `pausio-input-media-defense` |
| GitHub Actions, self-hosted transcription, workflow dispatch and runner secrets | `pausio-actions-runner-security` |
| Bug diagnosis, code review, PR readiness | `pausio-pr-review` |
| User journey, step flow, review and helpful empty/error states | `pausio-product-ux` |
| Tokens, hierarchy, contrast, responsive layouts | `pausio-ui-design-system` |
| Video preview, scrubbing, jump-cut timeline and keyboard | `pausio-video-interaction-ux` |
| Animated zoom, punch-in/out, reframing, transitions, cinematic motion or auto visual-effect suggestions | `pausio-visual-motion-effects` |
| Typed edits, project import/export, replay, schema changes, undo/redo | `pausio-edit-command-schema` |
| Browser QA, accessibility and regressions | `pausio-ui-quality` |

## Workflow and evidence

1. Inspect the current implementation and identify the smallest scope.
2. State expected behavior, edge cases, and the test oracle; prefer a failing regression test for bugs.
3. Make a narrowly scoped change behind stable interfaces. Do not invent a capability absent from the code.
4. Run `python -m unittest discover -s tests -v`, `python -m compileall -q src` and `python scripts/validate_skills.py` where relevant. Run FFmpeg E2E and manual listening/video inspection for media changes.
5. Report exactly what was tested and what remains unverified. No claims of perfect fidelity without real recorded footage.

Use feature branches / PRs for substantive changes. Document architectural decisions in `docs/DECISIONS.md`. No raw video or transcripts in Git.

## Agent-ready editing contract (planned direction)

For any overlay, audio loudness, media-library, self-hosted runner or chat connector change, **read [docs/AGENTIC_EDITING_PLAN.md](docs/AGENTIC_EDITING_PLAN.md) before implementation**. ChatGPT and Claude Chat provide creative/editorial reasoning through users' existing chat subscriptions; Pausio provides read-only observations and validated editing tools, and MUST NOT silently add OpenAI/Anthropic API-key inference or an in-process semantic video agent. The same typed edits must work in UI, import/export and future MCP tools with identical renderer semantics.

Every agent-facing write MUST be a versioned, bounded, deterministic project command or atomic batch with source-media SHA-256, expected project revision, asset identity, provenance and testable validation. MCP handlers call the same application service as Studio. Do not expose the local Studio HTTP server directly over the internet, allow arbitrary shell commands, grant filesystem-wide access, bypass user approval, or transmit user video/transcript/asset bytes remotely without opt-in. Chat client and MCP support are capability gates: implement a minimal real-client spike before promising automated editing. See WP0/WP1/WP7 of the plan.

The existing Playwright, FFmpeg, Python, media hash, autosave and privacy requirements apply unchanged to agent-proposed edits. Any conflict with the plan must be resolved in an ADR first.

## Mandatory security skill selection (effective on every new integration)

**Before changing any HTTP/MCP/remote integration, job, upload or GitHub Action:**
- Inspect the trust boundary and load `.agents/skills/pausio-network-abuse-defense/SKILL.md` for traffic/resource and DNS-rebinding changes.
- Load `.agents/skills/pausio-mcp-trust-boundary/SKILL.md` for each agent tool/connector and sensitive data flow.
- Load `.agents/skills/pausio-input-media-defense/SKILL.md` for media import, FFmpeg ingestion, asset library, SVG and project bundles.
- Load `.agents/skills/pausio-actions-runner-security/SKILL.md` for CI, release, dispatch or self-hosted transcription.
- Apply the existing `pausio-security-release`, `pausio-edit-command-schema` and `pausio-test-engineering` as applicable.

**Threat priority:** GitHub Pages is static and hosted by GitHub; local Studio/stdio MCP must stay on loopback. No public tunnel of Studio. A future public MCP gateway requires independent authenticated HTTPS, per-user and global quotas, bounded workers/jobs, abuse/incident monitoring and edge-level DDoS mitigation **before** any deployment. Local socket/Host controls do not prevent a distributed flood against public infrastructure. Never attach an untrusted public-repo PR workflow to the user's self-hosted Mac.

All security controls must have adversarial tests; skill documents alone are not defenses. See `docs/SECURITY_THREAT_MODEL.md` for the trust matrix and acceptance gates.

## Motion effects and transitions

When changing any video zoom/crop/keyframe, jump-cut transition, automatic visual rhythm or kinetic caption feature, load `.agents/skills/pausio-visual-motion-effects/SKILL.md` and read `docs/VISUAL_MOTION_EFFECTS_PLAN.md` before implementation. Visual effects are not freeform FFmpeg commands: each effect is a versioned, bounded project event with source-accurate timestamps, preview/export parity, undo/redo and explicit acceptance of automated suggestions. Avoid noisy automatic effects on every cut. Combine with media security and command schema skills.

### Rule for auto visual-effects profiles

`configs/visual_fx_presets_v1.json` and `schemas/pausio-visual-fx-presets-v1.schema.json` are currently **configuration designs**, not working editing features. Read `docs/VISUAL_FX_AUTOMATION_RESEARCH.md` and use `pausio-visual-motion-effects` before adding/modifying profile fields or the suggestion engine; run `python scripts/validate_visual_fx_presets.py`. Default Naturale; preserve manual edits; no silent effect application, permission escalation, raw FFmpeg expression or remote model API. Stage candidate generation and review separately from project mutation and output export.
