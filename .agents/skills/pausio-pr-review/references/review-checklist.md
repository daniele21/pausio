# Pausio PR review checklist

- [ ] Change request and acceptance criteria are clear.
- [ ] No source file overwrite, silent data loss, unmanaged subprocesses or secret exposure.
- [ ] Core modules do not import heavy media/ASR/UI dependencies.
- [ ] Millisecond/half-open interval invariant preserved.
- [ ] Editing remains reviewable and reversible; no silent speech removal.
- [ ] Error paths covered: invalid plan, no audio, missing executable, stale/missing input, existing output.
- [ ] Media behavior covered: VFR/rotation, audio sync, ambience changes, subtitle mapping (when applicable).
- [ ] Private clips kept out of Git; models/downloads/cloud remain opt-in.
- [ ] Third-party code, weights, fonts and audio licensing checked for actual usage.
- [ ] Tests/CI evidence included, unresolved warnings documented.
- [ ] README/ADR/roadmap updated when scope or behavior changes.

Suggested PR body:
**Why:** user impact and reproduction.
**Change:** relevant modules/contracts.
**Tests:** exact commands and outputs.
**Media review:** source type and what was listened to/watched.
**Risks:** compatibility, privacy, licenses, known corner cases.
