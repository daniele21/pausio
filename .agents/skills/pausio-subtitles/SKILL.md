---
name: pausio-subtitles
description: Use for implementing captions, SRT or ASS subtitles, Italian text correction, word alignment, timing, line breaking, burned-in text and 9:16 safe-area design for Reels, TikTok and Shorts.
---

# Captions and subtitle engineering

## Procedure
1. Treat model transcripts as editable drafts. The creator must be able to correct technical names, punctuation and timing without rerunning ASR.
2. Build captions from normalized original-source timestamps, then explicitly remap onto the **output timeline** using approved keep segments. Words spanning cuts must be split, removed or flagged—never silently shifted.
3. Define a pure subtitle segmentation function separate from FFmpeg rendering. Keep readable phrase boundaries; avoid overfilled lines and one-frame flashes.
4. Support accessible contrast, speaker-aware changes and a configurable vertical safe area. Do not hardcode social-platform overlays as invariant: preview on target devices.
5. Keep SRT and ASS export separate from burned-in output. Fonts, effects and template assets require documented licensing/provenance; fallback gracefully when unavailable.
6. Test mixed Italian/English AI terms, abbreviations, accents, quotes, emojis, non-ASCII paths, silence and frame boundary transitions.
7. Require playback review for actual clip readability and sync.

## Definition of done
- Correct text and stable source-to-output time mapping, non-overlapping display windows according to stated policy.
- No unwanted subtitle clipping under expected platform UI overlays.
- ASR is optional: editor-supplied words may drive subtitles independently.

See [subtitle timeline reference](references/subtitle-spec.md).
