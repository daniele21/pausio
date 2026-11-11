"""Independent, opt-in local transcription for Pausio Studio.

Architecture informed by ClosedRoom's MLX Whisper pipeline; Pausio owns
this adapter, model resolution, result validation and audio extraction.
ClosedRoom is NOT imported, installed, contacted or launched.

Models are cache-only by default. A network model download requires an
explicit per-operation user opt-in.
"""

from __future__ import annotations

import platform
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from pausio.media import MediaError, _run, probe, require_binary

DEFAULT_ASR_MODEL = "mlx-community/whisper-large-v3-turbo"
ASR_MODELS = (
    "mlx-community/whisper-large-v3-turbo",
    "mlx-community/whisper-turbo",
)
LANGUAGES = {"it", "en", "es", "fr", "de", "auto"}


class LocalASRError(RuntimeError):
    """Cannot run local MLX ASR or the model returned malformed timestamps."""


def validate_asr_settings(raw: object | None = None) -> dict[str, Any]:
    """Strict Studio input; downloads cannot be requested implicitly."""
    if raw is None:
        return {"model": DEFAULT_ASR_MODEL, "language": "it",
                "allow_model_download": False}
    if not isinstance(raw, dict) or set(raw) != {
        "model", "language", "allow_model_download"
    }:
        raise ValueError("Impostazioni ASR non valide.")
    model = raw["model"]
    if not isinstance(model, str) or model not in ASR_MODELS:
        raise ValueError("Modello ASR non supportato nella UI.")
    language = raw["language"]
    if not isinstance(language, str) or language not in LANGUAGES:
        raise ValueError("Lingua di trascrizione non supportata.")
    if type(raw["allow_model_download"]) is not bool:
        raise ValueError("Il consenso al download deve essere esplicito.")
    return dict(raw)


def _check_local_runtime() -> None:
    if sys.platform != "darwin" or platform.machine() != "arm64":
        raise LocalASRError(
            "MLX Whisper richiede un Mac Apple Silicon. "
            "Nessun servizio ClosedRoom viene utilizzato."
        )


def _local_model_directory(model: str, *, allow_download: bool) -> Path:
    """Resolve to a local snapshot, never pass a remote repo to MLX Whisper."""
    if model not in ASR_MODELS:
        # Explicit CLI local directory, not an arbitrary remote repo.
        path = Path(model).expanduser()
        if not path.is_absolute() or not path.is_dir():
            raise LocalASRError(
                "Scegli un modello MLX supportato oppure una cartella locale assoluta."
            )
        resolved = path.resolve()
    else:
        try:
            from huggingface_hub import snapshot_download
        except ImportError as exc:
            raise LocalASRError(
                "ASR non installato: esegui python -m pip install -e '.[asr]' "
                "in un ambiente Python 3.11–3.13."
            ) from exc
        try:
            # False = disk cache only, no HTTP and no hidden model downloads.
            # True = deliberate UI checkbox or --allow-model-download flag.
            resolved = Path(snapshot_download(
                repo_id=model, local_files_only=not allow_download
            )).resolve()
        except Exception as exc:
            if not allow_download:
                raise LocalASRError(
                    "Modello non presente nella cache locale. "
                    "In Studio abilita «Scarica modello (una volta)» "
                    "oppure usa --allow-model-download nella CLI."
                ) from exc
            raise LocalASRError(
                "Impossibile scaricare il modello MLX selezionato. "
                "Controlla rete, spazio disco e disponibilità del modello."
            ) from exc
    if not (resolved / "config.json").is_file() or not any(
        resolved.glob("*.safetensors")
    ) and not any(resolved.glob("*.npz")):
        raise LocalASRError("Modello locale incompleto: config e pesi MLX necessari.")
    return resolved


def _milliseconds(value: object, label: str) -> int:
    if value is None or isinstance(value, bool):
        raise LocalASRError(f"{label}: secondi non validi")
    try:
        seconds = Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation) as exc:
        raise LocalASRError(f"{label}: secondi non numerici") from exc
    if not seconds.is_finite() or seconds < 0:
        raise LocalASRError(f"{label}: secondi negativi o non finiti")
    return int(seconds * 1000)


