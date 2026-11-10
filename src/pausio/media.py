"""FFprobe/FFmpeg adapters. Executables are external dependencies, no vendored code."""

from __future__ import annotations

import json
import sys
from array import array
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from pausio.domain import Interval


class MediaError(RuntimeError):
    """Media inspection or processing failed."""


@dataclass(frozen=True, slots=True)
class MediaInfo:
    duration_ms: int
    width: int
    height: int
    has_audio: bool
    video_codec: str
    avg_frame_rate: str

    def as_dict(self) -> dict[str, int | bool | str]:
        return asdict(self)


def require_binary(name: str) -> str:
    exe = shutil.which(name)
    if exe is None:
        raise MediaError(f"{name} not found on PATH; install FFmpeg including ffprobe")
    return exe


def _run(args: list[str], timeout_s: int = 120) -> subprocess.CompletedProcess[str]:
    try:
        p = subprocess.run(
            args, capture_output=True, text=True, check=False, timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        raise MediaError(f"command timed out after {timeout_s}s: {args[0]}") from exc
    except OSError as exc:
        raise MediaError(f"could not start {args[0]}: {exc}") from exc
    if p.returncode:
        raise MediaError(f"{Path(args[0]).name} failed (exit {p.returncode}): {p.stderr[-1500:]}")
    return p


def _milliseconds(value: object) -> int | None:
    try:
        duration = Decimal(str(value))
        if not duration.is_finite() or duration <= 0:
            return None
        return int(duration * 1000)
    except (InvalidOperation, TypeError, ValueError):
        return None


def probe(path: Path) -> MediaInfo:
    if not path.is_file():
        raise MediaError(f"video file not found: {path}")
    p = _run([
        require_binary("ffprobe"), "-v", "error", "-show_streams", "-show_format",
        "-of", "json", str(path),
    ])
    try:
        data = json.loads(p.stdout)
        streams = data["streams"]
        video = next(s for s in streams if s.get("codec_type") == "video")
        audio = any(s.get("codec_type") == "audio" for s in streams)
        duration_ms = _milliseconds(data.get("format", {}).get("duration"))
        if duration_ms is None:
            duration_ms = _milliseconds(video.get("duration"))
        if duration_ms is None:
            raise MediaError("duration missing or invalid in ffprobe response")
        return MediaInfo(
            duration_ms=duration_ms, width=int(video["width"]),
            height=int(video["height"]), has_audio=audio,
            video_codec=str(video.get("codec_name", "unknown")),
            avg_frame_rate=str(video.get("avg_frame_rate", "unknown")),
        )
    except (KeyError, StopIteration, TypeError, ValueError) as exc:
        raise MediaError(f"no valid video stream in {path}: {exc}") from exc


_SILENCE_START = re.compile(r"silence_start:\s*(-?\d+(?:\.\d+)?)")
_SILENCE_END = re.compile(r"silence_end:\s*(-?\d+(?:\.\d+)?)")


def parse_silences(log: str, duration_ms: int) -> list[Interval]:
    """Parse FFmpeg silencedetect events, including trailing unclosed silence."""
    events: list[Interval] = []
    start: int | None = None
    for line in log.splitlines():
        match_start = _SILENCE_START.search(line)
        if match_start:
            start = max(0, int(Decimal(match_start.group(1)) * 1000))
        match_end = _SILENCE_END.search(line)
        if match_end:
            end = min(duration_ms, max(0, int(Decimal(match_end.group(1)) * 1000)))
            # Some ffmpeg versions log only the end for a leading silent section.
            beginning = 0 if start is None else start
            if end > beginning:
                events.append(Interval(beginning, end))
            start = None
    if start is not None and start < duration_ms:
        events.append(Interval(start, duration_ms))
    return events


def detect_silences(
    path: Path, duration_ms: int, *, noise_db: int = -35, min_detection_ms: int = 550,
) -> list[Interval]:
    """FFmpeg signal-level detection: not a speech recognizer or a VAD."""
    if not -90 <= noise_db <= -5:
        raise ValueError("noise_db must be between -90 and -5")
    if min_detection_ms < 50:
        raise ValueError("min_detection_ms must be >= 50")
    duration_sec = min_detection_ms / 1000
    result = _run([
        require_binary("ffmpeg"), "-hide_banner", "-nostdin", "-v", "info",
        "-i", str(path), "-map", "0:a:0", "-vn",
        "-af", f"silencedetect=noise={noise_db}dB:d={duration_sec:.3f}",
        "-f", "null", "-",
    ], timeout_s=900)
    return parse_silences(result.stderr, duration_ms)


def render(
    source: Path, output: Path, segments: tuple[Interval, ...], *,
    has_audio: bool, overwrite: bool = False, dry_run: bool = False,
    size: tuple[int, int] = (1080, 1920),
) -> list[str]:
    """Render ordered intervals in one re-encode; preserve aspect ratio with padding.

    No shell execution, destructive overwrite disabled by default. Intended for
    short vertical social content, not frame-accurate preservation of every codec.
    """
    if not source.is_file():
        raise MediaError(f"source not found: {source}")
    if size not in {(1080, 1920), (540, 960)}:
        raise MediaError("unsupported render size")
    if source.resolve() == output.resolve():
        raise MediaError("input and output must be different files")
    if output.suffix.lower() != ".mp4":
        raise MediaError("output filename must end in .mp4")
    if output.exists() and not overwrite:
        raise MediaError(f"output exists: {output}; pass --overwrite to replace")

    components: list[str] = []
    concat_inputs: list[str] = []
    for i, seg in enumerate(segments):
        start, end = seg.start_ms / 1000, seg.end_ms / 1000
        components.append(
            f"[0:v:0]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS[v{i}]"
        )
        concat_inputs.append(f"[v{i}]")
        if has_audio:
            components.append(
                f"[0:a:0]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[a{i}]"
            )
            concat_inputs.append(f"[a{i}]")
    components.append(
        f"{''.join(concat_inputs)}concat=n={len(segments)}:v=1:a={1 if has_audio else 0}"
        + ("[joinedv][joineda]" if has_audio else "[joinedv]")
    )
    components.append(
        f"[joinedv]fps=30,scale={size[0]}:{size[1]}:force_original_aspect_ratio=decrease,"
        f"pad={size[0]}:{size[1]}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p[outv]"
    )
    def make_args(destination: Path) -> list[str]:
        args = [
            require_binary("ffmpeg"), "-hide_banner", "-nostdin", "-y",
            "-i", str(source), "-filter_complex", ";".join(components),
            "-map", "[outv]",
        ]
        if has_audio:
            args.extend(["-map", "[joineda]", "-c:a", "aac", "-b:a", "160k"])
        args.extend([
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-movflags", "+faststart", str(destination),
        ])
        return args

    if dry_run:
        return make_args(output)

    output.parent.mkdir(parents=True, exist_ok=True)
    # Render to a separate same-filesystem file and publish only after success.
    # A failed encoder cannot corrupt a previous approved export.
    with TemporaryDirectory(prefix=".pausio-", dir=output.parent) as tmp:
        staged_output = Path(tmp) / "render.mp4"
        args = make_args(staged_output)
        _run(args, timeout_s=1200)
        if output.exists() and not overwrite:
            # Another process may have written the destination during rendering.
            raise MediaError(f"output appeared during rendering: {output}")
        staged_output.replace(output)
    return args


def waveform_envelope(
    source: Path,
    duration_ms: int,
    *,
    has_audio: bool,
    bins: int = 900,
) -> list[int]:
    """A compact 0–1000 peak envelope, indexed over ORIGINAL media time.

    Uses FFmpeg to decode into low-rate mono PCM. Never invents a waveform
    from transcription, and never persists or sends raw audio outside localhost.
    To avoid unbounded processing, media longer than 15 minutes yields an
    actionable failure instead of scanning arbitrarily long streams.
    """
    if not has_audio:
        return []
    if not 1 <= bins <= 1800:
        raise ValueError("bins must be in the range 1..1800")
    if not 0 < duration_ms <= 900_000:
        raise MediaError("Waveform disponibile per video fino a 15 minuti.")
    if not source.is_file():
        raise MediaError(f"source not found: {source}")
    command = [
        require_binary("ffmpeg"), "-hide_banner", "-nostdin", "-v", "error",
        "-i", str(source), "-map", "0:a:0", "-vn", "-ac", "1",
        "-ar", "2000", "-f", "s16le", "-c:a", "pcm_s16le", "-",
    ]
    # 15 minutes at 2 kHz mono 16-bit PCM = under 4 MB of stdout.
    try:
        result = subprocess.run(
            command, capture_output=True, check=False, timeout=180,
        )
    except subprocess.TimeoutExpired as exc:
        raise MediaError("Creazione waveform troppo lenta; prova un video più corto.") from exc
    except OSError as exc:
        raise MediaError(f"Impossibile avviare FFmpeg: {exc}") from exc
    if result.returncode:
        raise MediaError(
            "FFmpeg non riesce a leggere la traccia audio: "
            + result.stderr.decode("utf-8", errors="replace")[-500:]
        )
    if not result.stdout:
        return [0] * bins
    samples = array("h")
    samples.frombytes(result.stdout[:len(result.stdout) // 2 * 2])
    if sys.byteorder != "little":
        samples.byteswap()
    peaks = [0] * bins
    # The envelope follows source duration, even when encoded audio has
    # slightly shorter/longer sample counts.
    expected_samples = max(1, round(duration_ms / 1000 * 2000))
    for position, value in enumerate(samples):
        bucket = min(bins - 1, position * bins // expected_samples)
        peaks[bucket] = max(peaks[bucket], abs(value))
    return [min(1000, round(value * 1000 / 32768)) for value in peaks]
