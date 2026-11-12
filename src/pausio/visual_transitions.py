"""Minimal, source-safe visual cut transitions.

A `dip_black` inserts visual fades on the two KEEP halves without
overlapping/repeating frames or touching source audio or caption timestamps.
It is deliberately NOT a cross-dissolve/xfade.
"""
from __future__ import annotations

from typing import Any

MAX_TRANSITIONS=12
ALLOWED_KINDS=frozenset({"dip_black"})
MIN_SEGMENT_MS=1200


def _bounded_int(raw: Any, minimum: int, maximum: int, label: str)->int:
    if type(raw) is not int or not minimum <= raw <= maximum:
        raise ValueError(f"{label} must be an integer in [{minimum}, {maximum}]")
    return raw


def compile_dips(segments: tuple, transitions: list[dict]|None)->dict[int,list[str]]:
    """Compile allowlisted fade stages keyed by source KEEP segment index.

    The event targets exactly one adjacent boundary index (between i and i+1);
    it NEVER shifts output timing or interpolates unrelated source frames.
    """
    if transitions is None:
        return {}
    if not isinstance(transitions,list) or len(transitions)>MAX_TRANSITIONS:
        raise ValueError("Maximum 12 visual cut transitions")
    fades:dict[int,list[str]]={}
    used=set()
    for raw in transitions:
        if not isinstance(raw,dict) or set(raw)!={"boundary_index","kind","duration_ms"}:
            raise ValueError("Transition requires exact typed fields")
        idx=_bounded_int(raw["boundary_index"],0,len(segments)-2,"boundary_index")
        if raw["kind"]!="dip_black" or type(raw["kind"]) is not str:
            raise ValueError("Unsupported visual transition kind")
        dur=_bounded_int(raw["duration_ms"],200,600,"dip duration")
        if idx in used:
            raise ValueError("Duplicate visual transition at boundary")
        used.add(idx)
        left,right=segments[idx],segments[idx+1]
        l=left.end_ms-left.start_ms
        r=right.end_ms-right.start_ms
        if l<MIN_SEGMENT_MS or r<MIN_SEGMENT_MS:
            raise ValueError("Dip transition requires at least 1.2s on both KEEP sides")
        # Half-duration on each side, output duration remains unchanged.
        half=dur/2000
        left_duration=l/1000
        fades.setdefault(idx,[]).append(
            f"fade=t=out:st={left_duration-half:.3f}:d={half:.3f}:color=black"
        )
        fades.setdefault(idx+1,[]).append(
            f"fade=t=in:st=0:d={half:.3f}:color=black"
        )
    # Consecutive dips must never create concurrent ramps on short content.
    for idx in fades:
        if len(fades[idx])>1:
            s=segments[idx]
            length=(s.end_ms-s.start_ms)/1000
            durations=[float(stage.split(":d=")[1].split(":")[0]) for stage in fades[idx]]
            if sum(durations)>min(0.7,length*0.35):
                raise ValueError("Consecutive dips are too dense for this segment")
    return fades
