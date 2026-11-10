"""Local same-machine adapter to ClosedRoom's *existing* transcription API.

API contract verified against daniele21/closedroom, branch dev (2026-11-10):
POST /v1/audio/transcriptions/path, request TranscribePathRequest and
response_format=verbose_json. Pausio does not embed ASR models or rerun Whisper.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

from pausio.media import MediaError, _run, probe, require_binary

DEFAULT_CLOSEDROOM_URL = "http://127.0.0.1:1236"
CLOSEDROOM_ENDPOINT = "/v1/audio/transcriptions/path"
MAX_RESPONSE_BYTES = 16 * 1024 * 1024


class ClosedRoomError(RuntimeError):
    """ClosedRoom unavailable or response incompatible with Pausio."""


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _endpoint(origin: str) -> str:
    """Only direct loopback requests; cannot accidentally send video data to cloud."""
    try:
        u = urlsplit(origin)
        port = u.port
    except ValueError as exc:
        raise ValueError("invalid ClosedRoom URL") from exc
    if (
        u.scheme != "http" or u.hostname not in {"127.0.0.1", "::1"}
        or port is None or u.username is not None or u.password is not None
        or u.path not in {"", "/"} or u.query or u.fragment
    ):
        raise ValueError("ClosedRoom URL must be loopback HTTP, e.g. http://127.0.0.1:1236")
    return f"http://{u.netloc}{CLOSEDROOM_ENDPOINT}"


def _milliseconds(value: object, label: str) -> int:
    if value is None or isinstance(value, bool):
        raise ClosedRoomError(f"{label} must contain finite non-negative seconds")
    try:
        seconds = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ClosedRoomError(f"{label} must contain numeric seconds") from exc
    if not seconds.is_finite() or seconds < 0:
        raise ClosedRoomError(f"{label} must contain finite non-negative seconds")
    return int(seconds * 1000)


def _segment(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ClosedRoomError(f"{label} must be an object")
    start = _milliseconds(value.get("start"), f"{label}.start")
    end = _milliseconds(value.get("end"), f"{label}.end")
    if end <= start:
        raise ClosedRoomError(f"{label} end must exceed start")
    text = value.get("text", value.get("word", ""))
    if not isinstance(text, str):
        raise ClosedRoomError(f"{label}.text must be a string")
    return {"start_ms": start, "end_ms": end, "text": text}


def normalize_transcription(
    result: object, *, source: Path, duration_ms: int
) -> dict[str, object]:
    """Normalize ClosedRoom segment/word seconds to source-time milliseconds.

    Words are included only if ClosedRoom actually returned their alignment.
    """
    if not isinstance(result, dict) or result.get("asr_provider") != "local":
        raise ClosedRoomError("ClosedRoom must return a confirmed local-ASR response")
    if not isinstance(result.get("text"), str) or not isinstance(result.get("segments"), list):
        raise ClosedRoomError("ClosedRoom verbose_json requires text and segments")
    segments: list[dict[str, object]] = []
    last_start = -1
    word_count = 0
    for index, segment in enumerate(result["segments"]):
        item = _segment(segment, f"segments[{index}]")
        start, end = int(item["start_ms"]), int(item["end_ms"])
        if start < last_start or end > duration_ms + 2000:
            raise ClosedRoomError("ClosedRoom returned inconsistent source segment timestamps")
        last_start = start
        if "words" in segment:
            words = segment["words"]
            if not isinstance(words, list):
                raise ClosedRoomError("ClosedRoom segment words must be a list")
            normalized_words = [_segment(w, "word") for w in words]
            for word in normalized_words:
                if int(word["start_ms"]) < start - 1000 or int(word["end_ms"]) > end + 1000:
                    raise ClosedRoomError("word timestamps inconsistent with parent segment")
            item["words"] = normalized_words
            word_count += len(normalized_words)
        segments.append(item)
    for name in ("model", "backend", "language"):
        if result.get(name) is not None and not isinstance(result[name], str):
            raise ClosedRoomError(f"ClosedRoom {name} field must be text or null")
    return {
        "schema_version": 1,
        "source": str(source.resolve()),
        "source_duration_ms": duration_ms,
        "provider": "closedroom-local",
        "upstream_api": CLOSEDROOM_ENDPOINT,
        "model": result.get("model"),
        "backend": result.get("backend"),
        "language": result.get("language"),
        "text": result["text"],
        "segments": segments,
        "word_timestamps_available": word_count > 0,
        "warnings": [] if word_count else ["word_alignment_unavailable"],
    }


def _request_closedroom(
    wav: Path, *, url: str, language: str, model: str | None
) -> dict[str, object]:
    body: dict[str, object] = {
        "file": str(wav.resolve()),
        "language": language,
        "task": "transcribe",
        "response_format": "verbose_json",
        "word_timestamps": True,
        "asr_provider": "local",
        "diarization_provider": "disabled",
        "vad_guided": True,
        "vad_post_filter": True,
    }
    if model is not None:
        body["model"] = model
    request = urllib.request.Request(
        _endpoint(url),
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    # Ignore HTTP_PROXY and forbid redirects: this adapter is *strictly* local.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _RejectRedirects())
    try:
        with opener.open(request, timeout=900) as response:
            if response.status != 200:
                raise ClosedRoomError(f"ClosedRoom HTTP {response.status}")
            data = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise ClosedRoomError(f"ClosedRoom HTTP {exc.code}; check the local server") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ClosedRoomError("ClosedRoom unavailable: start its local API on 127.0.0.1:1236") from exc
    if len(data) > MAX_RESPONSE_BYTES:
        raise ClosedRoomError("ClosedRoom returned an oversized response")
    try:
        result = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ClosedRoomError("ClosedRoom returned invalid JSON") from exc
    if not isinstance(result, dict):
        raise ClosedRoomError("ClosedRoom returned invalid JSON shape")
    return result


def transcribe_video_with_closedroom(
    source: Path, *, url: str = DEFAULT_CLOSEDROOM_URL,
    language: str = "it", model: str | None = None
) -> dict[str, object]:
    """Extract local WAV for ClosedRoom's path API, then discard the temporary file."""
    _endpoint(url)  # Reject remote URLs before reading the source.
    if not isinstance(language, str) or not language:
        raise ValueError("language must be non-empty")
    source = source.resolve()
    info = probe(source)
    if not info.has_audio:
        raise MediaError("source video has no audio track")
    with TemporaryDirectory(prefix="pausio-asr-") as directory:
        wav = Path(directory) / "audio.wav"
        _run([
            require_binary("ffmpeg"), "-hide_banner", "-nostdin", "-v", "error",
            "-y", "-i", str(source), "-map", "0:a:0", "-vn",
            "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav),
        ], timeout_s=900)
        payload = _request_closedroom(wav, url=url, language=language, model=model)
    return normalize_transcription(payload, source=source, duration_ms=info.duration_ms)
