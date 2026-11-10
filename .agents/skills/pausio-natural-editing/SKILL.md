---
name: pausio-natural-editing
description: Use for Pausio AI Natural pacing, silence detection decisions, cut thresholds, filler/repeat proposals and human-in-the-loop review. Prioritize preserving meaningful speech and creator style over maximising compression.
---

# AI Natural — editing policy

## Product promise
Remove unnecessary dead air while preserving human rhythm. Do not turn authentic, spontaneous explanations into rushed cuts.

## Procedure
1. Check `docs/ROADMAP.md` and `src/pausio/planner.py`. Current baseline relies on FFmpeg energy-level silence detection; no semantic speech analysis exists yet.
2. Differentiate **evidence** (silence/VAD/ASR timestamps) from **decision** (why a specific cut is proposed) and **approval** (user-accepted or rejected). Do not conflate them.
3. Propose removal only for sufficiently long, high-confidence pauses. Protect onset/offset padding, short interjections and uncertain boundaries; preserve natural breath. Quiet speech must not be deleted without explicit review.
4. Make decisions inspectable: source interval, proposed removed span, evidence type, confidence/uncertainty (when available), editable rationale and original preview.
5. Any change to thresholds requires a before/after comparison on varied clips; do not optimize only for compression ratio.
6. Audio jump cuts require a listening check. Keep raw input immutable and produce a reversible plan.

## Acceptance
- No silent deletion of uncertain speech; meaningful speech loss has highest severity.
- Proposed cuts remain fully reversible and testable independent of any model.
- Measure false cuts, speech boundary clipping, edit acceptance rate and naturalness ratings, not only seconds saved.

See [review and evaluation protocol](references/review-eval.md).
