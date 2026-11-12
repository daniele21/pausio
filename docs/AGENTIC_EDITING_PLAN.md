# Pausio — Agent-ready Studio: execution plan

Status: PROPOSED / 12 November 2026. Product plan, not a claim that the capabilities below are shipped.
Owner: Pausio. Canonical implementation tracker for overlay editing, audio loudness, local media library, self-hosted transcription and ChatGPT/Claude Chat interoperability.

## Product contract / non-goals

A creator converses directly with **ChatGPT or Claude Chat using their existing subscription**, supplies a video (when supported) or a timestamped storyboard/transcript, and asks the assistant to finish a social video. The **chat model performs all semantic/visual/editorial judgment**: what to cut, explain, show, emphasize and which music fits. Pausio is the **deterministic, tool-addressable editing environment**: import, expose observations, execute proposed edits, preview, inspect, revise and export. No OpenAI/Anthropic inference API key is needed for Pausio, and no second LLM is hosted inside it.

The chat platform's support for raw video, attachments, custom connectors, tool writes, generated images and feedback into the chat **must be tested on the actual subscription and client**. Never assert blanket native MP4 or remote-MCP support. If video analysis is unavailable in a chosen chat client, Pausio supplies *data* (storyboard/contact sheets with timestamps, optionally short clips, transcript, technical measurements). It does not semantically interpret frames on behalf of the model. This is a capability-aware fallback, not silent degradation.

Future agent loop: OBSERVE -> PROPOSE -> VALIDATE -> APPLY -> RENDER PREVIEW -> INSPECT -> REVISE -> HUMAN APPROVAL -> EXPORT. Approval is explicit. The user can open the same project in Studio and undo/modify every edit. AI output is untrusted input, not executable code.

No cloud inference calls, no autonomous uploads, no mandatory paid services, no embedding raw/private video in the public repository, no arbitrary shell-execution tool, no unattended public posting, and no guarantee of unattended operation in chat clients that do not permit persistent tool execution.

## Baseline and integration prerequisite

As of 2026-11-12, main includes PR #18 (FX/mixer), #23 (desktop workspace), #24 (caption timing), #25 (caption trim/search). Existing: local Python/FFmpeg, standalone optional MLX Whisper, caption export, source-time KEEP timeline, project commands v2, Undo/Redo, FFmpeg previews, local private autosave, browser QA.

PR #26 (desktop/webcam portrait capture + Studio import) **conflicts with main** following prior merged mobile 9:16 fix PR #22; PRs #27 (teleprompter rehearsal) and #28 (FFmpeg ASS filter detection) depend on #26. Keep these pending until conflicts are reconciled without losing #22 portrait composition/framing and gobbo controls. #28 is a targeted bug fix and should be backported independently if the capture chain cannot be integrated safely.

**P0-MERGE**: Reconcile #22 + #26 on a new daniele/* integration branch; preserve all mobile portrait/gobbo behaviors and new desktop capture; run Python CI, Playwright at 320/390/desktop, FFprobe 9:16 with audio, Safari/Android manual checks. Then integrate #27 and #28. Do not force-merge the divergent capture.js, capture.html, capture.css or tests. Do not overwrite main by direct push; integrate via reviewed PRs. Acceptance: real 9:16 media, desktop recorder, mobile script controls, no lost features, PASS CI and documented residual hardware QA.

## Architectural invariants

