"""Deterministic, source-bound informational graphic cards for talking-head videos.

Pure validator/remapper and safe ASS composer. No HTML, shell, remote URLs,
user-provided FFmpeg filter expressions, model inference or arbitrary fonts.
"""
from __future__ import annotations

import re
from typing import Any

from pausio.domain import Interval
from pausio.captions import ass_document, _ass_time, _ass_text, _ass_color

MAX_GRAPHICS = 12
KINDS = frozenset({"headline", "stat", "code", "tip"})
ANIMATIONS = frozenset({"fade", "pop", "slide"})
FIELDS = frozenset({"id", "segment_id", "start_ms", "end_ms", "text",
                    "kind", "animation", "x_pct", "y_pct",
                    "font_size", "color"})
IDENTITY = re.compile(r"^[0-9a-f]{32}$")
COLOR = re.compile(r"^#[0-9A-F]{6}$")


def validate_graphic(raw: Any, segments: list[dict], source_duration_ms: int) -> dict:
    if not isinstance(raw, dict) or set(raw) != FIELDS:
        raise ValueError("Grafica: campi obbligatori o sconosciuti.")
    if not all(isinstance(raw[k], str) and IDENTITY.fullmatch(raw[k])
               for k in ("id", "segment_id")):
        raise ValueError("Grafica: ID non valido.")
    segment = next((s for s in segments if s["id"] == raw["segment_id"]), None)
    if segment is None:
        raise ValueError("Grafica: intervallo sorgente inesistente.")
    a, b = raw["start_ms"], raw["end_ms"]
    if not (type(a) is int and type(b) is int
            and 0 <= a < b <= source_duration_ms
            and segment["start_ms"] <= a and b <= segment["end_ms"]
            and 400 <= b-a <= 12000):
        raise ValueError("Grafica: usa 400 ms–12 s dentro lo stesso intervallo mantenuto.")
    text = raw["text"]
    if not (isinstance(text, str) and 1 <= len(text.strip()) <= 100
            and text == text.strip()
            and not any(ord(char) < 32 or ord(char) == 127 for char in text)):
        raise ValueError("Grafica: testo obbligatorio, massimo 100 caratteri e una riga.")
    if type(raw["kind"]) is not str or raw["kind"] not in KINDS:
        raise ValueError("Grafica: stile non supportato.")
    if type(raw["animation"]) is not str or raw["animation"] not in ANIMATIONS:
        raise ValueError("Grafica: animazione non supportata.")
    for key, low, high in (("x_pct", 15, 85), ("y_pct", 8, 62),
                            ("font_size", 36, 104)):
        value = raw[key]
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f"Grafica: {key} fuori dai limiti {low}–{high}.")
    if not isinstance(raw["color"], str) or not COLOR.fullmatch(raw["color"]):
        raise ValueError("Grafica: colore in formato #RRGGBB maiuscolo.")
    return dict(raw)


def validate_graphics(items: Any, segments: list[dict], duration_ms: int) -> None:
    if not isinstance(items, list) or len(items) > MAX_GRAPHICS:
        raise ValueError("Troppi elementi grafici (massimo 12).")
    seen: set[str] = set()
    for graphic in items:
        item = validate_graphic(graphic, segments, duration_ms)
        if item["id"] in seen:
            raise ValueError("Grafica: ID duplicato.")
        seen.add(item["id"])


def remap_graphics(graphics: tuple[dict, ...] | list[dict],
                   keep: tuple[Interval, ...]) -> list[dict]:
    """Map original-source graphic intervals to output time, preserving IDs."""
    out: list[dict] = []
    offset = 0
    for seg in keep:
        for graphic in graphics:
            a = max(seg.start_ms, graphic["start_ms"])
            b = min(seg.end_ms, graphic["end_ms"])
            if b-a >= 400:
                out.append({**graphic, "start_ms": offset + a-seg.start_ms,
                            "end_ms": offset + b-seg.start_ms})
        offset += seg.end_ms-seg.start_ms
    return sorted(out, key=lambda row: (row["start_ms"], row["id"]))


def compose_graphics_ass(cues: list[dict], graphics: list[dict], *,
                         style: str = "social", settings: dict | None = None) -> str:
    """Compose captions and overlays in one libass pass after zoom/crop.

    Pixel coordinates use the same ASS PlayRes 1080x1920 for preview and export.
    No user-controlled ASS override text is evaluated.
    """
    base = ass_document(cues, style=style, settings=settings)
    # Distinct native libass card styles; no user-provided fonts or filters.
    def style_line(name: str, font: str, border: int, outline: int,
                   back_color: str) -> str:
        return (
            f"Style: {name},{font},64,&H00FFFFFF,&H00FFFFFF,&H00000000,"
            f"{back_color},-1,0,0,0,100,100,0,0,"
            f"{border},{outline},0,5,40,40,0,1\n"
        )
    overlay_style = (
        style_line("Graphic", "Arial", 1, 5, "&H70000000")
        + style_line("GraphicHeadline", "Arial", 1, 5, "&H70000000")
        + style_line("GraphicStat", "Impact", 3, 10, "&H550D1724")
        + style_line("GraphicCode", "Courier New", 3, 12, "&H50131520")
        + style_line("GraphicTip", "Avenir Next", 3, 9, "&H5533291C")
    )
    result = base.replace("[Events]\n", overlay_style+"[Events]\n", 1)
    events = []
    for g in graphics:
        # Render-side hard check (all values are already source-validated).
        if (not isinstance(g, dict) or set(g) != FIELDS or
            type(g["start_ms"]) is not int or type(g["end_ms"]) is not int or
            g["end_ms"]-g["start_ms"] < 400 or
            type(g["kind"]) is not str or g["kind"] not in KINDS or
            type(g["animation"]) is not str or g["animation"] not in ANIMATIONS):
            raise ValueError("Grafica di rendering non valida.")
        x = round(g["x_pct"] * 1080 / 100)
        y = round(g["y_pct"] * 1920 / 100)
        color = _ass_color(g["color"])
        size = g["font_size"]
        style_name, font, padding = {
            "headline": ("GraphicHeadline", "Arial", 5),
            "stat": ("GraphicStat", "Impact", 10),
            "code": ("GraphicCode", "Courier New", 12),
            "tip": ("GraphicTip", "Avenir Next", 9),
        }[g["kind"]]
        # Native fixed ASS templates, never raw expressions from a project.
        pos = (fr"\move({x},{y+42},{x},{y},0,260)"
               if g["animation"] == "slide" else fr"\pos({x},{y})")
        effect = (r"\fscx85\fscy85\t(0,190,\fscx100\fscy100)"
                  if g["animation"] == "pop" else "")
        fade = r"\fad(180,160)" if g["animation"] != "pop" else r"\fad(100,130)"
        line = _ass_text(g["text"])
        if not line:
            continue
        overrides = (fr"\an5{pos}\fn{font}\fs{size}\c{color}"
                     fr"\bord{padding}\shad0{fade}{effect}")
        events.append(
            f"Dialogue: 1,{_ass_time(g['start_ms'])},{_ass_time(g['end_ms'])},"
            f"{style_name},,0,0,0,,{{{overrides}}}{line}\n"
        )
    return result + "".join(events)
