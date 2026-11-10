---
name: pausio-speech-ai
description: Use when integrating, validating or benchmarking Pausio transcription, Italian word alignment or VAD evidence. ClosedRoom dev owns all actual ASR/VAD engines, model management and caching; do not implement a second ML stack in Pausio.
---

# Reuse ClosedRoom local ASR — never reinvent transcription

## Owner and source of truth

The existing implementation lives in [daniele21/closedroom](https://github.com/daniele21/closedroom), branch `dev` (review upstream commit before changing contracts). ClosedRoom already supports on-device MLX Whisper / Nemotron, VAD, ASR worker, progress reporting, model configuration, caching and transcripts.

**Do not add faster-whisper, WhisperX, whisper.cpp, standalone Silero or another ASR runtime to Pausio.** Pausio must be a consumer, not a fork. ClosedRoom contains optional cloud providers but Pausio MUST explicitly select its local provider.

## Current API boundary

1. Read `docs/CLOSEDROOM_INTEGRATION.md`, `src/pausio/closedroom_asr.py` and upstream `src/local_asr_server/routers/transcriptions.py`, `schemas.py`, `services/transcription_service.py` on `dev`.
2. Use existing `POST /v1/audio/transcriptions/path` on `http://127.0.0.1:1236` with `file` absolute local WAV path, `language=it`, `asr_provider=local`, `response_format=verbose_json`, `word_timestamps=true`. Require same-machine loopback, no redirects or proxies; never silently select Speechmatics.
3. Keep video/audio files immutable. An FFmpeg-extracted WAV exists only for the request and must be cleaned after completion or failure. Server must be explicitly started/configured by user and models pre-provisioned if network downloads are forbidden.
4. Normalize ClosedRoom start/end seconds to source-time integer milliseconds. Preserve exact transcript text, model/backend provenance and actually returned word timings. Never fabricate word-level alignment, confidence or diarization.
5. Keep the reviewable transcript sidecar separate from Pausio EditPlan until the schema and source→output timeline remapping are explicitly implemented and tested. Do not automatically approve a text-derived cut.
6. Diagnose failures at the actual boundary (ClosedRoom unavailable, model missing, HTTP errors, response schema/timestamps, FFmpeg extraction, timebase offsets) before suggesting a new ASR library.
7. On need for shared engine code or a stable SDK, implement/extract it upstream in ClosedRoom, version a contract there, and consume via dependency/adapter. Do not copy model code into Pausio.

## Testing gate

- Local adapter unit tests with fake ClosedRoom payload (including missing word alignment, negative/nonfinite timestamps, local-only provider).
- Synthetic FFmpeg video→temporary WAV→mocked API checks.
- Before claiming production compatibility, run **real** ClosedRoom `dev` service with an A56 video, verify Italian jargon, word alignment, VFR, resampling offset, progress and cache behavior, and inspect transcript sidecar.

See [actual ClosedRoom contract](references/asr-contract.md).
