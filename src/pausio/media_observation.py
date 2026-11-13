"""Bounded, read-only FFmpeg video observation for the local MCP tunnel.

Only samples one JPEG frame of a verified local video. Never opens a URL or
uploads media. StudioWorkspace owns consent, source binding, rate limits and
preview freshness; this helper owns only safe FFmpeg extraction.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from pausio.media import require_binary

MAX_JPEG_BYTES = 256 * 1024
WIDTH, HEIGHT = 540, 960
TIMEOUT_S = 25


class ObservationError(ValueError):
    """Public, non-sensitive media observation failure."""


def frame_jpeg(path: Path, at_ms: int) -> bytes:
    if (type(at_ms) is not int or at_ms < 0 or
        path.is_symlink() or not path.is_file()):
        raise ObservationError("Frame locale non disponibile.")
    ffmpeg = require_binary("ffmpeg")
    args = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
        "-ss", f"{at_ms / 1000:.3f}", "-i", str(path),
        "-map", "0:v:0", "-frames:v", "1", "-threads:v", "1",
        "-vf", f"scale=w={WIDTH}:h={HEIGHT}:force_original_aspect_ratio=decrease",
        "-q:v", "10", "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1",
    ]
    try:
        result = subprocess.run(
            args, capture_output=True, timeout=TIMEOUT_S, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ObservationError("Estrazione frame FFmpeg non riuscita.") from exc
    data = result.stdout
    if (result.returncode or not 4 <= len(data) <= MAX_JPEG_BYTES or
        not data.startswith(b"\xff\xd8") or not data.endswith(b"\xff\xd9")):
        # Do not leak FFmpeg stderr: it may contain private macOS media paths.
        raise ObservationError("Frame JPEG non disponibile o troppo grande.")
    return data
