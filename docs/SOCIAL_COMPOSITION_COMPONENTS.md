# Pausio — Social composition engine: executable component blueprint

**Status:** proposed architecture, 13 November 2026. Not a shipping feature.
**Purpose:** make high-quality, editable AI-directed social videos achievable by
combining real source video, optional video/image B-roll, motion graphics,
word-accurate captions, sound design and a consistent audio mix. ChatGPT/Claude
Chat provide editorial judgment; Pausio only observes, validates, applies and
renders. This document is an implementation breakdown of
[AGENTIC_EDITING_PLAN.md](AGENTIC_EDITING_PLAN.md), not a second roadmap.

## 1. Current reality — reuse, do not replace

| Already present | Gaps blocking advanced social editing |
|---|---|
| KEEP cuts; source/output mapping, command history and Undo/Redo | Agent can't atomically preview/apply a coordinated set of cuts/effects |
| Source-bound camera zoom/slide/pulse, limited dip-black transitions | No generic bounded transform/opacity keyframes or video crossfades |
| Headline/stat/code/tip graphics rendered with ASS | No reusable data-driven graphic layouts, stacking order, selection/resize in live preview |
| Image PIP (max 4), output-time placement and a visible B-roll lane | No **video B-roll** clips with source trim/crop/full-screen/PIP/split layouts |
| Source speech, imported music/FX and gain/mute with FFmpeg | No fades, music ducking under voice, measured LUFS or multi-lane organization |
| Caption styles, verified word focus and actual FFmpeg output | No intentional caption emphasis coordinated with other foreground layers/safe areas |
| Local MCP (17 tools after PR #77) to read metadata and edit/import small assets | No image/audio observations returned to chat, full asset browser, command batch |
| Cached short/full FFmpeg preview | Slow repeated feedback for later/layer-heavy effects; no agent visual inspection |

### Hard constraints

- **One canonical project:** `ProjectTape` + typed event history; UI, MCP and
  CLI share validators, assets, time mapping and renderer.
- **One media engine:** FFmpeg/libass/ffprobe; Python stdlib. No mandatory
  Node/Remotion, Rust/EffectCraft, GPU model, browser automation engine or
  image-generation API embedded in Pausio.
- **Agents plan, humans approve:** user controls source access, licenses,
  proposed modifications and final export. Unknown assets/filters fail closed.
- **No new monoliths:** `studio.py` ~1,432 lines, `project_commands.py` ~858,
  `media.py` ~599, `app.js` ~2,084 and `styles.css` ~84 kB. Keep new
  responsibilities in focused modules; add only slim orchestration wires.
- **No accidental cloud:** sharing private frames or audio through an MCP tunnel
  requires an explicit per-project opt-in. Transcript and source bytes never
  enter the portable JSON.

## 2. Component graph

```text
ChatGPT / Claude Chat (creative director)
  |  observe frame/audio/transcript; propose scene beats + assets
  v
MCP adapter (trust, scope, bounds, status)
  |
  +-- Observation service <--- canonical project, media and FFmpeg
  +-- Asset catalog / import / rights
  +-- Proposal validator and atomic command batch
  |
Studio UI <------------------------> typed ProjectTape (single truth)
  |                                   |
  | timeline + inspector + preview    v
  +-------------------------> Composition compiler
                                  |
                source KEEP / transforms / footage B-roll
                images / graphics / captions / audio buses
                                  |
                    FFmpeg preview / export
                                  |
                       QA observations -> chat
                                  |
                     Human review -> final MP4
```

## 3. Component ownership and contracts

All names below are *proposed*, not existing modules; adapt incrementally
around the already implemented validators. No new top-level framework.

| Component (new or extracted module) | Responsibility | Interface / no duplication |
|---|---|---|
| **C1 — `timeline_projection.py`** | Source↔output ms mapping, cut intersections, clock conversion and event anchoring | Pure functions; invoked by reducer, FFmpeg compiler, B-roll UI and MCP; reuse existing mapping code instead of rewriting it |
| **C2 — `layer_events.py`** | Validated video B-roll, image, graphics and captions layer descriptors; z-order, positions, duration, crop, opacity | Canonical typed commands extending `ProjectTape`. No parallel browser-only layer state |
| **C3 — `motion_presets.py`** | Bounded, versioned keyframes for x/y, scale and opacity; easing/hold; preset parameters | Pure, deterministic keyframe sampler; FFmpeg expressions constructed exclusively from allowlisted primitives |
| **C4 — `video_broll.py`** | Import/probe original clips, trim section, mute source clip audio by default, PIP/full/split placement and crop | Reuse Studio content-addressed media importer; no raw input URLs, new codec stack or separate composition path |
| **C5 — `graphic_templates.py`** | Small reusable title/stat/tip/terminal/checklist/callout designs, typography, positions, entrances/exits | Extend `graphic_overlays.py` + libass; templates are versioned data, not arbitrary HTML/SVG/JS |
| **C6 — `audio_timeline.py`** | Speech/music/riser/SFX lanes, trim, fade, gain, mute, ducking and optional source clip sound | Reuse audio asset hash and existing mixer; FFmpeg built-in `afade`, `sidechaincompress`, `amix`; explicit lane semantics |
| **C7 — `loudness_report.py`** | Actual integrated LUFS/LRA/dBTP measurements, clipping risk and optional 2-pass normalization | FFmpeg `loudnorm`/ebur128; result measurements, not waveform-derived assumptions |
| **C8 — `media_observation.py`** | Frame at source/output time, contact sheet, short audio listening sample, actual render diagnostics | Read-only, FFmpeg-extracted, SHA/revision bound, request budgets + consent. MCP image/audio content where supported; separate image resource fallback |
| **C9 — `edit_transactions.py`** | Validate proposed batch, preview diff/affected ranges, apply all-or-nothing, one Undo unit, idempotency/revision | Wrap canonical command reducer/persistence; no agent-specific edit logic |
| **C10 — `render_composition.py`** | Compile validated layers, keyframes and A/V buses into **one** FFmpeg graph for preview and final | Extract internals from `media.py` incrementally. Explicit render profile; same overlay order for both outputs |
| **C11 — `mcp_editing_tools.py`** | Expose template catalog, frame/audio observations, inventory, batch, preflight and preview results to agents | `mcp_tool_catalog.py` remains schema registry; no generic shell/URL/FFmpeg tool |
| **C12 — focused UI modules** | Asset browser; 4 visible timeline lanes; preview drag/resize/keyframe controls; review before/after | Add `broll_video_ui.js`, `layer_timeline_ui.js`, `audio_timeline_ui.js`, `proposal_review_ui.js`, rather than grow `app.js` |

### Canonical timeline rules

The existing image/audio placement is **output-timed**, while camera zoom and
many graphic cards are **source-segment anchored**. This mismatch previously
made image positions hard to understand.

1. Preserve the current event formats and migrate explicitly where needed.
2. Every new event declares `timebase: "output"` or `"source"`; never infer
   timebase from a raw number. A speech-following annotation can reference a
   stable segment/caption ID; a soundtrack or independent clip can anchor to
   output milliseconds.
3. Map source events to output after KEEP, split only visually across cuts;
   neither duplicate one command nor silently migrate effects onto a different
   phrase. Allow explicit retiming when the cut changes.
4. Composition order: immutable original video + KEEP → camera/motion →
   video B-roll → image B-roll → graphic templates → captions → audio mixing
   → optional normalization. A fixed z-order default can be overridden only
   by a *validated* layer value; captions remain visible and checkable.
5. At playback, the same ordered timeline drives UI lane positions, selected
   time-range preview and full export. A DOM overlay is never the source of
   truth for pixel-perfect output.

### Minimal bounded layer-event sketch — DESIGN ONLY

```json
{
  "type": "layer.video.add",
  "payload": {
    "layer": {
      "id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "asset_sha256": "<sha256-of-imported-clip>",
      "timebase": "output",
      "start_ms": 18000,
      "duration_ms": 3200,
      "source_in_ms": 1500,
      "source_duration_ms": 3200,
      "layout": "full",
      "source_audio": "mute",
      "z_index": 20,
      "transform": {"x_pct": 50, "y_pct": 50, "scale_pct": 100},
      "keyframes": [
        {"at_ms": 0, "scale_pct": 100, "opacity_pct": 100},
        {"at_ms": 3200, "scale_pct": 106, "opacity_pct": 100}
      ]
    }
  }
}
```

This is **not** an already accepted command, or a full schema proposal. Define
exact fields/limits against real fixtures and increment the project format
version with backward import tests. Keyframes v1: maximum eight per layer,
integer output-relative ms, bounded scale/position/opacity, interpolation
`hold|linear|ease_in_out`. No user-supplied FFmpeg expressions or scripts.
No nesting/compositing trees until a demonstrable need emerges.

## 4. Actual editable features, not generic effects

### Layer/overlay primitives (first useful set)

- **Video B-roll**: local clip (MP4/MOV etc.), in/out, full screen, PIP or
  side-by-side; original voice remains audible under cutaway; optional use
  of B-roll sound. A project asset can appear at several moments.
- **Image overlay**: same layouts, source proof badge/label, rounded card
  background when feasible, subtle fade/pop/slide, mask only after basic
  placement is reliable.
- **Text/design**: headline, exact statistic with source note, terminal/code,
  numbered steps, label/callout, screenshot mock **clearly illustrative**.
  Template version + semantic role, not one CSS style copied into export.
- **Motion**: punch, slow push, ease, pulse/sweep (already available);
  additionally validated scale/position/opacity keyframes, limited
  dissolve and intentional whip/push *only if real samples prove legible*.
  No random FX insertion quota.
- **Captions**: phrase/verified-word alignment (already), sparse semantic
  highlights, captions over video B-roll, conflict detection with other text.
- **Audio design**: separate voice, music and SFX/riser lanes; fades and
  ducking under speech; measured true peak and integrated loudness; master
  volume finalization. No copying unlicensed songs from other creators.

### Asset choice order

1. The user's own currently available clip/screenshot/track.
2. Explicitly imported and licensed media from a **user-configured** library.
3. A newly created *illustrative* still or sound from the active chat provider
   when the user authorized generation and real bytes are delivered; cannot
   infer ChatGPT can attach files to MCP.
4. Optional remote stock with its own authenticated connector, verified
   license/attribution, and explicit user approval; **no unrestricted URL tool**.
5. **No asset** when the spoken content is clearer on camera.

Record origin/license declaration, asset SHA, selected interval, and purpose
in agent proposal metadata. A model-generated mock permission dialog must
never be represented as a screenshot of a real research finding.

## 5. Agent director contract

Pausio is not the semantic director. ChatGPT writes a bounded
`editing_proposal` grounded by observed source/transcript/caption intervals:

- **Why**: `evidence|explain|emphasize|pace|emotion|clarify`; freeform short
  rationale and associated exact source words/timestamps.
- **What**: existing asset ref, generated asset awaiting import, or predefined
  template/effect ID and version. No unrecognized effect names.
- **Where**: timebase, relevant segment ID and start/duration; safe default
  position plus optional explicit confidence/uncertainty.
- **How**: validated event list, font/style, transform keyframes, volume/fades,
  overlay order and expected changed ranges.
- **Review**: source/edited frame, audio observation, warnings for occlusion,
  missing assets/rights or A/V sync; option to skip a proposed change.

Example: on the exact "oltre 1.300 segreti" phrase, the model chooses one stat
template; on the "don't ask again" explanation, prefers a user-provided UI
image over generic footage; during the practical advice, shows a short
verified checklist; the closing line returns to the person's face. **An
empty proposal is valid.**

Do not hardcode a "virality score", minimum effects per minute, or impersonate
a creator's style. Profiles (`clean_tech`, `educational`, `dynamic_social`,
`custom`) are *constraint sets* (density, emphasis, animation duration,
safe areas, audio ceiling), not new rendering implementations.

