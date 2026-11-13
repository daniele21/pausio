"""Conservative, local, evidence-backed editing proposals across FX types.

This is not semantic understanding or LLM inference. It only proposes source-
anchored graphic cards from literal reviewed caption text and optional motion
from Pausio's existing measured-signal planner. Proposals NEVER mutate a tape.
"""
from __future__ import annotations

import hashlib
import math
import re
from typing import Any

from pausio.graphic_overlays import validate_graphic
from pausio.visual_fx_auto import propose_visual_fx

ENGINE = "pausio-editorial-v1"
RULES = {
    "clean_tech": {"graphics_per_min": 1, "camera_per_min": 1, "gap_ms": 12000,
                   "zoom_profile": "naturale"},
    "educational": {"graphics_per_min": 2, "camera_per_min": 2, "gap_ms": 8500,
                    "zoom_profile": "educativo"},
    "dynamic_social": {"graphics_per_min": 3, "camera_per_min": 3, "gap_ms": 6000,
                       "zoom_profile": "dinamico"},
}
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_NUMBER = re.compile(r"(?<![A-Za-z0-9])(?:\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d+)?\s*(?:%|€|euro\b|milioni\b|mila\b))", re.I)
_CODE = re.compile(r"(?<![A-Za-z0-9])(?:[A-Za-z0-9_-]{1,30}\.){1,4}(?:json|yaml|yml|toml|py|env)\b")
_TIP = re.compile(r"^\s*(?:controlla|verifica|evita|non autorizzare|ricorda|prima|seconda|terza|check)\b", re.I)


def _identity(*parts: Any) -> str:
    return hashlib.sha256(repr(parts).encode("utf-8")).hexdigest()[:32]


def _excerpt(sentence: str, match: re.Match[str], limit: int = 80) -> str:
    if len(sentence) <= limit:
        return sentence
    left = max(0, match.start() - 24)
    right = min(len(sentence), left + limit)
    if match.end() > right:
        left = max(0, match.end()-limit)
        right = min(len(sentence), left+limit)
    # Exact substring from the reviewed caption, never reworded by a model.
    text = sentence[left:right].strip()
    if right < len(sentence) and " " in text:
        text = text.rsplit(" ", 1)[0]
    return text or match.group(0)


