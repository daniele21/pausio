"""Bounded, deterministic integer count-up used by the v15 metric_countup scene.

Only a *literal*, already-approved integer is animated. An unparseable label
is left unchanged. Timing, colors, fonts and libass tags are code-owned, never
project-provided expressions; no new editing command is introduced here.
"""
from __future__ import annotations

import re
from typing import Callable

from pausio.captions import _ass_color

_INTEGER = re.compile(r"(?:0|[1-9][0-9]*|[1-9][0-9]{0,2}(?:\.[0-9]{3})+)\Z")
MAX_COUNT = 9_999_999


def _parse_integer(value: str) -> tuple[int, bool] | None:
    if type(value) is not str or not _INTEGER.fullmatch(value):
        return None
    number = int(value.replace(".", ""))
    if number > MAX_COUNT:
        return None
    return number, "." in value


def is_valid_counter_value(value: object) -> bool:
    """Only unsigned literal integers up to 9,999,999 are animated."""
    return _parse_integer(value) is not None if type(value) is str else False


def countup_frames(value: str, start_ms: int, end_ms: int) -> list[tuple[int, int, str]]:
    """Partition [start,end) into deterministic, flicker-free integer labels.

    Last label is always the exact caller-provided text; non-integer copy is
    never interpreted as a number. ASS timestamps are quantized to 10ms.
    """
    if (type(start_ms) is not int or type(end_ms) is not int or
        start_ms < 0 or end_ms <= start_ms):
        raise ValueError("Intervallo del contatore non valido.")
    parsed = _parse_integer(value)
    elapsed = end_ms - start_ms
    if parsed is None or parsed[0] == 0 or elapsed < 850:
        return [(start_ms, end_ms, value)]
    target, grouping = parsed
    travel = min(900, elapsed - 350)
    count = 12
    # At least 60ms per visible frame, rounded to centisecond for libass.
    if travel < count * 60:
        count = max(5, travel // 60)
    anchors = [start_ms + round(i * travel / count / 10) * 10
               for i in range(count + 1)]
    rows: list[tuple[int, int, str]] = []
    for i in range(count):
        progress = (i + 1) / count
        # Ease-out cubic; do not rely on floating-point display formatting.
        current = min(target, round(target * (1 - (1 - progress) ** 3)))
        text = format(current, ",").replace(",", ".") if grouping else str(current)
        begin = anchors[i]
        finish = anchors[i + 1] if i < count - 1 else end_ms
        if i == count - 1:
            text = value
        if rows and rows[-1][2] == text:
            prior = rows[-1]
            rows[-1] = (prior[0], finish, text)
        else:
            rows.append((begin, finish, text))
    return rows


def compose_counter_events(
    value: str, start_ms: int, end_ms: int,
    event: Callable[[int, int, int, str, str], str],
    safe: Callable[[str], str], *,
    x: int = 540, y: int = 810, size: int = 183,
    color: str = "#A84D2F",
) -> str:
    """Produce safe scene-layer ASS rows compatible with Pausio's compositor."""
    if (type(x) is not int or type(y) is not int or type(size) is not int or
        not 0 <= x <= 1080 or not 0 <= y <= 1920 or not 16 <= size <= 240 or
        type(color) is not str or not re.fullmatch(r"#[0-9A-F]{6}", color)):
        raise ValueError("Geometria o colore del contatore non validi.")
    frames = countup_frames(value, start_ms, end_ms)
    tag = (rf"\an5\pos({x},{y})\fnArial\fs{size}\b1\bord0\shad0\c"
           + _ass_color(color))
    return "".join(event(5, start, end, safe(label),
                         tag + (r"\fad(0,140)" if end == end_ms else ""))
                   for start, end, label in frames)
