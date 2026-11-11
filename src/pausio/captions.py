"""Reviewable social captions with explicit source->output timeline mapping.

Pure functions: model results are drafts, captions are typed project commands.
No model dependency, FFmpeg subprocess or I/O in this module.
"""

from __future__ import annotations

import re
from typing import Any

from pausio.domain import Interval

CAPTION_STYLES = ("social", "minimal", "boxed")
# Explicit allowlist is shared by the Studio UI and ASS renderer. Model/ASR
# cannot inject arbitrary ASS font-name delimiters or escape sequences.
# FFmpeg/libass resolves these families from fonts installed on the device.
CAPTION_FONTS = (
    "Arial", "Helvetica Neue", "Avenir Next", "Verdana",
    "Georgia", "Courier New", "Impact", "Times New Roman",
)
DEFAULT_CAPTION_FONT = "Arial"
CAPTION_PRESETS = {
    "social": {"preset": "social", "x_pct": 50, "y_pct": 80, "font_size": 64,
               "font_family": DEFAULT_CAPTION_FONT,
               "text_color": "#FFFFFF", "outline_color": "#000000",
               "outline_size": 4, "background": False, "background_color": "#000000"},
    "minimal": {"preset": "minimal", "x_pct": 50, "y_pct": 82, "font_size": 48,
                "font_family": DEFAULT_CAPTION_FONT,
                "text_color": "#FFFFFF", "outline_color": "#000000",
                "outline_size": 3, "background": False, "background_color": "#000000"},
    "boxed": {"preset": "boxed", "x_pct": 50, "y_pct": 76, "font_size": 56,
              "font_family": DEFAULT_CAPTION_FONT,
              "text_color": "#FFFFFF", "outline_color": "#000000",
              "outline_size": 3, "background": True, "background_color": "#161616"},
}
CAPTION_CONFIG_FIELDS = frozenset(CAPTION_PRESETS["social"])
CAPTION_CONFIG_RANGES = {
    "x_pct": (15, 85), "y_pct": (15, 85),
    "font_size": (32, 100), "outline_size": (0, 10),
}
_COLOR_RE = re.compile(r"^#[0-9A-F]{6}$")


def validate_caption_config(raw: object) -> dict[str, Any]:
    """Strictly validate normalized style data for project replay and FFmpeg."""
    # Projects created before font selection did not contain font_family.
    # Normalize only this known legacy omission. Other unknown/missing fields
    # remain rejected; replay of older .pausio.json stays deterministic.
    old_fields = CAPTION_CONFIG_FIELDS - {"font_family"}
    if not isinstance(raw, dict) or set(raw) not in (
        CAPTION_CONFIG_FIELDS, old_fields
    ):
        raise ValueError("Configurazione sottotitoli incompleta o non valida.")
    config = {"font_family": DEFAULT_CAPTION_FONT, **raw}
    preset = config["preset"]
    if not isinstance(preset, str) or preset not in (*CAPTION_STYLES, "custom"):
        raise ValueError("Preset sottotitoli sconosciuto.")
    for key, (minimum, maximum) in CAPTION_CONFIG_RANGES.items():
        if type(config[key]) is not int or not minimum <= config[key] <= maximum:
            raise ValueError(f"{key}: inserisci un intero tra {minimum} e {maximum}.")
    for key in ("text_color", "outline_color", "background_color"):
        if not isinstance(config[key], str) or not _COLOR_RE.fullmatch(config[key]):
            raise ValueError(f"{key}: usa un colore esadecimale #RRGGBB.")
    if type(config["background"]) is not bool:
        raise ValueError("Il valore di sfondo deve essere vero o falso.")
    if not isinstance(config["font_family"], str) or config["font_family"] not in CAPTION_FONTS:
        raise ValueError("Font sottotitoli non supportato. Scegli uno dei font disponibili.")
    if preset != "custom" and config != CAPTION_PRESETS[preset]:
        raise ValueError("Modifiche al preset richiedono Personalizzato.")
    return dict(config)


def default_caption_config(preset: str = "social") -> dict[str, Any]:
    if preset not in CAPTION_STYLES:
        raise ValueError("Preset sottotitoli sconosciuto.")
    return dict(CAPTION_PRESETS[preset])

MAX_CAPTIONS = 500
MAX_CAPTION_LENGTH = 300


def _text(words: list[str]) -> str:
    joined = " ".join(part.strip() for part in words if part.strip())
    return re.sub(r"\s+([,.;:!?%])", r"\1", joined).strip()


