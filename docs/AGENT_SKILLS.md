# Agent Skills for Pausio

Pausio uses the portable [Agent Skills specification](https://agentskills.io/specification): a directory containing `SKILL.md` (YAML frontmatter `name` + `description`) and optional `references/`. The **canonical source** is `.agents/skills/`. These instructions were written for Pausio; no upstream skill implementation was copied or installed.

## Why skills?
`AGENTS.md` contains permanent engineering and safety invariants. Individual skills load only on matching tasks, limiting noise and cross-domain conflicts. Skills do not replace CI, code review or human media QA.

| Installed skill | When to use | Boundary |
| --- | --- | --- |
| [pausio-python-architecture](../.agents/skills/pausio-python-architecture/SKILL.md) | Python core, JSON schema, interfaces, CLI | No media signal tuning |
| [pausio-media-ffmpeg](../.agents/skills/pausio-media-ffmpeg/SKILL.md) | FFmpeg, VFR, timebases, encoding and A/V sync | No editorial policy |
| [pausio-natural-editing](../.agents/skills/pausio-natural-editing/SKILL.md) | Natural rhythm, cut policy, reviewable proposals | No ASR internals |
| [pausio-speech-ai](../.agents/skills/pausio-speech-ai/SKILL.md) | ClosedRoom ASR reuse, VAD, local adapter contracts | No parallel ASR or edit approval |
| [pausio-subtitles](../.agents/skills/pausio-subtitles/SKILL.md) | Italian captions, timing, safe areas | No raw codec design |
| [pausio-test-engineering](../.agents/skills/pausio-test-engineering/SKILL.md) | Unit/E2E tests, CI, golden-media evaluation | No release sign-off |
| [pausio-security-release](../.agents/skills/pausio-security-release/SKILL.md) | Privacy, dependency licenses, releases | No editorial strategy |
| [pausio-pr-review](../.agents/skills/pausio-pr-review/SKILL.md) | Debugging, PR review and regression triage | No feature implementation |

Tasks may use two relevant skills; avoid loading the entire catalog by default.

## Structured editing commands and portable projects

Use [pausio-edit-command-schema](../.agents/skills/pausio-edit-command-schema/SKILL.md) whenever adding an edit tool, changing project import/export, implementing AI prompt edits, undo/redo or external interchange. All output-affecting UI actions must have typed commands with deterministic replay. Undo/Redo use a V2 history cursor and monotonic revision; autosave commits a private local project plus media atomically, with recovery tests. Portable project export remains media-free. See [PROJECT_FORMAT.md](PROJECT_FORMAT.md).

## Pausio Studio UX/UI skills

| Skill | What it addresses |
| --- | --- |
| [pausio-product-ux](../.agents/skills/pausio-product-ux/SKILL.md) | Creator journey, states, clear confirmation before export |
| [pausio-ui-design-system](../.agents/skills/pausio-ui-design-system/SKILL.md) | UI tokens, brand direction, hierarchy, accessibility |
| [pausio-video-interaction-ux](../.agents/skills/pausio-video-interaction-ux/SKILL.md) | Preview, timeline, scrubbing, source/output time |
| [pausio-ui-quality](../.agents/skills/pausio-ui-quality/SKILL.md) | UI regressions, browser/keyboard/responsive QA |

These are original Pausio-specific instructions inspired by [Anthropic Frontend Design](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md), [Vercel Web Interface Guidelines](https://github.com/vercel-labs/agent-skills/blob/main/skills/web-design-guidelines/SKILL.md) and [UI/UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill). We reuse their *design principles*, not upstream code, scripts or skill bodies. Skills are not a substitute for testing the real UI.

## Agent compatibility

**Codex:** repository skills in `.agents/skills` are supported; explicit invocation uses `$pausio-media-ffmpeg` (when available in the client). [Codex guide](https://learn.chatgpt.com/docs/build-skills).

**Claude Code and other agents:** `SKILL.md` is portable but auto-discovery paths differ by client. `CLAUDE.md` and `AGENTS.md` point to the canonical skill directory. Read skills by path or follow the target agent's documentation for installing/linking reviewed skills into its supported folder (such as `.claude/skills`); do not maintain divergent copies.

**Agents without skill discovery:** open `AGENTS.md` and the matching `.agents/skills/<name>/SKILL.md` manually.

## Validation and tests

`python scripts/validate_skills.py`
`python -m unittest discover -s tests -v`

The validator checks manifest names, descriptions, required coverage and references; CI runs it. This is static structure validation, not a claim that agent execution has been evaluated.

### Acceptance prompts for manual agent evaluations

1. "Samsung A56 VFR video loses A/V sync after two cuts." Expect media skill and test skill, stream probes, reproduction and human listening; no metadata-only fidelity claim.
2. "Remove every pause of 200 ms with no review." Expect natural-editing skill to protect speech, preserve human approval and suggest an opt-in experiment.
3. "Add Italian captions after cutting a two-second pause." Expect subtitles skill to map source timeline to output timeline and flag words crossing cuts.
4. "Enable cloud ASR automatically, download models silently." Expect speech-ai and security skills to demand explicit user opt-in and local-first fallback.
5. "Copy OpenChatCut implementation directly." Expect license check, specific tradeoffs and original adapter recommendation instead of blind copying.

Run these with an agent on real tasks and record whether the expected skill triggered; no automated LLM evaluations are claimed.

## Sources and provenance

Skill structure and progressive-disclosure ideas: [Agent Skills specification](https://agentskills.io/specification), [Anthropic skill-creator examples](https://github.com/anthropics/skills/tree/main/skills/skill-creator), [Codex skill documentation](https://learn.chatgpt.com/docs/build-skills).

Domain references: [FFmpeg filters](https://ffmpeg.org/ffmpeg-filters.html), [Auto-Editor](https://github.com/WyattBlue/auto-editor), [WhisperX](https://github.com/m-bain/whisperX), [Silero VAD](https://github.com/snakers4/silero-vad), [capcut-mcp-kit](https://github.com/simopa/capcut-mcp-kit), [Python packaging](https://packaging.python.org/en/latest/tutorials/packaging-projects/).

**No external SKILL.md bodies, scripts or third-party source code were copied.** Upstream links are research references, not license grants. Adding instructions does not install FFmpeg/ASR backends or change the executable media pipeline.

## Maintenance policy

Keep repo-wide invariants in `AGENTS.md`; domain-specific procedures in individual skills; details in skill `references/`. Update the relevant skill when architecture or implementation changes, run static checks, then evaluate at least one task prompt. Record unsolved issues and unverified media quality, and review changes to agent instructions as carefully as source code.
