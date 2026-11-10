---
name: pausio-edit-command-schema
description: Use for any Pausio UI edit, timeline action, command schema, project import/export, undo/redo, AI-driven edits, migrations or external editor interoperability. Require versioned deterministic replay and exact media binding; never store output-affecting changes only in UI state.
---

# Editing is a versioned command — never a hidden UI mutation

## Required architecture

Every user change that may affect the rendered video **MUST** have a typed, replayable command in `src/pausio/project_commands.py`. The browser dispatches instructions to `POST /api/command` with `revision`, `type` and `payload`. Python validates, appends, replays and derives the FFmpeg `EditPlan`. No separate JS-only editing state or silent full-plan overwrite.

Before touching edit behavior, read [`docs/PROJECT_FORMAT.md`](../../../docs/PROJECT_FORMAT.md), [JSON Schema v2](../../../schemas/pausio-project-v2.schema.json), legacy [v1 schema](../../../schemas/pausio-project-v1.schema.json), and `src/pausio/domain.py`.

## Checklist for each new edit feature

1. Name the operation precisely (`segment.update`, `subtitle.correct`, `audio.gain.set`, etc.) and define its **scope**, stable target ID, source-/output-time coordinates, units, parameters, defaults and failure cases.
2. Add a versioned event payload and matching JSON Schema. Reject unknown fields and unsupported versions; don't silently repurpose an existing type.
3. Make pure replay deterministic (no model calls, filesystem, clocks or randomness); store actual proposal values rather than only model prompt/seed.
4. Validate source-fingerprint binding, timestamp bounds, segment invariants and all references; failed command must leave both plan and log unchanged.
5. Show the UI change only after server acceptance. Record the user decision (including approval), not just the final cut list.
6. Updating an output-affecting setting invalidates approval and any stale export. Preview/render and import/export must derive from the same canonical projection.
7. Add pure replay, JSON export/import, rollback-on-invalid, stale revision and HTTP integration tests. Document migration strategy for later versions.
8. Keep source media, raw transcripts, private paths and API tokens **out of portable edit instructions**. External assets require references and provenance, not assumptions.

## History and recovery invariants

- V2 portable projects store the complete event history, `history_cursor` and monotonic `revision`. Undo/Redo are structured `history.undo` / `history.redo` API operations that move the cursor without generating fake inverse edits.
- On an edit after Undo, drop only the now-inactive redo tail and append the new event, preserving stable segment IDs. Redo must not apply an abandoned branch.
- Validate the full history, including inactive redo events. V1 import must migrate with cursor at the end and unchanged event IDs.
- The **portable** project is media-free; the **private local** session in `studio_persistence.py` additionally stores the imported video and atomic checkpoints. Do not conflate the two.
- Commit autosave to disk before displaying a successful UI edit; on disk failure leave in-memory project unchanged. Use one previous checkpoint and verify the media SHA-256 on restart.
- Never silently delete cached media after a failed recovery. Provide an explicit local-data delete action, locked to one running Studio per workspace.

## Current v2 event types
`analysis.propose`, `segment.update`, `segment.remove`, `segment.insert`, `timeline.restore_suggestion`, `timeline.keep_all`, `timeline.approve`, `timeline.replace` (legacy bridge).

## Future rule for prompt-driven changes
AI may **propose** a list of typed events plus evidence and rationale, but never directly mutate timeline arrays or authorize export. User reviews and confirms the same canonical commands as manual editing.

## Verification
`python -m unittest discover -s tests -v`
`python scripts/validate_skills.py`

Portable v2 project export/import, Undo/Redo, v1 import migration and local active-session recovery are implemented. Subtitle, audio/video effect commands and multi-project management are still future work.
