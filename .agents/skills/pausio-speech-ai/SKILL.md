---
name: pausio-speech-ai
description: Integrate and test Pausio-owned, independent on-device MLX Whisper transcription, language selection, explicit offline-first model provisioning, timestamps and local resource safeguards. ClosedRoom is a reference, not an operational dependency.
---

# Pausio standalone local ASR

Pausio MUST transcribe without ClosedRoom installed, running or exposing an HTTP service. ClosedRoom `dev` informs architecture and proven MLX Whisper options, but Pausio implements and owns `src/pausio/local_asr.py`.

## Engineering rules

1. Read `docs/LOCAL_ASR.md`, `src/pausio/local_asr.py`, `docs/DECISIONS.md` and the latest ClosedRoom `dev` transcriber when comparing optimization ideas.
2. Load MLX Whisper directly **on Apple Silicon**, with optional `pip install -e '.[asr]'`; no local HTTP service, cloud ASR, or hidden ClosedRoom process.
3. Always resolve model names to an existing local model directory **before** entering MLX Whisper. `snapshot_download(local_files_only=True)` by default; network downloads require the explicit `allow_model_download=true` UI approval or CLI `--allow-model-download`.
4. FFmpeg extracts 16 kHz mono PCM WAV into an ephemeral private directory; do not mutate or upload original audio/video. Clean temporary files on success and failure.
5. Preserve model/back-end metadata and actual segment and word timestamps in source-time integer milliseconds. Never invent word timestamps, confidence, speakers or diarization.
6. Keep transcripts as reviewable sidecar material, separate from the canonical edit-command timeline. Speech-derived edit proposals require new typed deterministic commands and explicit approval.
7. Model memory/latency, VAD, quality filtering, caching, cancellation and diarization are separate, staged improvements. Do not claim parity with ClosedRoom or verified quality until tested with real footage.
8. Installation failures, missing weights, CPU platform mismatches and malformed ASR output must be actionable, never silently route to a remote service.

## Test gates

- Pure validation and normalization tests, offline model cache tests with a fake HF resolver, explicit download opt-in forwarding and negative timestamps.
- Studio HTTP transcription job and CLI sidecar tests with mocked inference, Playwright import+transcribe UI, no running ClosedRoom.
- Real Mac Apple Silicon test on consented Italian footage, model output, audio sync and latency/memory budget before claiming product parity.

See [local ASR reference](references/asr-contract.md).
