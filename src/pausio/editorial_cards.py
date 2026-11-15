"""Versioned, realistic editorial UI compositions in the one libass renderer.

The underlying talking head is visible for the three compact UI variants.
Only a short metric moment takes over the frame. All geometry, visual
tokens, fonts, animation timings and mock disclaimers are code-owned.
No input-supplied HTML/CSS/SVG, FFmpeg expression, path or URL is evaluated.
"""
from __future__ import annotations

from typing import Callable

from pausio.captions import _ass_color, _ass_time

W, H = 1080, 1920
# Neutral, brand-agnostic design, not a screenshot of a named product.
INK = "#121823"
PAPER = "#F8FAFC"
MUTED = "#728197"
SUBTLE = "#E5EBF1"
NIGHT = "#101C2D"
NIGHT_PANEL = "#1B2B40"
WHITE = "#FFFFFF"


def _rounded(x: int, y: int, w: int, h: int, r: int) -> str:
    """Cubic Bézier rounded rectangle in ASS vector drawing coordinates."""
    r = max(1, min(r, w // 2, h // 2))
    k = round(r * .5523)
    return (
        f"m {x+r} {y} l {x+w-r} {y} "
        f"b {x+w-r+k} {y} {x+w} {y+r-k} {x+w} {y+r} "
        f"l {x+w} {y+h-r} "
        f"b {x+w} {y+h-r+k} {x+w-r+k} {y+h} {x+w-r} {y+h} "
        f"l {x+r} {y+h} "
        f"b {x+r-k} {y+h} {x} {y+h-r+k} {x} {y+h-r} "
        f"l {x} {y+r} "
        f"b {x} {y+r-k} {x+r-k} {y} {x+r} {y}"
    )


class _Canvas:
    def __init__(self, scene: dict, event: Callable, safe: Callable):
        self.scene = scene
        self.event = event
        self.safe = safe
        self.start = scene["start_ms"]
        self.end = self.start + scene["duration_ms"]
        self.accent = ("#E88852" if scene["accent"] == "orange" else "#42B5A6")
        self.parts: list[str] = []

    def panel(self, x: int, y: int, w: int, h: int, *,
              radius: int = 26, color: str = WHITE, delay: int = 0,
              shadow: bool = True, layer: int = 2,
              alpha: int = 0) -> None:
        a = self.start + delay
        if a >= self.end:
            return
        path = _rounded(x, y, w, h, radius)
        if shadow:
            tags = (r"\an7\pos(0,28)\bord0\shad0\blur16\c"
                    + _ass_color("#07111F") + r"\1a&H75&\p1\fad(130,140)")
            self.parts.append(self.event(layer-1, a, self.end, path, tags))
        tags = (r"\an7\pos(0,0)\bord0\shad0\c" + _ass_color(color)
                + fr"\1a&H{alpha:02X}&\p1\fad(130,140)")
        self.parts.append(self.event(layer, a, self.end, path, tags))

    def type(self, value: str, x: int, y: int, size: int, color: str,
             *, delay: int = 0, layer: int = 5, mono: bool = False,
             weight: bool = True, motion: bool = True) -> None:
        a = self.start + delay
        if a >= self.end:
            return
        pos = (fr"\move({x},{y+20},{x},{y},0,220)" if motion
               else fr"\pos({x},{y})")
        font = "Courier New" if mono else "Arial"
        tags = (fr"\an5{pos}\fn{font}\fs{size}\b{1 if weight else 0}"
                r"\bord0\shad0\c" + _ass_color(color) + r"\fad(100,140)")
        self.parts.append(self.event(layer, a, self.end, self.safe(value), tags))

    def badge(self, value: str, x: int, y: int, w: int, *,
              color: str, delay: int = 0, dark: bool = False) -> None:
        self.panel(x, y, w, 70, color=color, radius=20, delay=delay,
                   shadow=False, layer=3)
        self.type(value, x+w//2, y+36, 29,
                  WHITE if dark else NIGHT, delay=delay+100, mono=False)

    def output(self) -> str:
        return "".join(self.parts)


def _floating_insight(c: _Canvas, d: dict) -> None:
    # One short upper-third notification, face remains full-frame.
    c.panel(66, 168, 948, 400, radius=46)
    c.panel(96, 204, 888, 3, color=SUBTLE, radius=1, shadow=False)
    c.badge("INSIGHT", 112, 250, 184, color="#E7F4EF")
    c.type(d["title"], 540, 389, 51, INK, delay=190)
    c.type(d["detail"], 540, 495, 36, MUTED, delay=420, weight=False)


def _permission_mock(c: _Canvas, d: dict) -> None:
    # Explicitly illustrative; never pretend that this is an actual screenshot.
    c.panel(68, 142, 944, 718, radius=44)
    c.panel(70, 144, 940, 102, radius=42, color="#F0F4F8", shadow=False)
    for i, color in enumerate(("#E5A8A0", "#E9D4A2", "#ABD7C5")):
        c.panel(112+i*39, 184, 19, 19, radius=9,
                color=color, shadow=False, layer=4)
    c.type("AGENT PERMISSIONS", 557, 193, 31, MUTED, delay=160,
           mono=True, weight=False)
    c.badge("DEMO", 118, 290, 140, color="#FFF0DC")
    c.type(d["title"], 540, 422, 49, INK, delay=280)
    c.panel(124, 491, 832, 112, radius=19, color="#EDF2F6",
            delay=330, shadow=False)
    c.type(d["command"], 540, 547, 33, NIGHT, delay=460, mono=True)
    c.panel(124, 656, 376, 103, radius=20, color=SUBTLE,
            delay=650, shadow=False)
    c.panel(526, 656, 430, 103, radius=20, color="#F4D2C4",
            delay=650, shadow=False)
    c.type(d["once"], 312, 706, 32, INK, delay=760)
    c.type(d["persistent"], 740, 706, 32, "#883B24", delay=1050)
    c.type("SIMULAZIONE UI · NON È UNO SCREENSHOT",
           540, 901, 25, WHITE, delay=250, weight=False)


def _code_inspector(c: _Canvas, d: dict) -> None:
    # A product-like local settings editor: no real secret bytes.
    c.panel(64, 124, 952, 775, radius=38, color=NIGHT)
    c.panel(66, 126, 948, 112, radius=36, color=NIGHT_PANEL, shadow=False)
    c.panel(112, 169, 16, 16, radius=7,
            color=c.accent, shadow=False, layer=4)
    c.type(d["filename"], 550, 184, 32, WHITE, delay=210, mono=True)
    c.badge("LOCAL", 110, 276, 160, color="#315466", dark=True)
    for i, key in enumerate(("line_one", "line_two", "highlight")):
        y = 424 + i*128
        if i == 2:
            c.panel(100, y-48, 870, 96, radius=18,
                    color="#533C3E", delay=780, shadow=False)
            c.panel(104, y-48, 7, 96, radius=2,
                    color=c.accent, delay=790, shadow=False)
        c.type(f"{i+1:02d}", 148, y, 27, MUTED,
               delay=330+i*220, mono=True, weight=False)
        c.type(d[key], 580, y, 32,
               "#FFC9AA" if i==2 else "#E0E8F0",
               delay=380+i*220, mono=True)
    c.type("ESEMPIO ILLUSTRATIVO · NESSUNA CREDENZIALE REALE",
           540, 951, 25, WHITE, delay=350, weight=False)


def _metric_spotlight(c: _Canvas, d: dict) -> None:
    # Full-frame insert is intentional and rare, surrounded by face-first beats.
    c.panel(0, 0, W, H, radius=2, color="#F4F2ED", shadow=False)
    c.panel(76, 118, 928, 8, radius=4, color=c.accent, shadow=False)
    c.badge("EVIDENZA", 102, 234, 228, color="#E9E7E1")
    c.type(d["heading"], 540, 420, 51, INK, delay=180)
    c.type(d["number"], 540, 810, 183, "#A84D2F", delay=380)
    c.type(d["unit"], 540, 1004, 78, INK, delay=640)
    c.panel(115, 1164, 850, 2, radius=1,
            color="#CBD0D5", shadow=False, delay=800)
    c.type(d["detail"], 540, 1320, 39, MUTED,
           delay=910, weight=False)
    c.type(d["source_note"], 540, 1638, 27, MUTED,
           delay=1100, weight=False)


def compose_editorial_card(scene: dict, event: Callable, safe: Callable) -> str:
    """Compile one validated event into deterministic libass dialogue rows."""
    templates = {
        "floating_insight": _floating_insight,
        "permission_mock": _permission_mock,
        "code_inspector": _code_inspector,
        "metric_spotlight": _metric_spotlight,
    }
    render = templates[scene["template"]]
    canvas = _Canvas(scene, event, safe)
    render(canvas, scene["content"])
    return canvas.output()
