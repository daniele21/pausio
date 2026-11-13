# Social video direction for Pausio — practical reference map

This is an implementation reference, NOT a claim that a creator's specific
effects cause engagement or that we have frame-by-frame studied their videos.

## What to learn from open-source projects

| Reference | Relevant principle | Pausio decision |
|---|---|---|
| [ArtCraft](https://github.com/storytold/artcraft), [EffectCraft](https://github.com/storytold/effectcraft), [FilmCraft](https://github.com/storytold/filmcraft) | Scene/layer compositing, effects and keyframes, scriptable commands, clear timeline | Borrow concepts, **not** a second native Rust/video engine |
| [AutoBroll](https://github.com/andriidrok1/autobroll) (MIT) | Own footage before stock, AI selects only meaningful B-roll, subtle caption emphasis, face-aware layout, editable keyframes, MCP frame observation | Ground B-roll against actual spoken idea and source timeline; same reducer/FFmpeg |
| [MakeMyClip](https://github.com/MakeMyClip/editor) (MIT) | Word-accurate cut validation, pre/post frames, non-destructive JSON timeline | Add an agent-visible cut QA report; preserve individual undo and media binding |
| [Vedit](https://github.com/onetwothird/vedit) | Explainable short-form presets, selective zooms to mask jump cuts, export interop | Different editorial profiles, without arbitrary fixed zoom frequency |
| [Cutaway](https://github.com/S07K/cutaway) (MIT) | Discoverable multitrack timeline, one scene for preview/export, keyframes | Extend existing Pausio timeline and FFmpeg, not another frontend stack |

Licenses of source code, models, templates, stock images, logos, fonts and music
are separate. Don't import any reference project as a dependency by default.

## Creative goal

A good short-form explainer is not "more zooms per minute": it **maintains
attention while delivering the promised insight**. Simone Rizzo's public
statement about content value and consistency rather than effects as the main
drivers is a useful editorial principle, not proof of a particular effect's
performance. Source: https://it.linkedin.com/posts/simonerizzo98_ti-svelo-il-segreto-per-crescere-sui-social-activity-7260596687671283712-ccP7

The *user's* voice and brand win over trying to replicate an identifiable
creator. Defaults: calm but engaging, informative, clean, naturally spoken.

### Minimal director's beat sheet

1. **Hook** (first seconds): expose the risk/result in source speech; if useful
   one informative title and a small movement. No fabricated claims.
2. **Evidence**: when a specific number/source is spoken, show concise, legible
   evidence, not a generic decoration. For the Github password story, the
   existing line "oltre 1300" supports a bounded stat overlay.
3. **Mechanism**: a *relevant* visual, e.g., a locally generated mock permission
   dialog labeled as illustration, with no real secrets, might illustrate the
   "don't ask again" mechanism; do not replace real UI screenshots with a
   fabricated screenshot presented as authentic evidence.
4. **Practical payoff**: text cards for distinct useful checks, code example
   only if validated and exactly relevant; allow the human face to remain
   visible for high-trust phrases.
5. **Close**: one takeaway, avoid cosmetic transitions that muddy the message.

### Every proposed asset/effect carries the same intent

- `purpose`: evidence / explain / emphasize / pace / emotion / clarify
- `anchor`: original transcript quote + source segment / output timestamp
- `asset_choice`: user-owned first, then explicitly licensed, then generation
  of a *clearly illustrative* original; no automatic external downloads
- `rationale`: what improves comprehension or pacing; may be "none"
- `settings`: duration, crop, scale, position, entrance/exit, gain and fades
- `checks`: face/safe-area occlusion, caption collision, normalized loudness,
  audio intelligibility, actual preview screenshots and media rights

Do **not** hardcode a universal viral score or a minimum FX count. Prefer
small numbers of purposeful shots, explainable edits and alternation between
talking head, text card and useful B-roll. An agent must be able to omit all
assets if none is necessary.

## Dependency-light engineering milestones

**P1 — asset reachability**: list project-bound images/audio, reuse them with
source IDs, accept optional small user-provided/generated base64 files via
existing Studio import validation and the same typed command reducer. Source
files stay local, upload is explicit, no arbitrary fetch URLs or shell.

**P2 — see & hear**: read-only, bounded frame/storyboard and audio excerpts,
with explicit user consent before exposing media to the chat provider. Validate
media SHA and source/output time. No image-to-text LLM API inside Pausio.

**P3 — richer creation & asset libraries**: discover local licensed assets and
metadata, optional external stock provider only through an explicit configured
connector, deterministic full-screen video B-roll, layered time-based canvas,
small reusable graphic templates, audio fades/ducking. Persist sources and
licenses. Avoid embedded browser or another renderer.

**P4 — editorial planning/review**: one proposal manifest with beats, optional
media candidates, intentions and evidence; simulate/edit atomically, inspect
before/after with frame/audio observations, approve manually, then export.
Record watch-time and completion-rate metrics only when real platform analytics
are available; no false virality promise.

## Core invariants

- A single native Python reducer, one FFmpeg backend, local-first workspace.
- No new heavy runtime package or second independent edit project.
- UI and MCP share identical asset references, timestamps and command schema.
- Never silently change approval, publish, upload or download remote material.
- Keep media/import/observation/edit modules separately testable (~one scope/file).
- MCP discovery and authenticated ChatGPT tunnel do not grant extra filesystem
  permissions; generated media requires user authorization and provenance.
