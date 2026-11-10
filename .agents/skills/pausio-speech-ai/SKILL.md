---
name: pausio-speech-ai
description: Use when implementing or benchmarking local ASR, Italian transcription, word alignment, Silero VAD, WhisperX or faster-whisper adapters, resource management and ML-derived speech timestamps. Not for generic FFmpeg encoding.
---

# Local speech AI integration

## Procedure
1. Define the speech-analysis **contract** and test oracle before choosing model/library. Core `domain.py` and `planner.py` must not depend on Torch, CTranslate2, ONNX or model-specific structures.
2. Keep analysis separate from editing policy. A VAD score or ASR guess is evidence, not permission to cut.
3. Make model choice optional and explicit; document language, model revision, weights license, CPU/Metal performance, memory usage, sample rate, word timing confidence and provenance.
4. Never download weights silently or upload media. Explicit user opt-in is required for first-time downloads, network APIs or cloud inference; offer no-model fallback.
5. Normalize all timestamps to integer milliseconds in the **original source timeline**, accounting for audio extraction, resampling, start-time offsets and alignment drift. Prefer word-level timestamps only when alignment is actually available.
6. Handle Italian AI jargon and code-switching, hallucinations on silence, wind/traffic, two speakers, clipped words, extremely short audio and missing tracks.
7. Evaluate with consented real recordings (WER, timing deviations, VAD miss rate, false-cut risk), track reproducibility and run basic CPU acceptance tests.

## Constraints
Speech-derived edits remain proposals. No automatic deletion based only on low ASR confidence, no claims of diarization unless implemented/tested, and no mandatory heavyweight packages in base install.

See [ASR and VAD contract](references/asr-contract.md).
