"""Deterministic FFmpeg media-layer motion, shared by images and video B-roll.

Strict numeric-only graph compiler. All user data is validated first by the
portable project reducer. Source alpha fades are computed in asset-local time
BEFORE output-timeline PTS offset; slides use absolute edited-output seconds.
"""
from __future__ import annotations

from typing import Any

from pausio.graphic_motion import validate_motion

MEDIA_ENTER = frozenset({"none", "fade", "slide_up", "slide_left"})
MEDIA_EXIT = frozenset({"none", "fade", "slide_down", "slide_right"})


def validate_media_motion(raw: Any, duration_ms: int) -> dict:
    """Reuse v13 contract, limiting media to compositable safe transforms."""
    motion = validate_motion(raw, duration_ms)
    if motion["enter"] not in MEDIA_ENTER or motion["exit"] not in MEDIA_EXIT:
        raise ValueError("Motion media: per immagini/video usa fade o slide.")
    return motion


def compile_media_motion(
    clip: dict, *, size: tuple[int, int], x: str, y: str
) -> tuple[str, str, str]:
    """Return (asset-local RGBA fade filters, output-absolute x, y expressions).

    Input is already 30fps RGBA with PTS starting at zero. Compose filters
    before shifting PTS by clip.start_ms. In particular, do not add an
    absolute offset to a fade: FFmpeg interprets fade's st locally.
    """
    motion = clip.get("motion")
    if motion is None:
        return "", x, y
    validate_media_motion(motion, clip["duration_ms"])
    start = clip["start_ms"] / 1000.0
    end = (clip["start_ms"] + clip["duration_ms"]) / 1000.0
    enter_ms, exit_ms = motion["enter_ms"], motion["exit_ms"]
    filters = []
    if enter_ms:
        enter_seconds = enter_ms / 1000.0
        filters.append(f"fade=t=in:st=0:d={enter_seconds:.3f}:alpha=1")
    if exit_ms:
        exit_seconds = exit_ms / 1000.0
        out_start = clip["duration_ms"] / 1000.0 - exit_seconds
        filters.append(
            f"fade=t=out:st={out_start:.3f}:d={exit_seconds:.3f}:alpha=1"
        )
    # Native overlay expressions vary positions by frame; no dynamic
    # per-frame resizing, which some FFmpeg builds cannot support.
    distance = max(24, round(size[0] * 0.075))
    if motion["enter"] in {"slide_left", "slide_up"}:
        direction = "x" if motion["enter"] == "slide_left" else "y"
        base = x if direction == "x" else y
        # From -distance to the configured position, clamped to the intro.
        position = (
            f"({base})-{distance}*max(0\\,1-(t-{start:.3f})/"
            f"{enter_ms / 1000:.3f})"
        )
        if direction == "x":
            x = position
        else:
            y = position
    if motion["exit"] in {"slide_right", "slide_down"}:
        direction = "x" if motion["exit"] == "slide_right" else "y"
        base = x if direction == "x" else y
        # At exit start the displacement is zero; reach +distance at end.
        displacement = (
            f"{distance}*min(1\\,max(0\\,(t-{end - exit_ms / 1000:.3f})/"
            f"{exit_ms / 1000:.3f}))"
        )
        position = f"({base})+{displacement}"
        if direction == "x":
            x = position
        else:
            y = position
    return ",".join(filters), x, y
