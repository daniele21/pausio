"""Reviewable editorial Style Packs for Pausio's existing typed scene pipeline.

These are *planning policies*, not an automatic renderer and not AI inference.
A caller supplies narrative beats and exact, reviewed copy. No source footage,
remote URL, template default or unverifiable statistic is inserted by this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import ceil
from typing import Any

from pausio.scene_templates import MAX_SCENES, TEMPLATES, validate_scene

PURPOSES = frozenset({"hook", "problem", "evidence", "explanation", "takeaway"})
BEAT_FIELDS = frozenset({
    "start_ms", "end_ms", "purpose", "visuals", "evidence_verified",
})


@dataclass(frozen=True)
class StylePack:
    id: str
    label: str
    caption_preset: str
    camera_preset: str
    editorial_preset: str
    accent: str
    max_scenes_per_minute: int
    min_gap_ms: int
    max_scene_ms: int
    template_priority: dict[str, tuple[str, ...]]


_PACKS: tuple[StylePack, ...] = (
    StylePack(
        id="authority", label="Authority", caption_preset="minimal",
        camera_preset="naturale", editorial_preset="clean_tech",
        accent="mint", max_scenes_per_minute=2,
        min_gap_ms=3000, max_scene_ms=3500,
        template_priority={
            "hook": ("floating_insight",),
            "problem": (),
            "evidence": ("metric_spotlight",),
            "explanation": (),
            "takeaway": ("floating_insight",),
        },
    ),
    StylePack(
        id="visual_explainer", label="Visual Explainer",
        caption_preset="word_focus", camera_preset="educativo",
        editorial_preset="educational", accent="mint",
        max_scenes_per_minute=6, min_gap_ms=900, max_scene_ms=4700,
        template_priority={
            "hook": ("floating_insight",),
            "problem": ("permission_mock", "floating_insight"),
            "evidence": ("metric_spotlight",),
            "explanation": ("code_inspector", "floating_insight"),
            "takeaway": ("floating_insight",),
        },
    ),
    StylePack(
        id="social_impact", label="Social Impact",
        caption_preset="kinetic", camera_preset="dinamico",
        editorial_preset="dynamic_social", accent="orange",
        max_scenes_per_minute=8, min_gap_ms=450, max_scene_ms=2600,
        template_priority={
            "hook": ("floating_insight",),
            "problem": ("permission_mock", "floating_insight"),
            "evidence": ("metric_spotlight",),
            "explanation": ("code_inspector", "floating_insight"),
            "takeaway": ("floating_insight",),
        },
    ),
)

PACK_VERSION = 1
PACKS = {pack.id: pack for pack in _PACKS}


def catalog() -> list[dict[str, Any]]:
    """Read-only style metadata for future Studio/MCP consumers."""
    return [
        {
            "id": pack.id,
            "label": pack.label,
            "version": PACK_VERSION,
            "caption_preset": pack.caption_preset,
            "camera_preset": pack.camera_preset,
            "editorial_preset": pack.editorial_preset,
            "accent": pack.accent,
            "max_scenes_per_minute": pack.max_scenes_per_minute,
            "min_gap_ms": pack.min_gap_ms,
            "max_scene_ms": pack.max_scene_ms,
            "purpose_templates": {
                purpose: list(pack.template_priority[purpose]) for purpose in sorted(PURPOSES)
            },
        }
        for pack in _PACKS
    ]


def _validate_beats(beats: Any, output_ms: int) -> list[dict]:
    if type(output_ms) is not int or not 1 <= output_ms <= 172800000:
        raise ValueError("Durata del video montato non valida.")
    if not isinstance(beats, list) or not 1 <= len(beats) <= 60:
        raise ValueError("Sono necessari da 1 a 60 beat narrativi.")
    previous_end = 0
    for beat in beats:
        if not isinstance(beat, dict) or set(beat) != BEAT_FIELDS:
            raise ValueError("Beat narrativo: campi mancanti o sconosciuti.")
        start, end = beat["start_ms"], beat["end_ms"]
        if (type(start) is not int or type(end) is not int or
            start < previous_end or not start < end <= output_ms):
            raise ValueError("Beat narrativi non ordinati, sovrapposti o fuori timeline.")
        if type(beat["purpose"]) is not str or beat["purpose"] not in PURPOSES:
            raise ValueError("Beat narrativo: scopo non supportato.")
        if type(beat["evidence_verified"]) is not bool:
            raise ValueError("Beat narrativo: evidence_verified deve essere booleano.")
        visuals = beat["visuals"]
        if (not isinstance(visuals, dict) or
            any(type(key) is not str or key not in TEMPLATES or
                not isinstance(value, dict) for key, value in visuals.items())):
            raise ValueError("Beat narrativo: visuali o template sconosciuti.")
        previous_end = end
    return beats


def propose_variant(beats: list[dict], output_ms: int, style_id: str) -> dict:
    """Return *candidate* scene.template.add payloads; never apply project edits.

    All copy must be supplied by the caller. In particular evidence_verified
    is merely a human/editorial attestation and does not check factual accuracy.
    Unknown or incomplete template content fails closed for that beat.
    """
    _validate_beats(beats, output_ms)
    if type(style_id) is not str or style_id not in PACKS:
        raise ValueError("Style Pack sconosciuto.")
    pack = PACKS[style_id]
    max_scenes = min(MAX_SCENES, max(
        1, ceil(output_ms * pack.max_scenes_per_minute / 60000)
    ))
    candidates: list[dict] = []
    skipped: list[dict] = []
    previous_end = -pack.min_gap_ms

    for index, beat in enumerate(beats):
        if len(candidates) >= max_scenes:
            skipped.append({"beat_index": index, "reason": "density_limit"})
            continue
        reason = "missing_reviewed_visual"
        for template in pack.template_priority[beat["purpose"]]:
            if template not in beat["visuals"]:
                continue
            if template == "metric_spotlight" and not beat["evidence_verified"]:
                reason = "unverified_metric"
                continue
            spec = TEMPLATES[template]
            start = max(beat["start_ms"], previous_end + pack.min_gap_ms)
            duration = min(beat["end_ms"] - start, pack.max_scene_ms,
                           spec.get("max_duration_ms", 12000))
            if duration < spec.get("min_duration_ms", 2500):
                reason = "insufficient_space"
                continue
            identifier = sha256(
                f"pausio-style-v{PACK_VERSION}:{style_id}:{index}:{template}:{start}"
                .encode("ascii")
            ).hexdigest()[:32]
            scene = {
                "id": identifier, "template": template,
                "start_ms": start, "duration_ms": duration,
                "accent": pack.accent,
                "content": beat["visuals"][template],
            }
            try:
                scene = validate_scene(scene, output_ms)
            except ValueError:
                reason = "invalid_or_incomplete_reviewed_visual"
                continue
            candidates.append({
                "beat_index": index,
                "purpose": beat["purpose"],
                "command_type": "scene.template.add",
                "payload": {"scene": scene},
            })
            previous_end = start + duration
            break
        else:
            skipped.append({"beat_index": index, "reason": reason})

    return {
        "style_id": pack.id,
        "style_version": PACK_VERSION,
        "output_ms": output_ms,
        "caption_preset_suggestion": pack.caption_preset,
        "camera_preset_suggestion": pack.camera_preset,
        "editorial_preset_suggestion": pack.editorial_preset,
        "candidates": candidates,
        "skipped": skipped,
        "requires_editor_review": True,
    }


def propose_three_variants(beats: list[dict], output_ms: int) -> dict[str, dict]:
    """Three independent suggestions on the SAME edited-output timeline."""
    return {pack.id: propose_variant(beats, output_ms, pack.id) for pack in _PACKS}