## 6. Deliverable slices and parallel execution

| Slice | First thing the user can actually do | Work that can run alongside |
|---|---|---|
| **S0 — shared contracts and observations** | GPT obtains actual source/rendered frames plus bounded audio excerpts, with explicit consent and source/output timestamps; validates a sample proposal without editing | Extract time mapping from existing code; define image/audio MCP result transport and privacy gates |
| **S1 — layered visual B-roll** | Put one real video cutaway over spoken narration, trim/crop/move it and preview the exact 5s before/after | Build a minimal 4-lane UI on the existing timeline; add provenance/relink tests |
| **S2 — audio and visual polish** | Fade music in/out, duck voice-relative music, add a riser, animate one illustrated card with basic keyframes | Implement template catalog and LUFS measurement adapters against recorded fixtures |
| **S3 — agent-coordinated edit batch** | GPT proposes 3–5 coordinated edits, validates/commits them as **one undoable batch**, previews, inspects and revises | Design proposal-review UI, diagnostics and selective accept/skip controls |
| **S4 — creator-ready workflow** | Source video → storyboard → selected asset → preview observations → approve in Studio → reproducible MP4, with no shell/manual JSON editing | Cross-browser/Mac/A56 audio and visual QA, profile usability tests |

**Order dependencies:** S0's contract/timebase before S1/S3 merge. After
freezing that contract, source-media ingest and FFmpeg video overlay can be
implemented in parallel with timeline UI; audio compiler and template
catalog in parallel; MCP and browser UI consume the *same* validators.
Avoid two branches simultaneously rewriting `studio.py`, `project_commands.py`,
`media.py`, `app.js` or `styles.css`. Prefer small PRs with one
user-visible capability and merge gates, then immediately rebase consumers.