1. **One editing engine**. UI, CLI, import bundle and MCP call the same validated command service/reducer. No extra renderer or duplicate timeline for agents.
2. **Commands are canonical**. Every output-affecting edit is typed, versioned, deterministic, schema-validated and serializable. Stable UUID-like IDs, integer source-time milliseconds, explicit output/source mapping, canonical positions/sizes, fixed preset versions and bounded values. Browser-only ephemeral selection is not an edit.
3. **Agent proposals are transactions**. Separate dry-run validation and atomic apply against source SHA-256 + exact project revision. Optimistic concurrency 409, idempotency keys, diagnostics and per-command errors. Never partially apply a failed batch. Apply creates undoable history; any modification invalidates approval and previews.
4. **Assets are first-class**. Import assets into a private content-addressed store. Store SHA-256, MIME, duration, sample rate/size, provenance, licensing fields and usage rights. Portable manifest uses asset IDs + hashes, not absolute file paths. Provide explicit relink; refuse missing/mismatched assets before render. A full transferable project bundle may contain assets, but the lightweight JSON does not embed them.
5. **Separation of concerns**. Pausio runs no LLM for creative analysis. Technical metadata, actual FFmpeg loudness, waveform, thumbnails, transcript and render diagnostics are observations. The chat model interprets them. Avoid calling processing tools 'AI analysis'.
6. **Trust boundaries**. Studio's loopback HTTP server stays local; do not expose its existing session/CSRF endpoints directly to the internet. Any remote connector uses a separate authenticated, scoped HTTPS gateway with deny-by-default capabilities. Do not embed private GitHub credentials in project files. Avoid logging transcripts/assets/tokens.
7. **Reproducible, not necessarily bit-identical**. Pin renderer profile + FFmpeg version, font availability and asset hashes; preview/final use the same composition rules. Identical binary hashes across OS/codecs are not promised.
8. **Explicit authority**. Reading/analyzing the project is safe within user-granted scope; importing private video, starting runner jobs, uploading asset bytes and exporting are distinct consent-checked actions. No agent may silently delete originals, overwrite, publish or export to third-party destinations.

## Work packages, order and acceptance

### WP0 — Capability spikes and prerequisite stabilization [P0; small + integration risk]

Dependencies: none; precedes all other work.

- WP0.1 Resolve the #22/#26 conflict; integrate #27/#28 safely as described above.
- WP0.2 Build tiny end-to-end MCP spike: get_project -> validate/apply harmless caption/style edit -> render_preview. Test with **ChatGPT chat** and **Claude Chat** in the intended clients/accounts, using subscriptions rather than model API keys.
- WP0.3 Document actual client support: video upload vs image/storyboard route; file and generated-asset transfer; tool write approvals; local vs remote MCP/Apps, OAuth/HTTPS constraints, background job polling and final-file retrieval.
- WP0.4 Choose supported surface(s) for MVP from measured evidence. Claude Desktop local MCP may be one route; browser chat may require a remote HTTPS gateway. Do not assume parity.

Acceptance: demo logs, screenshots, plan/entitlement caveats, end-to-end harmless command from each supported client, clear fallback for unsupported client. Fail closed rather than pretending tools ran.

### WP1 — Instruction engine v3 and agent transactions [P0; large]

Dependencies: WP0 (especially feasibility), existing v2 reducer.

- Design versioned project schema v3 (migration from v1/v2; preserve command/history IDs, active cursor and revision).
- Introduce project_id/workspace_id, asset manifest, annotation/overlay and audio command families, media fingerprint, rendering profile and explicit source/output time coordinates.
- New typed commands: overlay.add/update/remove/transform; audio.loudness.configure; audio.track.add/update/remove; audio.track.gain; media.asset.import/relink; video.transform when implemented. Do not advertise non-implemented commands.
- Distinguish **project snapshot** (history + references) from **instruction batch** (precondition/revision, source hash, commands, optional required assets, author/provenance and rationale).
- Add validate_batch(dry_run), apply_batch(atomic), report_diff, undo/redo, and history provenance without hidden divergent state.
- Provide transaction-level revision and idempotency keys, deterministic failure when an ID is unknown, asset missing, cue out of bounds, invalid code/content or unsupported schema.
- Define cut boundary policy for overlays: store source-time anchored intervals; intersect/remap KEEP spans, split when necessary, never silently shift onto unrelated words.
- Standardize error categories so Studio and MCP receive the same actionable validation output.

Acceptance: v1/v2 round-trip migration; deterministic replay tests for every command; invalid inputs rejected; 409 on stale project; 2+ edits applied atomically; undo/redo/reimport exact same modeled state; no old projects lost.

### WP2 — Visual overlay editor (human and agent parity) [P0; large]

Dependencies: WP1 and current timeline/captions.

