"""Deterministic, conservative proposals. Never silently remove spoken material."""

from __future__ import annotations

from dataclasses import dataclass

from pausio.domain import Interval


@dataclass(frozen=True, slots=True)
class NaturalPreset:
    # A long pause is only a *candidate*. This is not transcript-aware editing.
    min_silence_ms: int = 900
    min_removed_ms: int = 500
    speech_padding_before_ms: int = 200
    speech_padding_after_ms: int = 250
    min_keep_ms: int = 350
    edge_tolerance_ms: int = 80


AI_NATURAL = NaturalPreset()

# Presets affect deterministic FFmpeg proposals, never directly authorize export.
# Persist the exact chosen values in portable analysis.propose commands.
CUT_PRESETS: dict[str, dict[str, int]] = {
    "natural": {
        "noise_db": -35, "min_silence_ms": 900, "min_removed_ms": 500,
        "speech_padding_before_ms": 200, "speech_padding_after_ms": 250,
        "min_keep_ms": 350,
    },
    "balanced": {
        "noise_db": -30, "min_silence_ms": 600, "min_removed_ms": 200,
        "speech_padding_before_ms": 125, "speech_padding_after_ms": 125,
        "min_keep_ms": 300,
    },
    "dynamic": {
        "noise_db": -25, "min_silence_ms": 350, "min_removed_ms": 100,
        "speech_padding_before_ms": 75, "speech_padding_after_ms": 75,
        "min_keep_ms": 200,
    },
}
CUT_SETTING_LIMITS: dict[str, tuple[int, int]] = {
    "noise_db": (-55, -15),
    "min_silence_ms": (200, 2000),
    "min_removed_ms": (50, 1000),
    "speech_padding_before_ms": (0, 600),
    "speech_padding_after_ms": (0, 600),
    "min_keep_ms": (50, 1000),
}


def validate_cut_settings(raw: object | None = None) -> dict[str, int | str]:
    """Validate portable analysis settings, preserving legacy Natural defaults."""
    if raw is None:
        return {"preset": "natural", **CUT_PRESETS["natural"]}
    if not isinstance(raw, dict) or set(raw) != {"preset", *CUT_SETTING_LIMITS}:
        raise ValueError("Impostazioni tagli: campi mancanti o sconosciuti.")
    preset = raw["preset"]
    if not isinstance(preset, str) or preset not in {*CUT_PRESETS, "custom"}:
        raise ValueError("Preset di montaggio non riconosciuto.")
    settings: dict[str, int | str] = {"preset": preset}
    for key, (minimum, maximum) in CUT_SETTING_LIMITS.items():
        value = raw[key]
        if type(value) is not int or not minimum <= value <= maximum:
            raise ValueError(f"{key} deve essere un intero tra {minimum} e {maximum}.")
        settings[key] = value
    if settings["min_removed_ms"] > settings["min_silence_ms"]:
        raise ValueError("Il taglio minimo non può superare la pausa minima.")
    if preset != "custom" and any(
        settings[key] != expected for key, expected in CUT_PRESETS[preset].items()
    ):
        raise ValueError("Il preset è stato modificato: seleziona Personalizzato.")
    return settings


def policy_from_cut_settings(settings: dict[str, int | str]) -> NaturalPreset:
    """Translate the validated preset into a pure editing policy."""
    validated = validate_cut_settings(settings)
    return NaturalPreset(
        min_silence_ms=int(validated["min_silence_ms"]),
        min_removed_ms=int(validated["min_removed_ms"]),
        speech_padding_before_ms=int(validated["speech_padding_before_ms"]),
        speech_padding_after_ms=int(validated["speech_padding_after_ms"]),
        min_keep_ms=int(validated["min_keep_ms"]),
    )


def _merge_intervals(intervals: list[Interval]) -> list[Interval]:
    merged: list[Interval] = []
    for item in sorted(intervals, key=lambda x: (x.start_ms, x.end_ms)):
        if merged and item.start_ms <= merged[-1].end_ms:
            last = merged.pop()
            merged.append(Interval(last.start_ms, max(last.end_ms, item.end_ms)))
        else:
            merged.append(item)
    return merged


def propose_segments(
    duration_ms: int,
    silences: list[Interval],
    policy: NaturalPreset = AI_NATURAL,
) -> tuple[Interval, ...]:
    """Retain speech plus human pacing; only remove the middle of long silences.

    Edge silence gets trimmed more aggressively. Adjacent internal retained clips
    shorter than min_keep_ms are protected rather than blindly fragmented.
    """
    if duration_ms <= 0:
        raise ValueError("duration_ms must be positive")

    normalized: list[Interval] = []
    for s in silences:
        start = min(max(s.start_ms, 0), duration_ms)
        end = min(max(s.end_ms, 0), duration_ms)
        if end > start:
            normalized.append(Interval(start, end))

    cuts: list[Interval] = []
    for gap in _merge_intervals(normalized):
        if gap.duration_ms < policy.min_silence_ms:
            continue
        start = (
            0 if gap.start_ms <= policy.edge_tolerance_ms
            else gap.start_ms + policy.speech_padding_before_ms
        )
        end = (
            duration_ms if duration_ms - gap.end_ms <= policy.edge_tolerance_ms
            else gap.end_ms - policy.speech_padding_after_ms
        )
        if end - start >= policy.min_removed_ms:
            cuts.append(Interval(start, end))

    keep: list[Interval] = []
    cursor = 0
    for cut in cuts:
        if cut.start_ms > cursor:
            candidate = Interval(cursor, cut.start_ms)
            if candidate.duration_ms < policy.min_keep_ms and cut.start_ms != 0:
                # Keep this short material by rejecting the proposed cut entirely.
                continue
            keep.append(candidate)
        cursor = cut.end_ms
    if cursor < duration_ms:
        tail = Interval(cursor, duration_ms)
        if tail.duration_ms < policy.min_keep_ms and keep:
            # Avoid an almost-empty final shot; retain footage from the last cut.
            previous = keep.pop()
            keep.append(Interval(previous.start_ms, duration_ms))
        else:
            keep.append(tail)
    if not keep:
        # If analysis suggests all content is silence, preserve the source.
        return (Interval(0, duration_ms),)
    return tuple(keep)
