# Portable Pausio editing project (.pausio.json)

## Source of truth

**Every editing action is a typed instruction.** The UI never directly owns the final timeline. The pure Python reducer `src/pausio/project_commands.py` validates/replays an ordered command tape and derives the same `EditPlan` used by FFmpeg.

The format is `pausio.project`, `schema_version: 1` and is documented by [JSON Schema v1](../schemas/pausio-project-v1.schema.json). JSON Schema checks the *shape*; the reducer additionally checks ordering, interval overlap, valid IDs, existing targets, media duration bounds and command history semantics.

## Example

Below is explanatory sample data, **not a file for importing against your own video** (the SHA-256 must match the exact imported source).

```json
{
  "format": "pausio.project",
  "schema_version": 1,
  "media": {
    "filename": "ripresa.mp4",
    "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "duration_ms": 10000,
    "has_audio": true
  },
  "commands": [
    {
      "id": "11111111111111111111111111111111",
      "type": "analysis.propose",
      "payload": {
        "engine": "ffmpeg.silencedetect",
        "policy": "ai-natural",
        "noise_db": -35,
        "segments": [
          {"id": "22222222222222222222222222222222", "start_ms": 0, "end_ms": 2300},
          {"id": "33333333333333333333333333333333", "start_ms": 3900, "end_ms": 10000}
        ]
      }
    },
    {
      "id": "44444444444444444444444444444444",
      "type": "segment.update",
      "payload": {
        "segment_id": "22222222222222222222222222222222",
        "start_ms": 0,
        "end_ms": 2400
      }
    },
    {
      "id": "55555555555555555555555555555555",
      "type": "timeline.approve",
      "payload": {}
    }
  ]
}
```

This reproduces a final kept timeline of `[0,2400)` and `[3900,10000)`, with explicit human approval. No ASR rerun is necessary because the proposal is recorded as concrete source-time intervals.

## Command vocabulary v1

| Type | Parameters | Effect |
| --- | --- | --- |
| `analysis.propose` | exact KEEP segments with stable IDs; analysis engine/policy/threshold | stores original suggestion, initializes a new editable timeline |
| `segment.update` | `segment_id`, `start_ms`, `end_ms` | trims/extends one identified segment |
| `segment.remove` | `segment_id` | excludes an entire retained region (cannot remove the final one) |
| `segment.insert` | a stable-ID segment (created by server) | recovers a removed range |
| `timeline.restore_suggestion` | none | restores the last AI proposal |
| `timeline.keep_all` | none | retains the original video without cuts |
| `timeline.approve` | none | explicit editorial approval; required for render |
| `timeline.replace` | complete identified KEEP list | backward-compatible legacy plan replace; discouraged for new UI controls |

IDs are 32-character lowercase hex identifiers. Times are integer milliseconds on the **original source timeline**, not output timestamps. Keep regions are half-open [start_ms, end_ms), sorted, non-overlapping and within media duration. Source paths, video bytes, model weights and transcripts are deliberately excluded from this v1 project file.

Only timeline-changing commands reset approval; an imported approved timeline stays logically approved **only after matching the exact source fingerprint**. Rendering an imported project still requires explicitly clicking Export and validating the final output.

## API and UI flow

1. Import the video (existing `POST /api/import`).
2. Perform analysis or edit with a specific UI action (new `POST /api/command`, shape below).
3. Save the project via **Esporta progetto**: `GET /api/project/export` returns `.pausio.json`.
4. Later import the **same video** into Pausio Studio, then choose **Importa progetto** (new `POST /api/project/import`).
5. Pausio validates format/version, SHA-256 of original media and every command. On full success it atomically replaces the derived plan; otherwise the current session remains unchanged.

```json
{
  "revision": 2,
  "type": "segment.update",
  "payload": {
    "segment_id": "22222222222222222222222222222222",
    "start_ms": 100,
    "end_ms": 2100
  }
}
```

The server assigns a unique event ID, validates the requested revision against the current history length, and responds with a fresh authoritative snapshot. Stale revisions fail with HTTP 409 (optimistic concurrency); malformed commands fail with HTTP 400. The Studio UI never sends a generic "overwrite the entire JSON" for single-range edits.

The legacy `POST /api/plan` continues to work for compatibility, but explicitly creates a `timeline.replace` instruction.

## Portability and safety

- **The video is NOT embedded.** Bring the original media separately; Pausio compares its streaming-computed SHA-256. Filename alone never authorizes binding.
- **Import is data-only.** Unknown or future commands/schema versions are rejected, never executed as code.
- No absolute source paths or external URLs are stored; the same project can be reopened on a different computer when paired with the identical video bytes.
- Replay is deterministic and independent of the AI model: no rerunning ClosedRoom, Whisper or FFmpeg silence detection for existing suggestions.
- v1 contains edit instructions only; it doesn't serialize transcripts, visual effects, fonts, subtitle assets or packaged exports. Each future *output-affecting* UI feature MUST add a typed, versioned operation with migration, import/export tests and a deterministic render/preview mapping.
- Export codec/profile in this release is still fixed by Pausio's renderer (1080x1920 H.264/AAC). Before adding export settings, record them as typed instructions rather than untracked UI-only state.
- No timeline-changing instruction can bypass explicit approval. A malformed or different-video project cannot partially mutate the active session.

## Quality gates

- Round-trip: `parse(serialize(project))` produces identical command history and derived plan.
- Replaying on the exact same media reproduces segment IDs, timing and approval without ASR or analysis.
- Invalid interval, stale revision, unknown type, unsupported version and source hash mismatch are rejected.
- Media/edit plan immutable unless a valid command is committed; no partial writes.
- CI covers pure replay and HTTP import/export. Real A56 and full browser QA remain separate acceptance gates.

## Next evolution

Add generic undo/redo by structured history cursor or explicit compensating commands; structured effects (captions, crop, color, audio), selection tools, AI/prompt edits (as a proposal that emits the **same typed commands**), batch operations and optional interchange exporters (e.g. OpenTimelineIO / CapCut). Preserve the canonical Pausio command model as source of truth rather than making CapCut drafts the database.
