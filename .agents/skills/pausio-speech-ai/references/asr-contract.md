# Standalone local ASR contract in Pausio

Pausio's active implementation is `src/pausio/local_asr.py`; `src/pausio/studio.py` calls it directly, with no ClosedRoom import, HTTP call or server requirement.

## Existing design references (not runtime dependencies)

- ClosedRoom `dev` [transcriber](https://github.com/daniele21/closedroom/blob/dev/src/local_asr_server/transcriber.py) — MLX Whisper options, model caching and sample-level alignment
- ClosedRoom `dev` [ASR model capabilities](https://github.com/daniele21/closedroom/blob/dev/src/local_asr_server/asr_models.py) — Whisper/Nemotron backend selection
- [MLX Whisper implementation](https://github.com/ml-explore/mlx-examples/tree/main/whisper) — direct model load and word timestamps
- [MLX Whisper Large v3 Turbo](https://huggingface.co/mlx-community/whisper-large-v3-turbo) — model weights

## Runtime contract

- Optional `mlx-whisper` and `huggingface-hub` packages (no ASR dependencies in the basic installation).
- An explicit model name allowlist or a local **absolute directory** (CLI); UI uses fixed choices.
- Cache-only by default. Only a user-approved download of weights may use the network; video/audio never leaves the Mac.
- `mlx_whisper.transcribe(str(wav), path_or_hf_repo=str(local_model_path), word_timestamps=True, ...)` with 16kHz mono WAV.
- Normalized sidecar: `provider: pausio-local`, `backend: mlx-whisper`, `model`, `language`, `text`, source-time millisecond `segments`, optional `words`, `word_timestamps_available` and warnings.
- No fabricated word alignment. No effect on automatic cuts without a separate user-reviewed instruction.
- CI uses fake inference. Real-model Italian speech performance and Python 3.15 compatibility are not yet proven.

See `docs/LOCAL_ASR.md` for user instructions.
