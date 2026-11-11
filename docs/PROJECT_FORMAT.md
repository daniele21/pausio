# Portable Pausio editing project (.pausio.json)

## Source of truth

**Every editing action is a typed instruction.** The UI never directly owns the final timeline. The pure Python reducer `src/pausio/project_commands.py` validates/replays an ordered command tape and derives the same `EditPlan` used by FFmpeg.

The current format is `pausio.project`, `schema_version: 2` and is documented by [JSON Schema v2](../schemas/pausio-project-v2.schema.json). **Existing v1 files remain readable** using a strict migration (all commands preserved; history cursor placed at the end). V1 schema: [JSON Schema v1](../schemas/pausio-project-v1.schema.json). JSON Schema checks the *shape*; the reducer additionally checks ordering, interval overlap, valid IDs, existing targets, media duration bounds and command history semantics.

## Example

Below is explanatory sample data, **not a file for importing against your own video** (the SHA-256 must match the exact imported source).

```json
{
  "format": "pausio.project",
  "schema_version": 2,
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
  ],
  "history_cursor": 3,
  "revision": 3
}
```

This reproduces a final kept timeline of `[0,2400)` and `[3900,10000)`, with explicit human approval. The example has three total events, all applied; `history_cursor` is 3. No ASR rerun is necessary because the proposal is recorded as concrete source-time intervals.

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
| `caption.set` | `style`, source-time `cues` with stable IDs, text and start/end ms | creates subtitle track from ASR |
| `caption.correct` | `caption_id`, `text` | corrects one caption without rerunning transcription |
| `caption.style` | `style` = `social`, `minimal` or `boxed` | legacy preset change |
| `caption.configure` | exact validated `config` with preset, X/Y percentages, font family, font size, RGB colors, outline and background | persists custom or named style consistently for browser preview and FFmpeg output |
| `caption.clear` | no payload | removes subtitle track |

IDs are 32-character lowercase hex identifiers. Times are integer milliseconds on the **original source timeline**, not output timestamps. Keep regions are half-open [start_ms, end_ms), sorted, non-overlapping and within media duration. Source paths, video bytes, model weights and **raw ASR transcripts** are excluded. Reviewed caption cues (stable ID, timestamps, text) are intentionally persisted as typed v2 project commands: they affect exported video, and allow playback without rerunning transcription.

Only timeline-changing commands reset approval; an imported approved timeline stays logically approved **only after matching the exact source fingerprint**. Rendering an imported project still requires explicitly clicking Export and validating the final output.

## Undo, Redo and revisions in v2

- `commands` contains the **complete ordered history**, including any future events that can be redone. `history_cursor` is the number of currently applied events, from 0 through `len(commands)`.
- `revision` is a **monotonic concurrency token**, incremented by every accepted edit, Undo and Redo. It is not necessarily equal to the number of events. All API commands must carry the current revision; stale callers receive HTTP 409.
- The UI sends explicit `history.undo` and `history.redo` operations to `POST /api/command` with an empty payload. These **move the cursor**, while preserving the original immutable events. Undo/Redo is therefore structured and reversible, and the current position survives project export/import.
- A new editing event after Undo truncates the inactive Redo tail before appending the new event. Old event IDs stay stable; new events get new IDs. Rendering always uses the replayed **active prefix**, never the inactive tail.
- An explicit `timeline.approve` event may be undone/redone along with the edit history. Edits made after Undo invalidate prior approval as usual.
- Import validates both the active prefix **and the complete redo tail**; unknown or corrupted instructions are rejected even when currently undone.
- V1 imports are upgraded to V2 in memory; exporting always writes V2, preserving original event IDs and instructions.

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

The server assigns a unique event ID, validates the requested revision against the monotonic project revision, and responds with a fresh authoritative snapshot. Stale revisions fail with HTTP 409 (optimistic concurrency); malformed commands fail with HTTP 400. The Studio UI never sends a generic "overwrite the entire JSON" for single-range edits.

The legacy `POST /api/plan` continues to work for compatibility, but explicitly creates a `timeline.replace` instruction.

## Local autosave versus the portable project

Pausio Studio also maintains a **private, automatically saved local session** for crash/restart recovery. This is distinct from the portable document: the local workspace retains a copy of the imported video and an atomic JSON checkpoint, plus one previous checkpoint for fallback. Closing the server does not erase this directory. Default paths: macOS `~/Library/Application Support/Pausio/Studio`; Linux `~/.local/share/pausio/studio` (or XDG_DATA_HOME). Use `pausio studio --data-dir <directory>` to choose another folder.

The session is locked to a single running Studio process; file/directory permissions on POSIX are 0600/0700. If the latest checkpoint is damaged, Studio attempts to recover the previous valid one without discarding media. The UI allows **Elimina dati locali** to remove stored media and project/checkpoints. **Raw ASR transcript data is stored ONLY in the private local session checkpoint (format `pausio.local-session`, schema v2), together with a SHA-256 association to the imported media. Legacy local-session v1 files still recover without a transcript. The exported portable `.pausio.json` never includes raw ASR.** The reviewed caption instructions persist and recover without rerunning Pausio ASR. The exported `.pausio.json` never embeds the video.

## Portability and safety

- **The video is NOT embedded.** Bring the original media separately; Pausio compares its streaming-computed SHA-256. Filename alone never authorizes binding.
- **Import is data-only.** Unknown or future commands/schema versions are rejected, never executed as code.
- No absolute source paths or external URLs are stored; the same project can be reopened on a different computer when paired with the identical video bytes.
- Replay is deterministic and independent of the AI model: no rerunning ClosedRoom, Whisper or FFmpeg silence detection for existing suggestions.
- V1 contains timeline edit instructions only. Portable project V2 stores reviewed caption text/timing/styles including the allowlisted `font_family` in `caption.configure`, but no raw ASR, font assets or packaged exports. For older v2 `caption.configure` payloads where `font_family` is absent, replay deterministically inserts `Arial` without changing prior serialized commands. Private autosave V2 is a different format and additionally retains the ASR transcript. Each future *output-affecting* UI feature MUST add a typed, versioned operation with migration, import/export tests and a deterministic render/preview mapping.
- Export codec/profile in this release is still fixed by Pausio's renderer (1080x1920 H.264/AAC). Before adding export settings, record them as typed instructions rather than untracked UI-only state.
- No timeline-changing instruction can bypass explicit approval. A malformed or different-video project cannot partially mutate the active session.

## Quality gates

- Round-trip: `parse(serialize(project))` produces identical command history and derived plan.
- Replaying on the exact same media reproduces segment IDs, timing and approval without ASR or analysis.
- Invalid interval, stale revision, unknown type, unsupported version and source hash mismatch are rejected.
- Media/edit plan immutable unless a valid command is committed; no partial writes.
- CI covers pure replay and HTTP import/export. Real A56 and full browser QA remain separate acceptance gates.

## Next evolution

Extend structured effects (captions, crop, color, audio), selection tools, AI/prompt edits (as a proposal that emits the **same typed commands**), batch operations and optional interchange exporters (e.g. OpenTimelineIO / CapCut). Preserve the canonical Pausio command model as source of truth rather than making CapCut drafts the database.