- First templates: text callout, statistic (value/label/source), code/terminal (safe text + syntax highlighting), image. Then video clip/B-roll with explicit crop/fill strategy.
- UI: +Overlay at playhead or selected transcript phrase; template palette; in-preview drag/resize, keyboard control, alignment/snapping and social safe-zone indicator; handles and stacking lanes on source-time timeline; contextual property inspector; duplicate/delete; preset save/reuse.
- Persist exact content, position/size normalized to 1080x1920 reference, anchor, start/end ms, z-index, animation presets and template version. Prefer deterministic preset/keyframe primitives instead of browser-only CSS animations.
- Media: image/video import, content hash, licensing metadata, thumbnails, replacement/relink. Font handling and supported SVG/raster safety must be explicit.
- Render: FFmpeg filtergraph overlay/ass/drawtext or a controlled rasterization adapter. No untrusted arbitrary filter strings or user shell injection. Preview FFmpeg and exported MP4 must agree on text placement, layering and timing; reconcile captions to avoid face/CTA occlusion.
- Agent uses precisely the same overlay.add/update/etc operations as UI. A selected transcript segment may prefill a proposed overlay; the human can accept/edit it.

Acceptance: add '1.379 segreti' at 15–20.5 s, terminal command later, import screenshot, move/resize/trim and undo/redo, export project, restart/reimport and reproduce the same visual edit; verify in 540x960 preview + 1080x1920 final; 320/390 mobile UI usable, keyboard and Playwright screenshot checks.

### WP2b — Camera motion, punch-ins and video transitions [P0/P1; medium/large]

Detailed spec: [VISUAL_MOTION_EFFECTS_PLAN.md](VISUAL_MOTION_EFFECTS_PLAN.md). Research and configurable automatic preset contract: [VISUAL_FX_AUTOMATION_RESEARCH.md](VISUAL_FX_AUTOMATION_RESEARCH.md), [versioned JSON profiles](../configs/visual_fx_presets_v1.json). Presets are not yet connected to Studio or rendering; use conservative local evidence-based proposals, then manual or chat-agent review. This is distinct from overlay editing: it changes the underlying footage framing or relationship between adjacent KEEP segments.

- MVP manual: source-segment-anchored punch-in/out and animated zoom/pan with ordered keyframes, explicit crop/face anchor, bounded scale, easing and start/end source ms.
- Optional transition event at a specific pair of adjacent KEEP segment IDs: start with hard cut and 120–250ms approved dissolve or dip. Enforce trim handles and A/V synchronization; no transition spam after every speech pause.
- Suggest mode: deterministic, conservative candidate ranking from existing cut boundaries, phrase/word timing, audio emphasis (when available) and optional locally tracked face. Default subtle; show evidence, confidence, proposal preview and individual accept/reject. No generated false prosody for silent reference clips.
- Composition order: KEEP -> per-clip transforms -> boundary transitions -> caption/overlay placement -> audio mix. Captions must remain stable and cannot drift with the face.
- All effects typed, versioned, deterministic/replayable/importable and reversible. UI Video FX track, MCP tool parity once permitted, frame-accurate preview/final, no raw FFmpeg filters or arbitrary remote media URLs.
- Security: bound effect counts, keyframes, render time and imported media complexity; follow local-first, security and runner gates. User-created screen recordings/reference footage never committed to Git.

Acceptance: at least two reference-quality selective punch-ins and one intentional transition across three KEEP clips, passing Python/FFmpeg and Playwright plus real-phone review, no clipped speech or moving subtitles. Initial feature implementation is pending, not shipped.

### WP3 — Audio loudness, normalizing and mix quality [P0; medium]

Dependencies: existing PR #18 audio mixer and WP1 instructions.

- Add an audio analysis adapter using FFmpeg ebur128=peak=true or loudnorm measurement. Persist measured integrated LUFS (I), LRA, true peak dBTP, short-term/momentary time series, measurement metadata and source/output revision cache key.
- Studio Audio panel shows **source** and **current full mix/final export** values; visual target difference, clipping warnings and before/after, not fabricated values based on waveform peaks.
- Preset Voice social default proposal: -16 LUFS integrated, <= -1.5 dBTP true peak (user configurable; **not an official universal platform rule**).
- Use two-pass loudnorm where possible, after all cuts, gains, risers/music, ducking and fades; validate true peak and integrated LUFS on decoded final AAC file. Some content may not safely reach target; report shortfall rather than false success.
- Typed target, enabled flag, max true peak, method, output measurements, render provenance; edits invalidate audio analysis where relevant and cached preview.
- Add protected limiter, safe headroom, suitable gain staging; allow comparing loudness-matched A/B clips without auto-replacing source.

