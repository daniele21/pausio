"""Safe, numeric-only FFmpeg visual effects for KEEP segments.

Source-anchored source_ms/segment_index events are already selected/validated
by project_commands in Studio. This module repeats critical validation for
standalone callers; no user-supplied filtergraph expressions are accepted.
"""
from __future__ import annotations

from typing import Any

MAX_RENDER_FX = 18
FPS = 30


def _integer(value: Any, lo: int, hi: int, name: str) -> int:
    if type(value) is not int or not lo <= value <= hi:
        raise ValueError(f"video FX {name} outside the allowed bounds")
    return value


def prepare_motion_fx(
    segments: tuple[Any, ...], video_fx: list[dict] | None
) -> dict[int, list[dict]]:
    """Validate renderer-facing events and map to source KEEP region indices.

    Renderer input uses the internal zero-based segment_index; the portable
    project uses a segment_id, which Studio resolves before calling render().
    """
    if video_fx is None:
        return {}
    if not isinstance(video_fx, list) or len(video_fx) > MAX_RENDER_FX:
        raise ValueError("Maximum 18 validated video effects")
    grouped: dict[int, list[dict]] = {}
    fields = {"segment_index", "start_ms", "end_ms", "kind",
              "start_scale_pct", "end_scale_pct", "anchor_x_pct", "anchor_y_pct"}
    for entry in video_fx:
        if not isinstance(entry, dict) or set(entry) != fields:
            raise ValueError("Video FX has unknown or missing parameters")
        i = _integer(entry["segment_index"], 0, len(segments)-1, "segment index")
        a = _integer(entry["start_ms"], 0, 172_800_000, "source start")
        b = _integer(entry["end_ms"], 0, 172_800_000, "source end")
        segment = segments[i]
        if not (segment.start_ms <= a < b <= segment.end_ms and
                250 <= b - a <= 60000):
            raise ValueError("Video FX outside source KEEP or invalid duration")
        if type(entry["kind"]) is not str or entry["kind"] not in ("punch", "slow_push", "ease_push", "ratchet"):
            raise ValueError("Unsupported video FX operation")
        scales = [
            _integer(entry[key], 100, 130, key)
            for key in ("start_scale_pct", "end_scale_pct")
        ]
        if entry["kind"] == "punch" and scales[0] != scales[1]:
            raise ValueError("Punch requires a constant scale")
        for key in ("anchor_x_pct", "anchor_y_pct"):
            _integer(entry[key], 0, 100, key)
        grouped.setdefault(i, []).append(dict(entry))
    for i, effects in grouped.items():
        effects.sort(key=lambda e:(e["start_ms"], e["end_ms"]))
        for a,b in zip(effects,effects[1:]):
            if a["end_ms"] > b["start_ms"]:
                raise ValueError("Overlapping video motion events")
    return grouped


def _window(effect: dict, source_start_ms: int) -> tuple[int,int]:
    # With CFR=30 and start_ms expressed on the original timeline,
    # round to nearest output frame rather than evaluating source PTS in VFR.
    a = round((effect["start_ms"]-source_start_ms)*FPS/1000)
    b = round((effect["end_ms"]-source_start_ms)*FPS/1000)
    return a,max(a+1,b)


def motion_filter(
    effects: list[dict], source_start_ms: int,
    size: tuple[int,int]
) -> str:
    """Produce one allowlisted, FFmpeg-escaped zoompan stage.

    zoompan on=output frame index, d=1; source frames are first normalized to
    CFR 30. Captions are composed AFTER this stage, never enlarged with a face.
    """
    width,height = size
    if (width,height) not in ((540,960),(1080,1920)):
        raise ValueError("Unsupported video size")
    if not effects:
        return ""
    # Escaping internal commas is essential for FFmpeg filtergraph lexer.
    # Never interpolate raw user-provided expression fragments.
    z="1"
    anchor_x="0.5"
    anchor_y="0.5"
    for fx in reversed(effects):
        start,end = _window(fx,source_start_ms)
        initial=fx["start_scale_pct"]/100
        final=fx["end_scale_pct"]/100
        if fx["kind"]=="punch":
            zoom=f"{initial:.3f}"
        else:
            frames=max(1,end-start-1)
            fraction=f"min(1\\,max(0\\,(on-{start})/{frames}))"
            if fx["kind"]=="ease_push":
                # Smoothstep: C1-continuous bounded acceleration. No overshoot.
                phase=f"({fraction})"
                progress=f"({phase}*{phase}*(3-2*{phase}))"
            elif fx["kind"]=="ratchet":
                # Three deliberate discrete steps. No strobing or repeated
                # fast flashes. Each step is held >= 83ms (250ms minimum).
                progress=f"(floor(3*({fraction}))/3)"
            else:
                progress=fraction
            zoom=f"({initial:.3f}+({final-initial:.3f})*({progress}))"
        in_window=f"between(on\\,{start}\\,{end-1})"
        z=f"if({in_window}\\,{zoom}\\,{z})"
        anchor_x=f"if({in_window}\\,{fx['anchor_x_pct']/100:.3f}\\,{anchor_x})"
        anchor_y=f"if({in_window}\\,{fx['anchor_y_pct']/100:.3f}\\,{anchor_y})"
    # During a 1x window, x/y evaluate to 0. During zoom, valid crop window
    # is (iw-iw/zoom); multiplying 0..1 guarantees no out-of-bounds sampling.
    return (
        f"zoompan=z='{z}':"
        f"x='(iw-iw/zoom)*({anchor_x})':"
        f"y='(ih-ih/zoom)*({anchor_y})':"
        f"d=1:s={width}x{height}:fps={FPS},format=yuv420p"
    )