def _timed_item(raw: object, label: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise LocalASRError(f"{label}: segmento non valido")
    start = _milliseconds(raw.get("start"), f"{label}.start")
    end = _milliseconds(raw.get("end"), f"{label}.end")
    if end <= start:
        raise LocalASRError(f"{label}: fine prima dell'inizio")
    text = raw.get("text", raw.get("word"))
    if not isinstance(text, str):
        raise LocalASRError(f"{label}: testo non valido")
    return {"start_ms": start, "end_ms": end, "text": text}


def normalize_local_transcript(
    payload: object, *, source: Path, duration_ms: int, model: str
) -> dict[str, Any]:
    """Preserve only real timestamps from MLX Whisper; never fabricate words."""
    if not isinstance(payload, dict):
        raise LocalASRError("Risposta ASR non valida.")
    if not isinstance(payload.get("text"), str) or not isinstance(
        payload.get("segments"), list
    ):
        raise LocalASRError("Il modello deve restituire testo e segmenti.")
    segments: list[dict[str, Any]] = []
    previous_start = -1
    words_count = 0
    for index, row in enumerate(payload["segments"]):
        item = _timed_item(row, f"segmento {index}")
        start, end = item["start_ms"], item["end_ms"]
        if start < previous_start or end > duration_ms + 2000:
            raise LocalASRError("Timestamp ASR fuori ordine o oltre il video.")
        previous_start = start
        if "words" in row:
            if not isinstance(row["words"], list):
                raise LocalASRError("Timestamp parole non validi.")
            words = [_timed_item(w, "parola") for w in row["words"]]
            if any(
                w["start_ms"] < start - 1000 or w["end_ms"] > end + 1000
                for w in words
            ):
                raise LocalASRError("Timestamp parole fuori dal segmento.")
            item["words"] = words
            words_count += len(words)
        segments.append(item)
    language = payload.get("language")
    if language is not None and not isinstance(language, str):
        raise LocalASRError("Lingua rilevata non valida.")
    return {
        "schema_version": 1,
        "source": str(source.resolve()),
        "source_duration_ms": duration_ms,
        "provider": "pausio-local",
        "backend": "mlx-whisper",
        "model": model,
        "language": language,
        "text": payload["text"],
        "segments": segments,
        "word_timestamps_available": words_count > 0,
        "warnings": [] if words_count else ["word_alignment_unavailable"],
    }


def _mlx_transcribe(wav: Path, model_path: Path, *, language: str) -> dict:
    try:
        import mlx_whisper
    except ImportError as exc:
        raise LocalASRError(
            "MLX Whisper non installato: usa python -m pip install -e '.[asr]' "
            "su un Mac Apple Silicon."
        ) from exc
    try:
        # Path is an already resolved local directory: MLX cannot fetch
        # weights from a remote model name at this boundary.
        result = mlx_whisper.transcribe(
            str(wav),
            path_or_hf_repo=str(model_path),
            language=None if language == "auto" else language,
            task="transcribe",
            word_timestamps=True,
            temperature=0.0,
            condition_on_previous_text=False,
            compression_ratio_threshold=2.2,
            logprob_threshold=-0.7,
            no_speech_threshold=0.35,
            verbose=False,
        )
    except Exception as exc:
        raise LocalASRError(f"Trascrizione MLX fallita: {str(exc)[:180]}") from exc
    if not isinstance(result, dict):
        raise LocalASRError("MLX Whisper non ha restituito un risultato valido.")
    return result


def transcribe_video_local(
    source: Path, *, model: str = DEFAULT_ASR_MODEL, language: str = "it",
    allow_model_download: bool = False
) -> dict[str, Any]:
    """Transcribe on-device, no localhost server or remote ASR API."""
    if not isinstance(model, str) or not model.strip() or not isinstance(
        language, str
    ) or language not in LANGUAGES or type(allow_model_download) is not bool:
        raise ValueError("Impostazioni ASR non valide.")
    _check_local_runtime()
    # Validate model and only then touch media; an uncached model fails early.
    model_path = _local_model_directory(
        model, allow_download=allow_model_download
    )
    source = Path(source).resolve()
    info = probe(source)
    if not info.has_audio:
        raise MediaError("Il video non contiene una traccia audio.")
    with TemporaryDirectory(prefix="pausio-local-asr-") as directory:
        wav = Path(directory) / "audio.wav"
        _run([
            require_binary("ffmpeg"), "-hide_banner", "-nostdin", "-v", "error",
            "-y", "-i", str(source), "-map", "0:a:0", "-vn",
            "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav),
        ], timeout_s=900)
        result = _mlx_transcribe(wav, model_path, language=language)
    return normalize_local_transcript(
        result, source=source, duration_ms=info.duration_ms, model=model
    )