Acceptance: measured reference synthetic videos; no unreported clipping, robust silent/no-audio behavior, stable across repeated renders, target results reported with tolerance (e.g. +/-1 LU and true peak within 0.3 dBTP) where physically achievable; UI/CLI/batch parity; measurements are from actual rendered media.

### WP4 — Personal media library and asset browser [P1; medium]

Dependencies: WP1, WP2, WP3.

- User-controlled private library roots and import flow (no implicit browsing of the whole disk, no cloud library by default).
- Index music/riser/image/video: file hash, duration, MIME, loudness/peak, user tags, mood/genre, BPM when provided/measured with evidence, license/source, usage restrictions; metadata is searchable via Studio and MCP.
- Provide previews and waveforms; drag music/FX from library to a typed audio track. Controls for bus volume, per-clip gain, trim, fade, loop, ducking, mixing under narration and LUFS reanalysis.
- Agent can list/filter and audition metadata/previews, pick only allowed assets, explain choice and propose timing/volumes. No assumption that BPM or mood is always known.
- Portable project uses hash/reference plus optional bundle; missing assets detected in preflight, explicit relink workflow.

Acceptance: select one track from private library, mix under voice at user-defined gain, add a riser, export, reload, verify no missing media and provenance metadata; no raw library files committed to Git.

### WP5 — Transcription via self-hosted GitHub Actions [P1; medium/high]

Dependencies: WP0 remote-tool feasibility, existing Pausio local_asr and WP1 jobs.

- Retain current Pausio-owned MLX Whisper engine; introduce *optional execution adapter* dispatching a fixed, version-pinned workflow to a **trusted self-hosted runner**. No new ASR provider.
- Local same-Mac runner: preapproved private shared workspace referenced by opaque job/project IDs, not arbitrary paths. Separate-machine runner: private authenticated transfer or user-approved storage, with retention/cleanup policy; never put video in Git history, workflow YAML args or public Actions artifacts.
- API: start_transcription(project_id, language, model, allow_model_download=false), get_job_status(job_id), cancel_job when possible, attach_transcript(job_id). Dispatch uses workflow_dispatch with minimal permissions and allowlisted inputs; job result bound to media SHA-256 and source timestamps.
- Polling, retry/recovery, concurrency policy, status provenance (workflow run ID, model hash/version, status/errors), minimal logs and network opt-in. Runner must not execute agent-provided scripts or arbitrary commands.
- In chat, the assistant triggers the job via Pausio, polls or resumes when the client supports it, then receives transcript/word timings. If chat has no persistent execution, user can return to the conversation; don't claim a continuous agent loop.

Acceptance: real self-hosted run on sample, media not leaked into Actions logs/artifacts, transcript stored in Pausio workspace and reusable without rerun, correct timestamp alignment after trims, proper failure/retry/permission/restart behavior.

### WP6 — Observation/export tools for a chat-based video editor [P0/P1; medium]

Dependencies: WP1; later WPs add richer tools.

- Read-only tools: list_projects, get_project, get_timeline, get_transcript, get_audio_analysis, get_render_diagnostics, list_assets, get_asset_metadata.
- Visual access: get_storyboard (configurable timestamp samples, dimensions and contact sheet), get_frame(time_ms), get_preview_clip(range) with bounded size and signed scope, get_safe_areas. Every output must carry source/output timebase and media hash.
- Agent can request denser samples around confusing moments. Pausio extracts real pixels/words; no semantic vision inference locally.
- Tool resource size caps/quotas; user-selectable privacy/attachment sharing and explicit consent for remote transfer. Tools report inaccessible media rather than fabricated observations.
- Rendering tools: render_preview, inspect_render (frames, subtitle placement measurements, LUFS, A/V sync, stderr), export_video after explicit approval. Final artifact URL/path access must be scoped and expiring if remote.

Acceptance: assistant can understand the 88.2 s example from actual frames + transcript, choose edit points, preview the result and identify remaining subtitle/audio issues without an internal Pausio LLM.

### WP7 — MCP/ChatGPT and Claude Chat connector [P0 spike then P1; large]

Dependencies: WP0 feasibility; WP1+WP6 for meaningful workflows.

