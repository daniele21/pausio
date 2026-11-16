"""Validated local video B-roll layers for the canonical FFmpeg composition.

Video B-roll is timed on the EDITED output timeline. Assets remain on disk;
portable project events hold only an SHA-256, safe name and bounded numeric
render properties. The original talking-head audio always stays authoritative.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pausio.media_motion import validate_media_motion, compile_media_motion

MAX_VIDEO_BROLL = 6
MAX_BROLL_BYTES = 256 * 1024 * 1024
VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".mkv", ".webm"})
VIDEO_BROLL_FIELDS = frozenset({
    "id", "asset_sha256", "filename", "start_ms", "duration_ms",
    "media_in_ms", "mode", "x_pct", "y_pct", "width_pct",
})
_ID = re.compile(r"^[0-9a-f]{32}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")


def validate_video_broll(value: Any, output_ms: int) -> dict:
    """Reject arbitrary paths, expressions, unknown fields and invalid times."""
    if type(output_ms) is not int or not 0 < output_ms <= 172_800_000:
        raise ValueError("Video B-roll: durata del montaggio non valida.")
    if not isinstance(value, dict) or set(value) not in (VIDEO_BROLL_FIELDS, VIDEO_BROLL_FIELDS | {"motion"}):
        raise ValueError("Video B-roll: campi non validi.")
    if (not isinstance(value["id"], str) or not _ID.fullmatch(value["id"])
            or not isinstance(value["asset_sha256"], str)
            or not _SHA.fullmatch(value["asset_sha256"])):
        raise ValueError("Video B-roll: identificativo o SHA-256 non valido.")
    name = value["filename"]
    if (not isinstance(name, str) or not 1 <= len(name) <= 160
            or "/" in name or "\\" in name or name in {".", ".."}
            or any(ord(c) < 32 or ord(c) == 127 for c in name)
            or Path(name).suffix.lower() not in VIDEO_EXTENSIONS):
        raise ValueError("Video B-roll: nome file o formato non valido.")
    for field in ("start_ms", "duration_ms", "media_in_ms",
                  "x_pct", "y_pct", "width_pct"):
        if type(value[field]) is not int:
            raise ValueError(f"Video B-roll: {field} deve essere un intero.")
    start, duration, media_in = (value[k] for k in
                                ("start_ms", "duration_ms", "media_in_ms"))
    if not (0 <= start < output_ms and 400 <= duration <= 20_000
            and start + duration <= output_ms
            and 0 <= media_in <= 172_800_000 - duration):
        raise ValueError("Video B-roll: tempi fuori dai limiti.")
    if type(value["mode"]) is not str or value["mode"] not in {"fullscreen", "pip"}:
        raise ValueError("Video B-roll: modalità non supportata.")
    for field, minimum, maximum in (
        ("x_pct", 0, 100), ("y_pct", 0, 100), ("width_pct", 20, 80)
    ):
        if not minimum <= value[field] <= maximum:
            raise ValueError(f"Video B-roll: {field} fuori limite.")
    if "motion" in value:
        validate_media_motion(value["motion"], duration)
    return dict(value)


def validate_video_brolls(rows: Any, output_ms: int) -> None:
    if not isinstance(rows, list) or len(rows) > MAX_VIDEO_BROLL:
        raise ValueError("Video B-roll: massimo sei clip.")
    ids: set[str] = set()
    for value in rows:
        item = validate_video_broll(value, output_ms)
        if item["id"] in ids:
            raise ValueError("Video B-roll: ID duplicato.")
        ids.add(item["id"])
    # V1: one video B-roll layer at a time; still images may be layered above.
    ordered = sorted(rows, key=lambda item: item["start_ms"])
    for previous, following in zip(ordered, ordered[1:]):
        if previous["start_ms"] + previous["duration_ms"] > following["start_ms"]:
            raise ValueError("Video B-roll sovrapposti: scegli intervalli separati.")


def compose_video_broll(
    filters: list[str], *, base_label: str, videos: list[tuple[Path, dict]],
    first_input: int, size: tuple[int, int], final_label: str
) -> None:
    """Append safe numeric-only filters; source clip audio is never connected."""
    previous = base_label
    for i, (_, clip) in enumerate(videos):
        start = clip["start_ms"] / 1000
        end = (clip["start_ms"] + clip["duration_ms"]) / 1000
        clip_in = clip["media_in_ms"] / 1000
        clip_out = (clip["media_in_ms"] + clip["duration_ms"]) / 1000
        width, height = size
        if clip["mode"] == "fullscreen":
            fit = (f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                   f"crop={width}:{height},setsar=1")
            x, y = "0", "0"
        else:
            pip_width = max(2, round(width * clip["width_pct"] / 100) // 2 * 2)
            pip_height = max(2, round(height * 0.58) // 2 * 2)
            fit = (f"scale={pip_width}:{pip_height}:"
                   "force_original_aspect_ratio=decrease,setsar=1")
            x = f"(main_w-overlay_w)*{clip['x_pct'] / 100:.3f}"
            y = f"(main_h-overlay_h)*{clip['y_pct'] / 100:.3f}"
        filters.append(
            f"[{first_input + i}:v:0]trim=start={clip_in:.3f}:end={clip_out:.3f},"
            f"setpts=PTS-STARTPTS+{start:.3f}/TB,fps=30,{fit},format=rgba[rollsrc{i}]"
        )
        target = final_label if i == len(videos) - 1 else f"[rollstage{i}]"
        filters.append(
            f"{previous}[rollsrc{i}]overlay=x='{x}':y='{y}':"
            f"enable='between(t\\,{start:.3f}\\,{end:.3f})':"
            f"eof_action=pass:repeatlast=0:shortest=0:format=auto"
            + (",format=yuv420p" if i == len(videos) - 1 else "")
            + target
        )
        previous = target