### First P0 implementation tickets (small, testable)

1. **OBS-01:** source and edited frame capture + contact sheet; at most eight
   540px frames per request, whitelisted timecodes, hash/revision metadata,
   no implicit remote sharing. Test FFmpeg timing on real cut boundaries.
2. **TIME-01:** extract pure source/output mapping helpers without changing
   persisted event semantics. Unit tests for cut intersections and the B-roll
   markers from the current Studio.
3. **LAY-01:** typed video-layer schema and safe asset binding. Reject unknown
   fields/codec/overlong durations, stale revision, missing media and
   unsupported project version.
4. **VID-01:** render a validated imported clip as full-screen/PIP with
   underlying original narration, same FFmpeg graph in preview and export.
5. **UI-01:** video B-roll lane, select/reposition/trim + contextual inspector,
   exactly one corresponding typed command per change.
6. **AUD-01:** explicit music/SFX/voice lanes + bounded fades, measured ducking
   and a true-peak diagnostic; no new audio framework.
7. **TMP-01:** three small data-driven graphic templates (stat, terminal,
   2-step checklist), plus linear/ease keyframes and social-safe placement.
8. **TXN-01:** dry-run errors + atomic, idempotent source-bound batch, one Undo;
   no partial success or automatic approval.
9. **MCP-01:** tool parity for observation, template catalog, batch and
   preview; bounded media responses through the connected ChatGPT tunnel.
