# Caption emphasis v1 — creator-first, reviewable subtitles

**Branch:** `daniele/social-caption-emphasis-v1` (stacked on `daniele/social-broll-video-v1`).

Pausio keeps the local transcript and FFmpeg/libass renderer. No external model,
browser render engine or cloud transcription is introduced.

## Current behavior

1. Generate captions from Pausio's local transcript, preserving verified word
   timestamps where available. A caption with no word timing does **not**
   invent karaoke timestamps.
2. Choose a caption in Studio's new word-emphasis panel and select up to six
   significant words. Clicking again removes the highlight. The change is a
   versioned `caption.emphasize` event with undo/redo and revision checks.
3. Choose the highlight color. The caption `motion_mode` is independent of
   its visual preset, so changing a font or color does not turn off the
   word-focus effect. Motion modes: none, kinetic phrase pop, real word focus.
4. The output-timed FFmpeg ASS document includes semantic highlights that
   stay visible throughout the caption; when real word timings exist, active
   spoken words are highlighted at their verified intervals. The original
   source->output KEEP mapping remaps selected indices when cuts remove
   individual aligned words.
5. The unrendered Studio overlay displays selected/active words as a
   lightweight editing aid. The FFmpeg preview remains the source of truth
   for final pixels, fonts, timings and layering.

## Typed project contract

- Portable project **v12** extends v11 with `caption.emphasize` and an
  optional per-cue `emphasis_indices` array. The indices are sorted unique
  non-boolean integers within the actual caption word count; maximum six.
- `caption.configure` accepts optional `highlight_color` (uppercase
  `#RRGGBB`) and `motion_mode`. Older project configurations that lack
  these fields normalize to safe defaults. Legacy v1–v11 projects remain
  readable; exporting uses v12.
- Text corrections deliberately discard stale word timestamps and word
  indices. Re-timing a cue discards uncertified ASR word clocks but preserves
  the manual, phrase-level emphasis of unchanged words.
- All project/edit inputs are data, not arbitrary ASS tags, FFmpeg expressions
  or executable code. Text is escaped by the existing caption pipeline.
- ChatGPT/Claude through Pausio MCP can send `caption.emphasize` as an
  ordinary deterministic command; agents cannot approve a final export.

## Inspiration and adoption

- [AutoBroll](https://github.com/andriidrok1/autobroll) for the timing-aware
  editorial caption UX and intentional word accent.
- [FableCut](https://github.com/ronak-create/FableCut) for the style/motion
  separation. Pausio's implementation is native Python + ASS rather than
  adopting another timeline or rendering runtime.

## Verification

- `tests/test_caption_emphasis.py` covers schema replay, selected-word
  validation, undo/redo, old config migration, phrase-level fallback, exact
  word timing and remapping through cuts.
- `tests/browser/test_studio_playwright.py` covers selecting words and
  customizing highlight color without losing word-focus motion.
- CI Python versions 3.11/3.12/3.13, full Playwright studio audit and
  an optional Mac review on an owned real-world short-form recording.

## Intentional limits

This change does not automatically infer which words are important, download
B-roll, add object tracking or create animated keyframes on arbitrary graphic
layers. Such changes should use separate reviewed editing proposals and small,
typed commands. A user-visible cue without verified word timing may still
have **static** color emphasis, not fabricated word-by-word playback.
