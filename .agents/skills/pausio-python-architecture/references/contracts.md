# Core boundaries & edit-plan contracts

**Present state**: `src/pausio/domain.py` holds `Interval` / `EditPlan` and JSON conversion, `planner.py` the deterministic cut policy, `media.py` FFprobe / FFmpeg interactions, `cli.py` the user-facing orchestration.

**Contract examples**:
- Segment to KEEP: `{"start_ms": 1200, "end_ms": 3400}` in source time; not output time.
- Only `schema_version: 1` is supported today. Preserve it; never relabel a changed shape as v1.
- `source` is resolved relative to the plan file if not absolute; portability requires testing relocation.
- `source_duration_ms` > 0; intervals strictly positive, ordered, within source, no overlap.
- `has_audio` reflects source availability, not requested export codec.
- `preset` currently only accepts `ai-natural`.

**Schema change checklist**: clarify source vs output timeline, define defaults, add JSON round-trip tests, specify unknown-field policy, consider historical v1 plan round trip, revise docs and add an ADR.

**Adapters**: take immutable source refs / normalized timestamps, return typed analysis with provenance. Do not let ASR model objects, FFmpeg output or CapCut draft data leak into the core.