- Implement shared application service for typed operations, then MCP adapters; no duplicate logic in MCP handlers. Do not put high-level creativity/reasoning into Pausio.
- Suggested tool groups: observe.*, transcript.*, audio.*, asset.*, timeline.*, overlay.*, project.validate/apply/undo, render.preview/inspect/export. Minimize tools in initial client session; enable richer capability by phase.
- Claude Desktop local MCP where supported; for browser ChatGPT/Claude Chat use a distinct authenticated HTTPS MCP endpoint (or supported plugin path). Existing localhost Studio must NOT become publicly accessible.
- OAuth/token scope, allowlisted operations, project-specific access, replay protection, short-lived credentials, rate limits, audit logs (metadata only), transport CSRF/SSRF checks, no arbitrary filesystem paths, no shell exec and no unsafe arbitrary FFmpeg filter strings.
- Agent attaches a declared reason/confidence to proposed edits; Pausio stores provenance alongside typed commands but never trusts the rationale as an instruction.
- Display agent proposal diff in Studio and require explicit human approval for applying high-impact proposals and final export; optional future policies may narrow approvals after real QA.
- Feature compatibility matrix by chat product/account/client, with documented unsupported operations and fallback to exportable instruction package.

Acceptance: in a real ChatGPT or Claude Chat session (not model API), use scoped tools to fetch project -> propose three overlays and one audio normalization change -> validate/apply -> render -> inspect -> revise -> request final approval. Audit that no unauthorized network/upload/file read took place.

### WP8 — Quality loop and pilot video [P1; medium]

Dependencies: WP2, WP3, WP6, WP7; music and runner optional for first vertical slice.

- Single pilot: existing talking-head cybersecurity video. Desired overlays: research statistic, permission mechanism illustration and Git command. Fix caption typo (.claude/settings.local.json), adjust framing, normalize voice and optionally choose music from the private library.
- Pilot agent receives video when chat client supports it, otherwise Pausio-produced timestamped storyboard + transcript; ChatGPT/Claude decides content, no Pausio semantic agent.
- Agent creates **structured instructions**, checks preview, edits issues detected, and asks for explicit human acceptance of the final proposal. Preserve manual overrides.
- Compare with manual baseline in Pausio/CapCut: editing time, changes accepted/rejected, caption error rate, overlay timing and safe-zone compliance, true peak/LUFS, video A/V sync, unsupported-tool behavior.
- Goal metrics (proposed, not measured): zero silent media replacements/exports; 100% output-affecting edits replayable; all three overlays rendered as positioned; word/subtitle timing ≤100 ms drift on test fixtures; loudness QC within stated achievable tolerance; ≥30% manual time savings in 3 clips compared with the measured manual workflow.

Acceptance: one approved MP4, editable project/bundle, instruction batch and asset manifest, QA screenshots and render diagnostics, tests and user approval captured.

## Recommended delivery order and parallel tracks

1. **Gate 0**: merge reconciliation + MCP feasibility spike. Do not spend weeks building remote integration before confirming chat-client support.
2. **Milestone A**: WP1 instruction protocol/transaction + basic WP6 observations. Independently start WP3 LUFS analysis on an adapter branch.
3. **Milestone B**: WP2 overlay editor; WP3 normalization; both integrated into the same instruction engine. These are enough for a meaningful manual Studio improvement.
4. **Milestone C**: WP7 minimal MCP tool set and pilot loop; in parallel WP4 media library and WP5 self-hosted transcription adapter after access/credentials are provisioned.
5. **Milestone D**: WP8 iterative agentic pilot, visual and audio QA, stabilization and documented supported clients.

