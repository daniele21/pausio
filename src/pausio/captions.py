"""Reviewable social captions with explicit source->output timeline mapping.

Pure functions: model results are drafts, captions are typed project commands.
No model dependency, FFmpeg subprocess or I/O in this module.
"""

from __future__ import annotations

import re
from typing import Any

from pausio.domain import Interval

CAPTION_STYLES = ("social", "minimal")
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


def ass_document(cues: list[dict], *, style: str = "social") -> str:
    """Produce UTF-8 ASS cues for FFmpeg libass burning, at 1080x1920 coords."""
    if style not in CAPTION_STYLES:
        raise ValueError("Stile sottotitoli sconosciuto.")
    font_size = 64 if style == "social" else 48
    outline = 4 if style == "social" else 3
    margin = 385 if style == "social" else 350
    header = (
        "[Script Info]\nScriptType: v4.00+\n"
        "PlayResX: 1080\nPlayResY: 1920\nScaledBorderAndShadow: yes\n"
        "WrapStyle: 0\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Caption,Arial,{font_size},&H00FFFFFF,&H00FFFFFF,"
        f"&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,"
        f"{outline},1,2,105,105,{margin},1\n"
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
                f"Caption,,0,0,0,,{value}\n"
            )
    return header + "".join(events)
