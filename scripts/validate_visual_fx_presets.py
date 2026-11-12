"""Validate design-only automatic visual-FX preset data with the stdlib.

This does NOT implement or run any video effect. It prevents unsafe/unknown
configuration values from silently entering the future suggestion engine.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "visual_fx_presets_v1.json"
PROFILE_IDS = ("naturale", "educativo", "dinamico", "personalizzato")
SIGNALS = frozenset({
    "cut_boundary", "phrase_boundary", "speech_energy",
    "face_stability", "scene_change", "semantic_marker",
})
PROFILE_FIELDS = frozenset({
    "id", "label", "description", "execution_mode", "allowed_moves",
    "cadence", "zoom", "transition", "signals", "guards",
})
ALLOWED_MOVES = frozenset({"punch", "slow_push", "ratchet"})
ALLOWED_TRANSITIONS = frozenset({"hard_cut", "dissolve", "dip_black"})


def _number(value: Any, lo: float, hi: float, *, integer: bool = False) -> bool:
    if integer:
        return type(value) is int and lo <= value <= hi
    return type(value) in (int, float) and math.isfinite(value) and lo <= value <= hi


def _keys(value: Any, required: set[str] | frozenset[str]) -> bool:
    return isinstance(value, dict) and set(value) == set(required)


def validate(data: Any) -> list[str]:
    problems: list[str] = []
    expected_top = {
        "format", "schema_version", "status", "default_profile",
        "selector_version", "profiles",
    }
    if not _keys(data, expected_top):
        return ["Preset root must be an object with exactly the approved keys"]
    expected = {
        "format": "pausio.visual_fx_presets",
        "schema_version": 1,
        "status": "design_only_not_connected_to_renderer",
        "default_profile": "naturale",
        "selector_version": "weighted-gates-v1",
    }
    for name, value in expected.items():
        if type(data[name]) is not type(value) or data[name] != value:
            problems.append(f"{name}: expected {value!r}")

    profiles = data["profiles"]
    if not _keys(profiles, set(PROFILE_IDS)):
        return problems + ["profiles: expected exactly naturale, educativo, dinamico, personalizzato"]

    for preset_id, p in profiles.items():
        prefix = f"profiles.{preset_id}"
        if not _keys(p, PROFILE_FIELDS):
            problems.append(f"{prefix}: unknown or missing profile fields")
            continue
        if p["id"] != preset_id or not isinstance(p["id"], str):
            problems.append(f"{prefix}.id must match profile key")
        for key, limit in (("label", 60), ("description", 200)):
            if not isinstance(p[key], str) or not 1 <= len(p[key]) <= limit:
                problems.append(f"{prefix}.{key}: invalid text")
        if p["execution_mode"] != "suggest":
            problems.append(f"{prefix}.execution_mode: must be 'suggest'; never auto-apply")
        moves = p["allowed_moves"]
        if not isinstance(moves, list) or not 1 <= len(moves) <= 3 or any(
            not isinstance(x, str) or x not in ALLOWED_MOVES for x in moves
        ) or len(moves) != len(set(moves)) or "punch" not in moves:
            problems.append(f"{prefix}.allowed_moves: invalid or duplicate")

        cadence = p["cadence"]
        if not _keys(cadence, {"max_effects_per_minute", "min_gap_ms", "min_segment_ms"}):
            problems.append(f"{prefix}.cadence: missing or extra keys")
        else:
            for field, lo, hi in (("max_effects_per_minute", 0, 12),
                                   ("min_gap_ms", 1500, 30000),
                                   ("min_segment_ms", 500, 30000)):
                if not _number(cadence[field], lo, hi, integer=True):
                    problems.append(f"{prefix}.cadence.{field}: outside safe bounds")

        zoom = p["zoom"]
        zoom_fields = {"punch_min_scale", "punch_max_scale", "punch_ramp_ms",
                       "punch_hold_ms", "slow_push_max_scale", "slow_push_duration_ms"}
        if not _keys(zoom, zoom_fields):
            problems.append(f"{prefix}.zoom: missing or extra keys")
        else:
            for field in ("punch_min_scale", "punch_max_scale", "slow_push_max_scale"):
                if not _number(zoom[field], 1.0, 1.3):
                    problems.append(f"{prefix}.zoom.{field}: allowed [1,1.3]")
            if _number(zoom["punch_min_scale"], 1, 1.3) and _number(
                zoom["punch_max_scale"], 1, 1.3
            ) and zoom["punch_min_scale"] > zoom["punch_max_scale"]:
                problems.append(f"{prefix}.zoom: min scale exceeds max")
            for field, lo, hi in (("punch_ramp_ms", 0, 600),
                                   ("punch_hold_ms", 150, 2500),
                                   ("slow_push_duration_ms", 700, 15000)):
                if not _number(zoom[field], lo, hi, integer=True):
                    problems.append(f"{prefix}.zoom.{field}: outside safe bounds")

        transitions = p["transition"]
        fields = {"allowed_kinds", "max_per_minute", "duration_ms", "context_change_only"}
        if not _keys(transitions, fields):
            problems.append(f"{prefix}.transition: missing or extra keys")
        else:
            allowed = transitions["allowed_kinds"]
            if not isinstance(allowed, list) or not allowed or any(
                not isinstance(v, str) or v not in ALLOWED_TRANSITIONS for v in allowed
            ) or len(set(allowed)) != len(allowed) or "hard_cut" not in allowed:
                problems.append(f"{prefix}.transition.allowed_kinds: invalid")
            elif not _number(transitions["max_per_minute"], 0, 3, integer=True):
                problems.append(f"{prefix}.transition.max_per_minute: invalid")
            elif transitions["context_change_only"] is not True:
                problems.append(f"{prefix}.transition: transitions must be contextual")
            elif transitions["max_per_minute"] == 0 and (
                allowed != ["hard_cut"] or transitions["duration_ms"] != 0
            ):
                problems.append(f"{prefix}.transition: hard-cut-only must have 0ms")
            elif transitions["max_per_minute"] > 0 and (
                len(allowed) < 2 or not _number(transitions["duration_ms"], 80, 350, integer=True)
            ):
                problems.append(f"{prefix}.transition: contextual transition settings invalid")

        weights = p["signals"]
        if not _keys(weights, SIGNALS):
            problems.append(f"{prefix}.signals: missing or extra weights")
        elif any(not _number(v, 0, 100, integer=True) for v in weights.values()):
            problems.append(f"{prefix}.signals: weights must be integers 0..100")
        elif sum(weights.values()) != 100 or weights["cut_boundary"] == 0:
            problems.append(f"{prefix}.signals: weights must sum to 100 and include cuts")

        guards = p["guards"]
        gf = {"protect_manual_edits", "protect_speech", "face_margin_pct",
              "cut_guard_ms", "minimum_source_width_px"}
        if not _keys(guards, gf):
            problems.append(f"{prefix}.guards: missing or extra gates")
        else:
            if guards["protect_manual_edits"] is not True or guards["protect_speech"] is not True:
                problems.append(f"{prefix}.guards: protected edits and speech cannot be disabled")
            for field, lo, hi, integer in (
                ("face_margin_pct", 0.04, 0.2, False),
                ("cut_guard_ms", 100, 1000, True),
                ("minimum_source_width_px", 360, 2160, True),
            ):
                if not _number(guards[field], lo, hi, integer=integer):
                    problems.append(f"{prefix}.guards.{field}: outside safe bounds")
    return problems


def main() -> int:
    try:
        document = json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"FX preset config cannot be read: {type(exc).__name__}", file=sys.stderr)
        return 1
    problems = validate(document)
    if problems:
        for problem in problems:
            print("FX CONFIG ERROR:", problem, file=sys.stderr)
        return 1
    print(f"Validated {len(PROFILE_IDS)} bounded, design-only Pausio visual FX profiles.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