Parallelization: audio measurement and storyboard extraction can proceed while the schema is designed; Studio overlay UI can start with fixture-backed controls but must not ship without the shared typed commands/real renderer; connector implementations must wait for validated services. Keep work in daniele/* branches with small, testable PRs; no direct push to main without explicit authorization.

## Interface examples (design only, not implemented)

Agent proposes a batch against a specific source/project revision:

~~~json
{
  "format": "pausio.instruction-batch",
  "schema_version": 1,
  "project_id": "project-opaque-id",
  "base_revision": 42,
  "source_sha256": "<64 lowercase hex characters>",
  "idempotency_key": "client-generated-unique-key",
  "commands": [
    {
      "type": "overlay.add",
      "payload": {
        "id": "stable-generated-id",
        "kind": "statistic",
        "start_ms": 15000,
        "end_ms": 20500,
        "timebase": "source",
        "value": "1.379",
        "label": "segreti individuati",
        "source_label": "Apiiro",
        "style_preset": "statistic-dark-v1",
        "x_pct": 50,
        "y_pct": 25,
        "z_index": 10
      }
    },
    {
      "type": "audio.loudness.configure",
      "payload": {
        "enabled": true,
        "target_integrated_lufs": -16,
        "max_true_peak_dbtp": -1.5,
        "method": "two_pass"
      }
    }
  ]
}
~~~

For strict validation, production will use real stable IDs, exact typed per-command payloads, an actual source digest, asset manifests, server-assigned provenance and a versioned JSON Schema. This sketch is deliberately illustrative.

Representative chat-tool journey:
1. list_projects / get_project; confirm chosen project.
2. get_storyboard + get_transcript; chat model reads actual frames/text and plans.
3. list_assets; choose permitted music; start_transcription via runner only if transcript missing.
4. validate_batch -> diff review -> apply_batch.
5. render_preview -> get_frame or get_preview_clip + get_audio_analysis -> new batch if needed.
6. request explicit final approval -> export_video -> user downloads final MP4 and project.

## Security, interoperability and failure test matrix

- Media source mismatch, missing asset, transcript from wrong video, stale revision, reused idempotency key, invalid JSON/unsupported version and corrupted import.
- Agent-generated markup/code snippets cannot execute JS, browser events, commands or arbitrary FFmpeg expressions; escape text and enforce bounds.
- Wrong font, absent ASS filter (libass), unavailable binary, loudnorm nonconvergence, silent audio, duplicate music, missing license, 60/120 fps input and variable-frame-rate phone footage.
- Renderer crash, job timeout/retry/cancel, partial asset upload, runner offline, expired auth, concurrency between Studio and chat, import/export after restart, and poor network connectivity.
- MCP endpoint exposure: blocked unauthenticated tools, no loopback bypass, no arbitrary paths/commands, opt-in remote upload only, filtered logs and revocable tokens.
- UX: pointer/keyboard input, 320/390/768/1440 widths, captions and overlays within safe zones, high-DPI preview, Undo/Redo and no draft-only controls.
- Tests: Python reducer/schema/unit, FFmpeg synthetic E2E on preview/final, API permission tests, Playwright flows and screenshots, real Safari/macOS + Android/Galaxy A56 listening and visual sign-off.

## Definition of done for every deliverable

- User-facing feature works; no decorative controls.
- New output-affecting behavior is represented by validated typed commands; JSON import/export, replay, history, undo/redo and restart recovery covered.
- Same render semantics in preview and final, source video immutable, assets reproducible and licensed.
- Automated CI green with code/schema/security/FFmpeg tests; browser UI passes Playwright and screenshot review; limitations and unverified hardware called out.
- Documentation covers exact tool shape, access permissions, error handling, client support, version migration and privacy.
- Real pilot acceptance, not merely synthetic test green.

## Open decisions (explicit gates)

1. Which ChatGPT account/mode and which Claude Chat client actually permit the required MCP write operations and file round-trips? WP0 must resolve from a real proof.
2. Which Mac hosts Pausio Studio and which self-hosted runner has access to original video files? Choose private shared workspace vs authenticated transfer after measurement.
3. How will a generated image from chat be delivered safely into Pausio? Native tool asset attachment, explicit file upload or user download/relink; never infer local access to chat attachments.
4. Minimum portable project packaging: JSON + external assets now, or full project archive with assets and manifest? Prefer manifest first, archive next.
5. Should some command batches apply automatically? MVP policy is proposal/review/apply with explicit final export; do not relax without real pilot evidence.

## Related implementation sources

- docs/ARCHITECTURE.md and docs/DECISIONS.md
- docs/PROJECT_FORMAT.md and schemas/pausio-project-v2.schema.json
- docs/ROADMAP.md and docs/DESKTOP_EDITOR_UX.md
- src/pausio/project_commands.py, studio.py, media.py, local_asr.py, studio_static/
- .github/workflows/ci.yml, .github/workflows/playwright-ui.yml
- Existing pending capture stack: PR #26 -> #27 -> #28; dependency on merged #22 and #25
