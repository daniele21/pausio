"""Deterministic bounded WAV excerpts from a local source or FFmpeg preview.

The caller provides a verified local Path, never a URL or filter expression.
16 kHz mono signed 16-bit PCM, standard wave header, max 6 seconds.
"""
from __future__ import annotations

import io
import subprocess
import wave
from pathlib import Path

from pausio.media import require_binary
from pausio.media_observation import ObservationError

SAMPLE_RATE = 16_000
MIN_MS, MAX_MS = 500, 6_000
MAX_WAV_BYTES = SAMPLE_RATE * 2 * 6 + 128
TIMEOUT_S = 30


def audio_wav(path: Path, start_ms: int, duration_ms: int) -> bytes:
    if (type(start_ms) is not int or type(duration_ms) is not int or
        start_ms < 0 or not MIN_MS <= duration_ms <= MAX_MS or
        path.is_symlink() or not path.is_file()):
        raise ObservationError("Estratto audio locale non valido.")
    args = [
        require_binary("ffmpeg"), "-hide_banner", "-loglevel", "error",
        "-nostdin", "-ss", f"{start_ms/1000:.3f}", "-i", str(path),
        "-t", f"{duration_ms/1000:.3f}", "-map", "0:a:0", "-vn",
        "-ac", "1", "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le",
        "-f", "s16le", "pipe:1",
    ]
    try:
        result = subprocess.run(args, capture_output=True, timeout=TIMEOUT_S,
                                check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ObservationError("Estrazione audio FFmpeg non riuscita.") from exc
    samples = result.stdout
    if (result.returncode or not 0 < len(samples) <= SAMPLE_RATE * 2 * 6
        or len(samples) % 2 != 0):
        raise ObservationError("Nessuna traccia audio disponibile o campione non valido.")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(samples)
    result_bytes = buffer.getvalue()
    if len(result_bytes) > MAX_WAV_BYTES:
        raise ObservationError("Estratto audio troppo grande.")
    return result_bytes
