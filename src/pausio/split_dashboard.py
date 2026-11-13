"""Deterministic split-screen talking-head dashboard.

Only a fixed, data-driven template: no arbitrary FFmpeg/ASS expressions,
external UI engine, HTML, JS scripts or unbounded keyframe data.
"""
from __future__ import annotations

from typing import Callable


def compose_dashboard(scene: dict, rect: Callable, label: Callable) -> str:
    """Timed ASS cards in the TOP region; source video occupies the bottom."""
    a, end = scene["start_ms"], scene["start_ms"] + scene["duration_ms"]
    d = scene["content"]
    mint = "#65D9CB" if scene["accent"] == "mint" else "#FFA875"
    background, panel, text, muted = "#0B1725", "#192B3C", "#F4F7FA", "#B7C8D2"
    height = d["presenter_height_pct"]
    # Coordinates in the canonical libass 1080x1920 canvas, not export pixels.
    top = 1920 - (1920 * height // 100)
    events: list[str] = []

    def bar(start: int, stop: int, x: int, y: int, w: int, h: int,
            color: str) -> None:
        if stop > start and w > 0 and h > 0:
            events.append(rect(start, stop, x, y, w, h, color))

    def text_at(start: int, value: str, x: int, y: int,
                size: int, color: str, *, pop: bool = False) -> None:
        if end > start:
            events.append(label(start, end, value, x, y, size, color, pop=pop))

    bar(a, end, 0, 0, 1080, top, background)
    bar(a + 110, end, 80, 90, 920, 6, mint)
    text_at(a + 180, d["title"], 540, round(top * .16), 54, text)

    tasks = [d["task_one"], d["task_two"], d["task_three"]]
    for i, task in enumerate(tasks):
        reveal = a + 420 + i * 620
        y = round(top * (.31 + i * .135))
        bar(reveal, end, 90, y-47, 900, 94, panel)
        bar(reveal, end, 117, y-25, 55, 55, "#334D56")
        text_at(reveal + 100, task, 560, y, 39, text)
        # Native ASS appearance, intentionally no fake "real UI" screenshot.
        text_at(reveal + 440, "✓", 144, y, 48, mint, pop=True)

    progress_y = round(top * .755)
    bar(a + 2300, end, 130, progress_y, 820, 29, "#263B4A")
    progress_width = round(820 * d["progress_pct"] / 100)
    # Step-by-step bar progression. Each step replaces the prior extent.
    for step in range(1, 7):
        begin = a + 2470 + (step-1)*165
        stop = min(a + 2470 + step*165, end) if step < 6 else end
        bar(begin, stop, 130, progress_y,
            max(2, round(progress_width*step/6)), 29, mint)
    text_at(a + 2450, d["progress_label"],
            440, round(top * .71), 36, muted)
    text_at(a + 3470, f'{d["progress_pct"]}%', 870,
            round(top * .71), 38, mint, pop=True)

    bar(a + 3970, end, 130, round(top * .845), 820, 92, panel)
    text_at(a + 4170, d["budget"], 540,
            round(top * .885), 40, text, pop=True)
    # Divider between content and talking head.
    bar(a, end, 0, top-8, 1080, 8, mint)
    return "".join(events)


def compile_speaker_splits(components: list[str], label: str,
                           scenes: list[dict], size: tuple[int, int]) -> str:
    """Produce scene-gated presenter crop over the BOTTOM band of the video.

    The source stream is already normalized to the output's dimensions.
    Outside the selected output-time intervals the original video is unchanged.
    The existing audio graph is not modified.
    """
    width, full_height = size
    result = label
    for i, scene in enumerate(s for s in scenes
                              if s["template"] == "dashboard_split"):
        data = scene["content"]
        height = max(2, round(full_height * data["presenter_height_pct"]/100)//2*2)
        top = full_height-height
        anchor = data["presenter_anchor_pct"]
        crop_y = min(top, round(top * anchor/100)//2*2)
        start = scene["start_ms"]/1000
        end = (scene["start_ms"]+scene["duration_ms"])/1000
        # Bounded numeric dimensions and timing are validated by scene schema.
        components.append(f"{result}split=2[sbase{i}][ssrc{i}]")
        components.append(
            f"[ssrc{i}]crop={width}:{height}:0:{crop_y},setsar=1[sperson{i}]"
        )
        components.append(
            f"[sbase{i}][sperson{i}]overlay=x=0:y={top}:"
            f"enable='gte(t\\,{start:.3f})*lt(t\\,{end:.3f})':"
            f"shortest=1:format=auto,format=yuv420p[sfull{i}]"
        )
        result = f"[sfull{i}]"
    return result