def propose_captions(
    transcript: dict[str, Any], *, source_duration_ms: int
) -> list[dict[str, Any]]:
    """Break real word alignments into readable short cues.

    If word timestamps are absent, keep the original *segment* interval;
    never fabricate word timings by distributing text across time.
    """
    if not isinstance(transcript, dict) or not isinstance(
        transcript.get("segments"), list
    ):
        raise ValueError("Trascrizione non valida per creare sottotitoli.")
    proposed: list[dict[str, Any]] = []
    for segment in transcript["segments"]:
        if not isinstance(segment, dict):
            raise ValueError("Segmento trascritto non valido.")
        start, end = segment.get("start_ms"), segment.get("end_ms")
        if type(start) is not int or type(end) is not int or not (
            0 <= start < end <= source_duration_ms + 2000
        ):
            raise ValueError("Timestamp della trascrizione non validi.")
        end = min(end, source_duration_ms)
        if end <= start:
            continue
        words = segment.get("words")
        if isinstance(words, list) and words:
            chunk: list[dict] = []

            def flush() -> None:
                if not chunk:
                    return
                cue = {
                    "start_ms": chunk[0]["start_ms"],
                    "end_ms": chunk[-1]["end_ms"],
                    "text": _text([w["text"] for w in chunk]),
                }
                if cue["text"] and cue["end_ms"] > cue["start_ms"]:
                    proposed.append(cue)
                chunk.clear()

            for word in words:
                if not isinstance(word, dict):
                    raise ValueError("Parola ASR non valida.")
                a, b, value = (
                    word.get("start_ms"), word.get("end_ms"), word.get("text")
                )
                if type(a) is not int or type(b) is not int or not isinstance(value, str):
                    raise ValueError("Timestamp delle parole non validi.")
                a, b = max(start, a), min(end, b)
                if b <= a or not value.strip():
                    continue
                if chunk and (
                    len(chunk) >= 6
                    or b - chunk[0]["start_ms"] > 2800
                    or len(_text([w["text"] for w in chunk] + [value])) > 46
                ):
                    flush()
                chunk.append({"start_ms": a, "end_ms": b, "text": value})
                if re.search(r"[.!?]$", value.strip()) and len(chunk) >= 3:
                    flush()
            flush()
        else:
            value = segment.get("text", "")
            if not isinstance(value, str):
                raise ValueError("Testo trascritto non valido.")
            if value.strip():
                proposed.append({
                    "start_ms": start, "end_ms": end, "text": value.strip()
                })
        if len(proposed) > MAX_CAPTIONS:
            raise ValueError(
                "Troppi sottotitoli per un singolo progetto (massimo 500)."
            )
    # Preserve original timestamps. If ASR intervals overlap, clip the next
    # display interval, never move words beyond their documented timestamps.
    cleaned = []
    for cue in sorted(proposed, key=lambda c: (c["start_ms"], c["end_ms"])):
        begin = max(cleaned[-1]["end_ms"], cue["start_ms"]) if cleaned else cue["start_ms"]
        if begin >= cue["end_ms"]:
            continue
        if len(cue["text"]) > MAX_CAPTION_LENGTH:
            raise ValueError("Un sottotitolo è troppo lungo: correggi la trascrizione.")
        cleaned.append({**cue, "start_ms": begin})
    return cleaned


def remap_captions(
    cues: tuple[dict, ...] | list[dict], keep: tuple[Interval, ...],
) -> list[dict]:
    """Intersect captions with KEEP segments, then map to concatenated output ms.

    A cue crossing a removed pause is split at the output boundary.
    Discarded words entirely inside a removed interval never reappear.
    """
    output: list[dict] = []
    offset = 0
    for segment in keep:
        for cue in cues:
            start = max(segment.start_ms, cue["start_ms"])
            end = min(segment.end_ms, cue["end_ms"])
            if end <= start:
                continue
            mapped_start = offset + start - segment.start_ms
            mapped_end = offset + end - segment.start_ms
            if output and mapped_start < output[-1]["end_ms"]:
                mapped_start = output[-1]["end_ms"]
            if mapped_end - mapped_start < 80:
                continue
            output.append({
                "id": cue["id"],
                "start_ms": mapped_start, "end_ms": mapped_end,
                "text": cue["text"],
            })
        offset += segment.end_ms - segment.start_ms
    return output


def _ass_time(ms: int) -> str:
    hundredths = max(0, ms // 10)
    return (
        f"{hundredths // 360000}:"
        f"{hundredths // 6000 % 60:02d}:"
        f"{hundredths // 100 % 60:02d}."
        f"{hundredths % 100:02d}"
    )


def _ass_text(value: str) -> str:
    # No ASS override injection: braces and backslash commands are stripped.
    clean = value.replace("\\", "").replace("{", "").replace("}", "")
    clean = re.sub(r"[\x00-\x1f\x7f]", " ", clean)
    return clean.strip()


def _ass_color(rgb: str, *, alpha: str = "00") -> str:
    """ASS requires the AABBGGRR color channel order."""
    return f"&H{alpha}{rgb[5:7]}{rgb[3:5]}{rgb[1:3]}".upper()


def ass_document(
    cues: list[dict], *, style: str = "social",
    settings: dict[str, Any] | None = None
) -> str:
    """Produce UTF-8 ASS cues for FFmpeg libass burning, at 1080x1920 coords."""
    config = validate_caption_config(
        settings if settings is not None else default_caption_config(style)
    )
    font_size = config["font_size"]
    font_family = config["font_family"]
    outline = config["outline_size"]
    x = round(config["x_pct"] * 1080 / 100)
    y = round(config["y_pct"] * 1920 / 100)
    border_style = 3 if config["background"] else 1
    foreground = _ass_color(config["text_color"])
    stroke = _ass_color(config["outline_color"])
    background = _ass_color(config["background_color"], alpha="30")
    header = (
        "[Script Info]\nScriptType: v4.00+\n"
        "PlayResX: 1080\nPlayResY: 1920\nScaledBorderAndShadow: yes\n"
        "WrapStyle: 0\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Caption,{font_family},{font_size},{foreground},{foreground},"
        f"{stroke},{background},-1,0,0,0,100,100,0,0,"
        f"{border_style},{outline},1,5,105,105,0,1\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
    )
    events = []
    for cue in cues:
        start, end = cue["start_ms"], cue["end_ms"]
        if end - start < 80:
            continue
        value = _ass_text(cue["text"])
        if value:
            events.append(
                f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},"
                f"Caption,,0,0,0,,{{\\an5\\pos({x},{y})}}{value}\n"
            )
    return header + "".join(events)