def propose_editorial_plan(
    *, segments: list[dict], captions: list[dict], existing_graphics: list[dict],
    existing_fx: list[dict], transcript: dict | None, preset: str,
    media_sha256: str, base_revision: int, source_duration_ms: int,
    waveform: list[int] | None = None,
) -> dict:
    if type(preset) is not str or preset not in RULES:
        raise ValueError("Profilo editoriale non supportato.")
    if (type(base_revision) is not int or base_revision < 0 or
        not isinstance(media_sha256, str) or not _HEX64.fullmatch(media_sha256) or
        type(source_duration_ms) is not int or not 0 < source_duration_ms <= 172_800_000):
        raise ValueError("Vincolo media o revisione non valido.")
    if not isinstance(segments, list) or len(segments) > 200:
        raise ValueError("Intervalli KEEP non validi.")
    if (not isinstance(captions, list) or len(captions) > 300 or
        not isinstance(existing_graphics, list) or len(existing_graphics) > 12 or
        not isinstance(existing_fx, list) or len(existing_fx) > 32):
        raise ValueError("Segnali editoriali oltre i limiti.")
    last_end = 0
    output_offsets: dict[str, int] = {}
    output_ms = 0
    for segment in segments:
        if (not isinstance(segment, dict) or set(segment) != {"id", "start_ms", "end_ms"} or
            type(segment["id"]) is not str or len(segment["id"]) != 32 or
            any(ch not in "0123456789abcdef" for ch in segment["id"]) or
            type(segment["start_ms"]) is not int or
            type(segment["end_ms"]) is not int or
            not last_end <= segment["start_ms"] < segment["end_ms"] <= source_duration_ms):
            raise ValueError("Intervallo KEEP non valido.")
        output_offsets[segment["id"]] = output_ms
        output_ms += segment["end_ms"] - segment["start_ms"]
        last_end = segment["end_ms"]
    rule = RULES[preset]
    def budget(per_min: int) -> int:
        return min(8, max(1, math.ceil(output_ms * per_min / 60000))) if output_ms else 0

    signals = []
    for cue in captions:
        if not isinstance(cue, dict):
            continue
        text = cue.get("text")
        a, b = cue.get("start_ms"), cue.get("end_ms")
        if (type(text) is not str or not text or len(text) > 300 or
            "\n" in text or "\r" in text or
            type(a) is not int or type(b) is not int or not 0 <= a < b <= source_duration_ms):
            continue
        segment = next((s for s in segments
                        if s["start_ms"] <= a and b <= s["end_ms"]), None)
        if segment is None or b-a < 500:
            continue
        code = _CODE.search(text)
        statistic = _NUMBER.search(text)
        tip = _TIP.search(text)
        if code:
            kind, match, priority = "code", code, 88
            snippet = code.group(0)
        elif statistic:
            kind, match, priority = "stat", statistic, 92
            snippet = _excerpt(text, statistic)
        elif tip:
            kind, match, priority = "tip", tip, 70
            snippet = _excerpt(text, tip)
        else:
            continue
        start = a
        end = min(b, a + 2500)
        if end-start < 500:
            continue
        # If an existing graphic is already near the same source statement,
        # prefer the creator's explicit work over an automated proposal.
        if any(g.get("start_ms",0) < end+1500 and
               g.get("end_ms",0) > start-1500 for g in existing_graphics
               if isinstance(g, dict)):
            continue
        graphic = {
            "id": _identity(ENGINE, media_sha256, preset, segment["id"], a, kind, snippet),
            "segment_id": segment["id"], "start_ms": start, "end_ms": end,
            "text": snippet, "kind": kind,
            "animation": "slide" if kind == "code" else "pop" if kind == "stat" else "fade",
            "x_pct": 50, "y_pct": 20 if kind == "code" else 24,
            "font_size": 56 if kind == "code" else 68 if kind == "stat" else 54,
            "color": "#FFFFFF" if kind == "code" else "#FFC69F" if kind == "stat" else "#D4FFE1",
        }
        validate_graphic(graphic, segments, source_duration_ms)
        signals.append({
            "candidate_id": graphic["id"], "command_type": "graphic.overlay.add",
            "payload": {"graphic": graphic}, "score_0_100": priority,
            "output_time_ms": output_offsets[segment["id"]] + a-segment["start_ms"],
            "evidence": {"kind": "caption_"+kind, "source_ms": a,
                         "quoted_text": snippet},
        })
    signals.sort(key=lambda c: (-c["score_0_100"],c["output_time_ms"],
                                c["candidate_id"]))
    graphics = []
    for candidate in signals:
        if len(graphics) >= budget(rule["graphics_per_min"]):
            break
        if any(abs(candidate["output_time_ms"]-g["output_time_ms"]) < rule["gap_ms"]
               for g in graphics):
            continue
        graphics.append(candidate)

    fx_plan = propose_visual_fx(
        segments=segments, transcript=transcript, existing=existing_fx,
        preset=rule["zoom_profile"],media_sha256=media_sha256,
        base_revision=base_revision,waveform=None,
        source_duration_ms=source_duration_ms
    )
    motion=[]
    for candidate in fx_plan["candidates"]:
        if len(motion) >= budget(rule["camera_per_min"]):
            break
        at=candidate["output_time_ms"]
        if any(abs(at-g["output_time_ms"]) < 3500 for g in graphics):
            continue
        if any(abs(at-f["output_time_ms"]) < rule["gap_ms"] for f in motion):
            continue
        motion.append({
            "candidate_id": candidate["candidate_id"],
            "command_type": "video.transform.add",
            "payload": {"effect": candidate["effect"]},
            "score_0_100": candidate["score_0_100"],
            "output_time_ms": at,
            "evidence": candidate["evidence"],
        })
    candidates = sorted([*graphics,*motion],
                        key=lambda c: (c["output_time_ms"],c["candidate_id"]))
    return {
        "engine": ENGINE, "preset":preset, "base_revision":base_revision,
        "media_sha256":media_sha256,"total_output_ms":output_ms,
        "candidates": candidates,
        "missing_signals": (["reviewed_caption_data"] if not captions else []) +
                           ["semantic_director", "visual_scene_detection"],
        "approval_required":True,
    }
