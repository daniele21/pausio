---
name: pausio-ui-quality
description: Use when testing, auditing or accepting Pausio Studio changes for browser correctness, accessible states, UX regressions, responsive layouts, loading errors, real media quality, privacy and UI performance.
---

# Studio UI quality and accessibility audit

## Audit order
1. Run existing test suite and `python scripts/validate_skills.py`. Confirm Studio serves packaged HTML/CSS/JS and rejects external/unsafe HTTP POSTs.
2. Test end-to-end HTTP workflow with a generated synthetic MP4: import, analyze, edit, server rejection of invalid plan, explicit approval, render, Range GET and download.
3. In a real browser, verify file import/drop, video preview and scrub, split original/montaggio, restore controls, transcript panel, status/error feedback and disabled/busy states.
4. Keyboard-only pass: full Tab flow; controls show focus; space/arrow shortcut works only outside typing; every input has a label; tab aria state mirrors visible panel.
5. Responsive pass at 1440x900, 1024x768 and 390x844, plus zoom/reduced-motion. No horizontal overflow, clipped button or focus trap.
6. Evaluate actual sound and cut boundaries with a real consented clip; a synthetic CI render alone does not verify editor naturalness or audio continuity.
7. Check privacy and robustness: no remote fonts/scripts, no media paths in logs, localhost-bound server, same-origin POSTs, 2 GB cap, workspace cleanup, errors recoverable.
8. Report issues in severity order with reproduction, expected/actual, viewport and screenshot when available.

## Definition of done
UI controls invoke working endpoints; happy and negative paths covered; all essential editing tasks reachable without mouse; screenshot visual review performed when browser environment is available. Do not mark untested real-footage quality as passed.

See [UI QA matrix](references/qa-matrix.md).
