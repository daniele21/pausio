---
name: pausio-test-engineering
description: Use when adding tests, fixing regressions, modifying GitHub CI, benchmarking edit quality or validating media outputs in Pausio. Cover pure unit tests, synthetic FFmpeg E2E, private real-world golden footage and reproducible quality gates.
---

# Test engineering and reproducibility

## Workflow
1. Write a minimal failing test/reproduction for a bug, or an explicit acceptance criterion for a feature.
2. Place pure-domain tests in `tests/test_domain.py` and policy tests in `tests/test_planner.py`; media/CLI tests in `tests/test_media.py` and `tests/test_cli.py`; synthetic video E2E in `tests/test_e2e.py`.
3. Generate small synthetic fixtures with FFmpeg when possible. Do not commit real personal video/audio, full transcripts, embeddings or weights.
4. Test positive, negative and interrupted paths. Verify non-destructive behavior and predictable errors as well as happy-path output. Specifically test Undo→Redo, branching after Undo, v1→v2 project migration, persisted redo cursor, save failure rollback, corrupted-checkpoint fallback, same-directory locking and explicit removal of private cached media.
5. For timebase changes, test edited boundaries on source frames and audio samples, not only duration/stream metadata.
6. Keep fast deterministic tests in the required CI path. Optional slow ML/golden tests must be opt-in, version-pinned and run on representative macOS/Linux machines.
7. When media quality is subjective, report **what required human video/audio inspection** and do not mark visual or phoneme fidelity as verified by metadata-only tests.

## Commands (existing)
`python -m unittest discover -s tests -v`
`python -m compileall -q src`
`python scripts/validate_skills.py`
`python -m pausio doctor`

## Minimum regression cases
No audio, leading/trailing long silence, fully silent fallback, short protected utterance, overlap/out-of-bounds JSON, input equals output, output collision, paths with spaces, VFR/rotation, mixed stream offsets, export sync and subtitle cut mapping (once implemented).

See [test matrix](references/test-matrix.md).
