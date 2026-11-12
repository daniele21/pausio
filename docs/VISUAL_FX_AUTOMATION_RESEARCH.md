# Pausio visual FX — open-source research and configurable automation

Status: **design/contract only**. Reviewed on 12 November 2026. No zoom, tracking or automatic transition engine is shipped by this change. Start from [Visual Motion Effects Plan](VISUAL_MOTION_EFFECTS_PLAN.md), WP2b. The user's creative goal is short natural talking-head videos, not high-frequency template effects.

## Repository research — actionable implementation patterns

| Repository | Concrete verified implementation | Best Pausio adaptation | Caveat |
| --- | --- | --- | --- |
| [WyattBlue/auto-editor](https://github.com/WyattBlue/auto-editor) / [actions](https://auto-editor.com/docs/actions) | A timeline is divided into labelled classes (inactive, normal and 2–255 other classes); classes map to actions (cut, zoom, speed, volume). Keyframe/easing syntax; transition option has minimum-cut filter, default 1s. Repo license Unlicense. | **Rule layer**: detect signals -> label candidate regions -> choose a safe effect; transition eligibility gates. Keep effect types in typed events, not string commands. | The semantics/classes are inspiration; our UI/history and preview/render remain authoritative. Avoid zoom-on-motion as a universal rule. |
| [louisedesadeleer/add-zooms](https://github.com/louisedesadeleer/add-zooms) / [scripts/zoom_lib.py](https://github.com/louisedesadeleer/add-zooms/blob/main/scripts/zoom_lib.py) | Three zoom moves: punch (instant jump), ratchet (progressive steps), Ken Burns (long smooth push). Turns event list into keyframes and a **piecewise zoom envelope**, combining overlaps with max zoom. MIT. | **Effect primitives**: punch, slow_push, ratchet; explicit keyframes anchored to exact ASR start or cut timestamps. Resolve overlapping suggestions deterministically. | Their envelope is one global zoom curve, not Pausio's KEEP/source timeline. Do not copy the frame-resolution or filter builder verbatim; respect VFR/cut discontinuities. |
| [georgilusikov/talking-head-jumpcut-zoom](https://github.com/georgilusikov/talking-head-jumpcut-zoom) | Describes a 1.00→1.08→1.16 step ladder, eye-line/blur/pose gates and independent output QC. Repo includes director-review code sampling frames and face position. MIT. | **Natural preset**: modest zoom ladder and visual QC flags before suggesting effects. | Small experimental project; described AI dramaturgy needs actual dataset/real-world validation. Do not advertise robust automatic creative judgment based solely on readme. |
| [idopinto/ai-video-reframing](https://github.com/idopinto/ai-video-reframing) / [planner](https://github.com/idopinto/ai-video-reframing/blob/main/smartcrop/plan.py) / [render](https://github.com/idopinto/ai-video-reframing/blob/main/smartcrop/render.py) | Tracks subject & face on sampled frames; selects one track, holds near-stationary crop, uses smoothing, renders x(t) through FFmpeg crop/sendcmd. MIT repository. | **Face reframe**: track/hold/dead-zone/smooth/fallback to center, output a deterministic sparse trajectory that can be manually edited. | Current example only moves x (full-height window), doesn't detect scene cuts or multiple active speakers; YOLO/Ultralytics dependencies have **AGPL/enterprise licensing implications** independently of the repo license. Do not bundle without commercial licensing review. |
| [andriidrok1/autobroll](https://github.com/andriidrok1/autobroll) / [timeline](https://github.com/andriidrok1/autobroll/blob/main/src/timeline.ts) | Per-clip source-relative keyframe tuple {t,scale,x,y}; smoothstep interpolation; separate render composition; editor provides undo/redo and keeps manual edits. | **Editor UX + data model**: a real FX lane and inspector, keyframes in source time, review of auto suggestions without overwriting manual edits. | It uses Remotion/React: Pausio already uses Python/FFmpeg. Remotion licensing is distinct from the open repo; avoid runtime dependency for MVP. |
| [Breakthrough/PySceneDetect](https://github.com/Breakthrough/PySceneDetect) | Dedicated cut/scene-transition detector with configurable thresholds and scene lengths; BSD-3-Clause. | **Input observation** for B-roll and scene changes; not an automatic artistic transition decision. | False cuts on camera motion/flashes need gating; optional module, not necessary for MVP. |
| [prismosoft/clipcast](https://github.com/prismosoft/clipcast) | Exposes tracking controls such as detection stride, dead zone, follow smoothness, jitter threshold and scene reset. | **Advanced configuration** of subject tracking, shown only behind Advanced mode and tested with real footage. | Larger feature scope and models requiring optional tokens; no remote inference needed for Pausio. |

License references: auto-editor Unlicense; add-zooms / talking-head-jumpcut-zoom / ai-video-reframing MIT; PySceneDetect BSD-3-Clause; [Ultralytics official licensing](https://www.ultralytics.com/license) and [Remotion licensing](https://www.remotion.dev/docs/license/pricing). **The license of a repository does not override the licenses of its dependencies, weights or media.** Review versions and transitive licenses before reuse.

## Synthesis — architecture for Pausio

```text
Existing Pausio raw source and KEEP/cut plan
    ↓
Cheap observations (all source-time, media SHA bound)
  cut boundaries / KEEP durations / ASR words / prosody / scene cuts
    + optional offline face boxes & subject motion
    + optional user or ChatGPT/Claude semantic markers
    ↓
Candidate producers (pure, independent and feature-gated)
  cut_punch | phrase_push | emphasis_punch | optional ratchet
  contextual_transition | subject_reframe
    ↓
Signal availability & confidence gates
  [no audio = no audio claim] [unknown face = conservative center]
    ↓
Deterministic priority/scoring & interval conflict resolver
  apply preset budgets, min spacing, cut protection, manual rejection memory
    ↓
PROPOSAL (not project edit, not render approval)
  exact start/end ms, source/KEEP IDs, trigger evidence, score, preset version
    ↓
Review UI: compare / accept one / accept selected / reject / adjust
    ↓
Typed command service + undo/redo + source hash + project revision
    ↓
Pausio-owned FFmpeg preview + export
```

This preserves ChatGPT/Claude Chat as the **creative brain** if available and authorized. Pausio's local scoring merely estimates where changes are technically plausible. It must not invent semantics ("this is the viral moment") or read private transcripts/frames without user consent to share them externally.

### Automatic suggestions must be meaningfully different from auto-application

- `off`: no proposal generation.
- `suggest` (default): generate an ephemeral previewable list; project remains unchanged until explicitly accepted. Can accept all, selected or one; ignore/reject stored against proposal signature.
- `preview_auto`: render a temporary *unapproved* before/after draft from candidate instructions **without committing them**. Bounded FFmpeg jobs and temp storage; do not silently mark project approved or export.
- Never provide a mode that silently rewrites the editable project, exports, posts, or overrides manual edits. In the future the chat client may propose typed edits, not bypass approval.

Profile selection and execution mode are separate. Profiles `naturale`, `educativo`, `dinamico`, `personalizzato` are versioned. `personalizzato` starts as a copy of `educativo`; users may override bounded fields in a per-project settings command, without mutating the bundled profile JSON. The default for talking-head videos is **naturale**.

## Candidate signal and scoring contract

Candidate = `{candidate_id, kind, segment_id, source_start_ms, source_end_ms, base_revision, media_sha256, score_0_100, evidence: [{kind,timestamp_ms,value,provenance}], effect_payload, preset_id, preset_version}`.

1. Generate candidates only on existing KEEP spans. Cut boundaries are strong candidates for **instant punch shifts**; do not schedule slow motion across a removed gap.
2. ASR word/phrase boundaries are *timing opportunities*, not proof of emotional significance. Prosody uses local energy/onset changes with confidence; prefer clear words over silence. If word timing unavailable, omit the feature; do not fabricate word-level evidence.
3. Face stability protects framing. For candidates with missing detections, either use center with lower confidence and a conservative zoom, or skip when safe framing cannot be established. Tracking is **optional** and disabled until a license-safe local adapter exists.
4. Scene change can make a dissolve *eligible* only with sufficient source handles and no speech discontinuity. It does not compel a dissolve.
5. Agent/user emphasis markers are an **explicit optional input** from ChatGPT/Claude Chat or manual editing, not silently synthesized by Pausio. Treat them as untrusted suggestion data and validate source-binding.
6. Normalize each available signal to `[0,1]`, combine preset weights, renormalize weights only over actually available signals, then add deterministic bonuses/penalties for visual/audio safety. Missing signals are listed in the proposal; they are not assumed to be zero-quality observations.
7. Resolve using stable priority + weighted interval scheduling/non-max suppression: score descending, then source ms ascending, then stable candidate ID, with density caps and min spacing. Allow manual forced choices to override other proposals **within bounds**; rejected IDs remain rejected when the same source/preset/algorithm is regenerated.
8. For a segment with no trustworthy evidence, return an empty proposal set; no random effects to fill a target quota.

Important: proposed weights in `configs/visual_fx_presets_v1.json` are **starting hypotheses**, not learned scores. Validate against manually curated real clips. This is deterministic scoring, not trained attention prediction.

## Configurable parameters and UI

Initial UI mock (not yet implemented):

```text
Effetti automatici                         [ Off | Suggerisci | Preview auto ]
Stile                                      [ Naturale ▼ ]
[ ] Zoom rapidi          [✓] Zoom lenti      [ ] Transizioni
Intensità zoom                         1.08x — 1.16x
Massimo effetti al minuto                  3
Distanza minima fra effetti                8.0 s
Sfumature/dissolvenze                      Off
[ Avanzate ▾ ] Face-safe crop, triggers, pause/cut guard, analysis quality
[ Analizza e proponi ]  [ Confronta prima/dopo ] [ Accetta selezionati ]
```

Advanced groups (collapsible): density/min spacing, candidate types & weights, zoom peak and hold, keyframe/easing, transition kinds and min source handles, protected intro/CTA/text regions, face tracking window and confidence, agent/manual semantic markers, local CPU/runtime limits. Preview shows *why* each suggestion was made. Avoid presenting irrelevant controls on mobile.

Expected UX: auto suggestions appear on a **Video FX lane** separate from cuts and captions, in a neutral pending appearance. Greenlight requires explicit acceptance; once accepted edits use the canonical command tape, can be undone, exported and reimported, including accepted preset ID/version and exact resolved numerical keyframes. Re-running Auto FX must preserve manual adjustments and accepted/rejected decisions by default; optionally show an explicit replacement diff.

## Preset design (initial hypotheses)

See [validated preset contract](../configs/visual_fx_presets_v1.json), designed for single-talking-head 9:16 videos. The values are not guarantees and require real-footage testing.

| Preset | Target | Max events/min | Min gap | Punch peak | Slow push | Transitions |
| --- | --- | ---: | ---: | --- | --- | --- |
| **Naturale** (default) | Calm walking/talking explainers, minimal distraction | 3 | 8s | 1.08–1.16× | ≤1.10× / 2.6s | Hard cuts |
| **Educativo** | Educational listicles/data with captions and occasional overlay | 6 | 4.5s | 1.10–1.22× | ≤1.13× / 2.2s | Contextual dissolve only, ≤1/min |
| **Dinamico** (opt-in) | High-energy short social clips | 10 | 2.8s | 1.12–1.28× | ≤1.16× / 1.8s | Contextual dissolve/dip only, ≤2/min |
| **Personalizzato** | User-editable copy of Educativo | 6 | 4.5s | 1.10–1.22× | ≤1.13× / 2.2s | Custom bounded policies |

Any preset is a **maximum**, not a minimum: 0 effects on a calm 30-second clip is valid. Density guards apply across effect types; transition max is an additional cap. Auto FX always needs evidence; avoid zoom over faces cut by 9:16 social safe areas.

## Implementation phases

1. **AF0 — Config contract and test fixtures (this PR)**: research, bounded/versioned JSON presets + JSON Schema + CI validation, no effect runtime.
2. **AF1 — Zoom engine**: deterministic candidate producers from source cut map and available word timestamps, simple selection/preset policies, typed `video.transform.*` commands, FFmpeg crop/zoom, Playwright FX lane + preview. Do not introduce face dependency yet.
3. **AF2 — Prosody + scene gates**: optional speech energy/onset analysis, PySceneDetect cut observations, guard accidental transitions/word overlaps; independent artifact/cache by media SHA+analysis version.
4. **AF3 — Face reframe**: adapter interface with license-cleared, optional local detector/tracker; sparse frame sample, dead zone, smoothing, face safe area, explicit fallback. **Do not bundle Ultralytics YOLO or Remotion without review.**
5. **AF4 — Agent MCP**: `visual_fx.list_profiles`, `visual_fx.propose`, `visual_fx.inspect_candidates`, `visual_fx.preview`, `visual_fx.apply_approved` as project-scoped capabilities after auth/permissions; no user-data remote uploads by default.

Tests per phase: no audio/transcript, no face, static clip, dense cut timeline, reimport after manual edit, repeated determinism, huge/untrusted config rejected, VFR/rotation, high-res/low-res, no valid transition handles, 540×960 vs 1080×1920 frame comparisons, actual listening and face crop checks.

## Security, performance and license gate

- Config is *data*, never arbitrary FFmpeg expression, shell, Python code, remote media URL or imported upstream skill. Strict types/allowlists/ranges prevent unbounded zoom/effect counts; guard every MCP request separately.
- Cache pure observations by source fingerprint, model/version, input settings and hash, not plaintext private transcript. No auto-dispatched expensive renders on repeated requests. Queue bounded, cancel/reuse revision-aware previews.
- Third-party dependencies are optional behind explicit review; keep using the existing Pausio FFmpeg pipeline and Python stdlib initially. Source repositories are **ideas**, not automatic dependencies. No user media/frames in git.
- Face/object detectors may include licensing/redistribution obligations independent of the top-level MIT repository (notably Ultralytics AGPL). Remotion has eligibility-based licensing.
- Keep local Studio on loopback and MCP stdio local until security issue #38 for a hosted gateway is resolved.

## Acceptance for deciding if automation works

Pilot 5–10 clips with diverse content (calm explanation, energetic hook, 3-step list, B-roll scene change, no-audio reference, landscape source, VFR phone with head movement); preserve clips outside the public repo.
- **Zero** auto-generated effects with unsupported source/segment references, clipped face or changed source bytes.
- **Zero** silent overwrites of manually edited FX.
- Each proposed effect includes evidence and exact source-time, with accepted edit reproducible from JSON.
- Compare accepted suggestion rate, number removed for distraction, zoom framing correctness, subtitle occlusion, perceived rhythm, render time and edit-time savings vs manual baseline.
- Tune per preset from real creator feedback; no claims of improved view count or retention without controlled measurement.
