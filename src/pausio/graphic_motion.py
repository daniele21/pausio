"""Bounded, deterministic entrance/exit motion for editable graphic cards.

No executable ASS/FFmpeg expression can be provided by a project or agent.
The core compiler emits at most 3 non-overlapping ASS dialogue segments per
graphic, with independent entrance/hold/exit phases on the edited timeline.
"""
from __future__ import annotations

from typing import Any

from pausio.captions import _ass_time

MOTION_FIELDS = frozenset({"enter", "exit", "enter_ms", "exit_ms"})
ENTER = frozenset({"none", "fade", "pop", "slide_up", "slide_left"})
EXIT = frozenset({"none", "fade", "shrink", "slide_down", "slide_right"})


def validate_motion(value: Any, duration_ms: int) -> dict:
    """Validate every field before storing typed user editing instructions."""
    if not isinstance(value, dict) or set(value) != MOTION_FIELDS:
        raise ValueError("Motion: parametri incompleti o sconosciuti.")
    if type(value["enter"]) is not str or value["enter"] not in ENTER:
        raise ValueError("Motion: animazione di entrata sconosciuta.")
    if type(value["exit"]) is not str or value["exit"] not in EXIT:
        raise ValueError("Motion: animazione di uscita sconosciuta.")
    for mode, duration_field in (("enter", "enter_ms"), ("exit", "exit_ms")):
        duration = value[duration_field]
        if type(duration) is not int:
            raise ValueError("Motion: durata intera obbligatoria.")
        if value[mode] == "none":
            if duration != 0:
                raise ValueError("Motion: nessuna animazione richiede durata zero.")
        elif not 80 <= duration <= 800:
            raise ValueError("Motion: durata tra 80 e 800 ms.")
    if value["enter_ms"] + value["exit_ms"] > duration_ms - 100:
        raise ValueError("Motion: serve un intervallo visibile tra entrata e uscita.")
    return dict(value)


def _dialogue(start: int, end: int, style: str, tags: str, text: str) -> str:
    return (
        f"Dialogue: 1,{_ass_time(start)},{_ass_time(end)},"
        f"{style},,0,0,0,,{{{tags}}}{text}\n"
    )


def compose_motion_events(
    graphic: dict, *, style: str, font: str, padding: int,
    color: str, text: str, x: int, y: int, size: int,
) -> str:
    """Compile a motion contract to native libass transitions.

    Entrance, hold and exit use independent ASS events because libass supports
    only one \move per event. All values come from the validator's allowlist.
    """
    start, end = graphic["start_ms"], graphic["end_ms"]
    motion = validate_motion(graphic["motion"], end - start)
    enter, leave = motion["enter"], motion["exit"]
    in_ms, out_ms = motion["enter_ms"], motion["exit_ms"]
    # These are generated tags, never project data. Times are absolute.
    base = fr"\an5\fn{font}\fs{size}\c{color}\bord{padding}\shad0"
    hold = base + fr"\pos({x},{y})"
    events: list[str] = []
    if in_ms:
        tags = hold
        if enter == "slide_up":
            tags = base + fr"\move({x},{y+72},{x},{y},0,{in_ms})"
        elif enter == "slide_left":
            tags = base + fr"\move({x-100},{y},{x},{y},0,{in_ms})"
        elif enter == "fade":
            tags += fr"\fad({in_ms},0)"
        elif enter == "pop":
            tags += (
                fr"\fscx82\fscy82"
                fr"\t(0,{in_ms},1.8,\fscx100\fscy100)"
                fr"\fad({min(110, in_ms // 2)},0)"
            )
        events.append(_dialogue(start, start + in_ms, style, tags, text))
    steady_start, steady_end = start + in_ms, end - out_ms
    if steady_end > steady_start:
        events.append(_dialogue(steady_start, steady_end, style, hold, text))
    if out_ms:
        tags = hold
        if leave == "slide_down":
            tags = base + fr"\move({x},{y},{x},{y+72},0,{out_ms})"
        elif leave == "slide_right":
            tags = base + fr"\move({x},{y},{x+100},{y},0,{out_ms})"
        elif leave == "fade":
            tags += fr"\fad(0,{out_ms})"
        elif leave == "shrink":
            tags += (
                fr"\t(0,{out_ms},2,\fscx82\fscy82)"
                fr"\fad(0,{min(120, out_ms // 2)})"
            )
        events.append(_dialogue(end - out_ms, end, style, tags, text))
    return "".join(events)
