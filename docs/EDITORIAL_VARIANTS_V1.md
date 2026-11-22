# Pausio · Three independently editable video variants (v1)

**Status:** implemented on development branch `feat/editorial-style-packs`, PR #89,
not yet merged or included in the historical v0.1.0 wheel.

## What actually works

On **Video FX → Tre regie**, with imported media and a prepared edit timeline:

1. **Crea 3 versioni indipendenti** explicitly forks the current reviewed
   `ProjectTape` into **Authority**, **Visual Explainer**, **Social Impact**.
2. Existing captions, if present, receive the respective
   `minimal`, `word_focus`, and `kinetic` presets as normal undoable
   `caption.style` instructions. No captions are fabricated.
3. Click a saved version to switch Studio to its **own** segments, caption
   style, graphic overlays, scene templates, camera transformations, effects,
   approval status and independent Undo/Redo tail.
4. The standard **Generate preview**, **Conferma montaggio**, **Esporta MP4**
   controls operate on the **active version only**. The download name
   indicates the active style: `pausio-authority.mp4`,
   `pausio-visual-explainer.mp4`, `pausio-social-impact.mp4`.
5. To populate each version with distinct graphics and motion, choose that
   active version, generate the three evidence-based storyboard proposals,
   select the **matching Style Pack**, and apply only desired interventions.
   Proposals become stale on switch, fork or edit; regenerate them.
6. **Esporta 3 versioni** downloads a JSON bundle (all 3 project command
   tapes and current active choice, **no media bytes**).
   **Importa 3 versioni** loads such a bundle after independently importing
   the exact source video; SHA-256, duration and audio presence must match.

**Current limitation:** Pausio renders one selected version at a time.
It does not render three concurrent previews/MP4s or automatically choose
semantic scenes from video footage. Subtitle preset differences do not
alone constitute complete editorial post-production.

## Storage design

`src/pausio/variant_projects.py` owns a strict, pure
`VariantWorkspace` with exactly three independent `ProjectTape` objects.
No new `pausio.project` schema or rendering instruction is introduced:
the existing canonical reducer/preview/export pipelines are reused.

`StudioSessionStore` persists an opt-in local session v3 with:
`project` (the active tape), `variants` (all three tapes),
`transcript` (private, from the original source) and the existing source
media identity. One atomic checkpoint covers active selection and all three
tapes; the backup is retained for crash fallback. For users who haven't
created variants, the original local-session **v2** format remains unchanged.
The historical portable single-project `.pausio.json` remains readable.

Every edit to the active tape also updates its corresponding saved variant
inside that same transaction. Transcription saves preserve the variant
bundle. Switching variants invalidates existing local previews and exports,
rotates the in-memory media token to invalidate stale asynchronous
proposals, and deletes old preview/render caches. A render job must finish
before a variant switch. No source video is overwritten.

`pausio.local-variants` v1 exported JSON includes `active` and
`projects` (exactly three portable `ProjectTape` records).
It includes **reviewed subtitle/caption content and configuration**; users
should treat the JSON as private. It omits raw ASR segments, video bytes,
image/audio asset bytes, raw source paths and generated MP4 files. Existing
media/FX assets must already be accessible locally to re-render them.
Renamed *identical* source files are allowed at bundle import with display
filename rebinding after SHA/duration/audio validation.

Import refuses to replace an already created three-variant session silently:
save/delete or start a separate Studio session first.

## Safety invariants

- No direct mutation of source media, FFmpeg filter expressions or arbitrary
  remote asset URLs; edits are standard typed `ProjectTape` commands.
- Source SHA-256, duration and audio properties are verified on import.
- Malformed bundles, duplicate/missing styles, future schema versions,
  invalid command tapes and inconsistent active tape checkpoints fail closed.
- No arbitrary background worker or Web service is started; Studio stays
  on loopback and all POST endpoints retain existing Origin/client checks.
- Existing v1/v2 local recovery remains compatible.
- After crashing during a write, the previous known-good checkpoint is
  used if the active one is invalid.
- A source replacement or explicit `Elimina dati locali` discards the
  currently associated variants without modifying other files.

## Verification

```bash
python -m unittest discover -s tests -p 'test_variant_projects.py' -v
python -m unittest discover -s tests -p 'test_variant_studio.py' -v
python -m unittest discover -s tests -p 'test_studio.py' -v
python -m unittest discover -s tests/browser -v
```

The browser test uses a synthetic 9-second clip and checks variant switching
and isolation, rather than uploading a user's personal video. Run full
real-Mac preview/export QA, audio alignment and video-source checks before
a release.

## Follow-up features

- Editable motion-graphics components, particularly the count-up metric
  prototype, will become versioned scene templates **after** resolving
  the schema v11–v14 work already staged in PRs #84–#87.
- Richer per-style AI storyboards, exact asset matching and structured
  motion timing; preserve human approvals and strict scene validation.
- Three rendered preview cards and automated multi-export after all three
  timelines have been individually reviewed and explicitly approved.
