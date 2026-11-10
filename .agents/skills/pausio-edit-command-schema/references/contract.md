# Commands and project format reference

Canonical specification: `docs/PROJECT_FORMAT.md`. Machine-readable shape: `schemas/pausio-project-v1.schema.json`.

## Principles
- Event: `{"id":"<32 lowercase hex>","type":"segment.update","payload":{...}}`
- Commands ordered and immutable; `project_revision = len(commands)`.
- UI post: `{"revision":3,"type":"segment.update","payload":{"segment_id":"...","start_ms":100,"end_ms":200}}`.
- Source-bound: `media.sha256` of imported video, plus source duration and audio presence.
- Command IDs and segment IDs are different roles. Segment IDs remain stable under trim/update.
- Replay follows the same source-to-output edit plan as FFmpeg; no model needs to rerun.
- Approval is an explicit event; any later editing action invalidates it.
- Unknown events/fields/versions: **reject**, do not ignore.
- Source paths never appear in portable projects; no cloud/network importers.

## Tests
- Export → mutate → import → identical timeline and approval.
- Wrong fingerprint, schema 2, unknown command, duplicate ID, overlap, inverted interval.
- Stale UI revision results HTTP 409 and no state change.
- Regression of legacy `/api/plan` to explicit `timeline.replace`.
- No reliance on browser client to enforce editing invariants.