10. **QA-01:** synthetic 9:16 FFmpeg fixtures + Chromium Playwright + 1–2
    actual A56 videos, checking subtitle/face collision, sound and timebase.

## 7. Definition of done — one video, not 100 effects

Use a short Italian talking-head explaining the GitHub AI-agent credentials
risk as the realistic acceptance scenario:

- Hook preserves the original speaker and complete intelligible words.
- One stat ("oltre 1.300") appears at the actual spoken claim, with honest
  presentation and no unverified source details.
- A separate imported visual *illustrates* a permission selection while the
  voice continues; trim/pan/crop and undo it from Studio **or** ChatGPT.
- One useful terminal/checklist card; sparing verified word-focus captions,
  no face/caption occlusion and no gratuitous transitions.
- Low bed music + optional riser; actual voice intelligibility and measured
  LUFS/true peak, rather than assumed safe gains.
- GPT sees a true FFmpeg frame at/after each changed point (with consent),
  reads enough audio to evaluate balance if the connected client supports it,
  and revises the project. No claims of visual success from job status alone.
- Same source hash, exact project revision, reproducible preview/final
  composition. Undo/redo, restart persistence, JSON round-trip and missing
  asset errors work.
- Python matrix, FFmpeg synthetic E2E, Playwright 320/390/1440, Safari/Mac
  spot-check, A56 recording review and security negatives pass. Manual final
  approval remains mandatory; the final MP4 is retrieved through Studio.
- Track quality with creator review and eventual real analytics; never assert
  an effect is successful based on popularity of an inspiration repository.

## 8. Deliberately deferred

3D cameras, arbitrary compositing expressions, shader/node editor, untrusted
user SVG/HTML, masks/rotoscoping, huge multi-layer graphs, cloud media crawler,
new ML scene detectors, automatic publishing, source video upload from
ChatGPT without explicit consent, auto-accepted stock licensing, remote
inference API keys, invasive face tracking and a second rendering frontend.

## References and architectural records

- Existing contract: [AGENTIC_EDITING_PLAN.md](AGENTIC_EDITING_PLAN.md)
  and [PROJECT_FORMAT.md](PROJECT_FORMAT.md)
- Design reference: [SOCIAL_EDITOR_RESEARCH.md](SOCIAL_EDITOR_RESEARCH.md)
- Engineering: [STUDIO_FRONTEND_MODULES.md](STUDIO_FRONTEND_MODULES.md),
  [DECISIONS.md](DECISIONS.md)
- Official FFmpeg filters: https://ffmpeg.org/ffmpeg-filters.html
- AutoBroll: https://github.com/andriidrok1/autobroll
- EffectCraft: https://github.com/storytold/effectcraft

Use ideas as product design inputs; verify third-party licenses before copying
code, effects, media or graphics.
