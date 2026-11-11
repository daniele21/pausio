# Pausio — standalone local transcription with MLX Whisper

## Runtime, models and privacy

Pausio **does not require ClosedRoom to be running or installed**. Its active local engine is `src/pausio/local_asr.py`; ClosedRoom `dev` is only a reference for MLX decoding options and future VAD improvements.

- Platform: macOS Apple Silicon; FFmpeg and FFprobe must be available.
- Prefer a Python 3.12 virtual environment (`python -m pip install -e '.[asr]'`). Python 3.11–3.13 run in CI without an actual MLX model; the user's Python 3.15 environment is not yet hardware-validated.
- Studio: choose **Trascrizione locale → Modello / Lingua**, then **Trascrivi il parlato**.
- Default: **cache only**. Hugging Face's `snapshot_download(local_files_only=True)` looks up an existing snapshot with no model download. If absent, choose the download checkbox and confirm; then `local_files_only=False` is used for model weights. Audio and video are never uploaded.
- Default model `mlx-community/whisper-large-v3-turbo` (~1.6 GB); `mlx-community/whisper-turbo` is the alternative. CLI can also take a complete absolute local model directory.

## CLI

```bash
pausio transcribe input.mp4 -o output.transcript.json
pausio transcribe input.mp4 -o output.transcript.json --allow-model-download
pausio transcribe input.mp4 -o output.transcript.json --language auto \
  --model mlx-community/whisper-large-v3-turbo --overwrite
```

## Pipeline and contracts

1. Resolve and validate `config.json` and MLX model weights on disk, **before** inference.
2. Extract temporary 16 kHz mono PCM WAV with FFmpeg, leaving the original untouched; securely clean temporary WAV on both success and failure.
3. Run `mlx_whisper.transcribe` with a **local model path**, `word_timestamps=True` and conservative decoding parameters; no HTTP server or ClosedRoom import.
4. Normalize genuine segment and optional word timestamps to source-time integer milliseconds, without synthesizing confidence, speaker labels or word timing. Sidecar provider is `pausio-local`; backend is `mlx-whisper`.
5. Save full ASR text and word timing in the private, media-hash-bound v2 local session checkpoint; restore after restarting Studio. Raw transcripts are never exported in the portable project. Only reviewed caption text/styles enter the canonical `.pausio.json` command history.

## Not yet at parity with ClosedRoom

Nemotron streaming, Silero VAD-guided chunking, diarization, resource-aware queuing, durable transcripts and detailed progress/cancellation are **not implemented** in this first standalone ASR. Tests mock inference; real Italian footage from an A56, accuracy, memory and audio sync need Mac validation. There is no automatic cloud fallback.
