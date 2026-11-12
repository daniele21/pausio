"""Conservative, deterministic, non-mutating visual-FX suggestions.

Only objective KEEP/cut boundaries and real timestamped ASR phrases are used.
No semantic reasoning, model APIs, face recognition, media downloads, or
unbounded rendering. The caller must validate the revision and source hash.
"""
from __future__ import annotations

import hashlib
import math
from typing import Any

PROFILE_RULES = {
    "naturale": {
        "max_per_min": 3, "gap_ms": 8000, "min_segment_ms": 1400,
        "punch_pct": 116, "push_pct": 110, "push_ms": 2600,
    },
    "educativo": {
        "max_per_min": 6, "gap_ms": 4500, "min_segment_ms": 1100,
        "punch_pct": 118, "push_pct": 113, "push_ms": 2200,
    },
    "dinamico": {
        "max_per_min": 10, "gap_ms": 2800, "min_segment_ms": 850,
        "punch_pct": 125, "push_pct": 116, "push_ms": 1800,
    },
    "personalizzato": {
        "max_per_min": 6, "gap_ms": 4500, "min_segment_ms": 1100,
        "punch_pct": 118, "push_pct": 113, "push_ms": 2200,
    },
}
ENGINE = "pausio.visualfx.cut-phrase-v1"
MAX_INPUT_SEGMENTS = 200
MAX_WORD_PHRASES = 1000
MAX_CANDIDATES = 18

CUSTOM_LIMITS = {"max_per_min":(1,10), "gap_ms":(2500,12000),
                 "punch_pct":(105,125), "push_pct":(105,120),
                 "push_ms":(1200,4000)}


def _config(preset: str, overrides: dict | None) -> tuple[dict, bool]:
    if overrides is None:
        return dict(PROFILE_RULES[preset]), False
    if preset != "personalizzato" or not isinstance(overrides,dict):
        raise ValueError("Only personalizzato accepts custom settings")
    if set(overrides)!=(set(CUSTOM_LIMITS)|{"use_audio_energy"}):
        raise ValueError("Incomplete or unknown custom FX settings")
    cfg=dict(PROFILE_RULES[preset])
    for name,(low,high) in CUSTOM_LIMITS.items():
        value=overrides[name]
        if type(value) is not int or not low<=value<=high:
            raise ValueError(f"Invalid custom FX setting {name}")
        cfg[name]=value
    if type(overrides["use_audio_energy"]) is not bool:
        raise ValueError("Invalid use_audio_energy toggle")
    if cfg["gap_ms"]<cfg["push_ms"]:
        raise ValueError("FX gap cannot be shorter than the push duration")
    return cfg,overrides["use_audio_energy"]


def _audio_peaks(waveform: list[int] | None) -> list[int]:
    if waveform is None:
        return []
    if (not isinstance(waveform,list) or len(waveform)!=900 or
            any(type(v) is not int or not 0<=v<=1000 for v in waveform)):
        raise ValueError("Invalid measured waveform")
    return waveform



def _as_ms(value: Any) -> int | None:
    if type(value) is int and 0 <= value <= 172_800_000:
        return value
    return None


def _identity(parts: tuple[object, ...]) -> str:
    return hashlib.sha256("|".join(map(str, parts)).encode("utf-8")).hexdigest()[:32]


def _real_phrases(transcript: Any) -> list[int]:
    if not isinstance(transcript, dict):
        return []
    source = transcript.get("segments")
    if not isinstance(source, list) or len(source) > MAX_WORD_PHRASES:
        return []
    phrase_starts = []
    for item in source:
        if not isinstance(item, dict):
            continue
        start, end = _as_ms(item.get("start_ms")), _as_ms(item.get("end_ms"))
        if start is not None and end is not None and start < end:
            phrase_starts.append(start)
    return sorted(set(phrase_starts))


def propose_visual_fx(
    *,
    segments: list[dict], transcript: dict | None, existing: list[dict],
    preset: str, media_sha256: str, base_revision: int,
    overrides: dict | None = None, waveform: list[int] | None = None,
    source_duration_ms: int | None = None,
) -> dict:
    if preset not in PROFILE_RULES or type(preset) is not str:
        raise ValueError("Unsupported visual FX preset")
    if (type(base_revision) is not int or base_revision < 0 or
            type(media_sha256) is not str or len(media_sha256) != 64 or
            any(c not in "0123456789abcdef" for c in media_sha256)):
        raise ValueError("Invalid media binding or project revision")
    if not isinstance(segments, list) or len(segments) > MAX_INPUT_SEGMENTS:
        raise ValueError("Invalid KEEP segment list")
    if not isinstance(existing, list) or len(existing) > MAX_CANDIDATES:
        raise ValueError("Invalid existing visual FX")
    rule, audio_enabled = _config(preset,overrides)
    peaks = _audio_peaks(waveform) if audio_enabled else []
    if peaks and (type(source_duration_ms) is not int or not 0<source_duration_ms<=172_800_000):
        raise ValueError("Waveform requires precise media duration")
    proposals = []
    output_offset = 0
    last_end = 0
    phrases = _real_phrases(transcript)

    for index, seg in enumerate(segments):
        if not isinstance(seg, dict) or set(seg) != {"id","start_ms","end_ms"}:
            raise ValueError("Malformed source segment")
        seg_id = seg["id"]
        a, b = _as_ms(seg["start_ms"]), _as_ms(seg["end_ms"])
        if (type(seg_id) is not str or len(seg_id) != 32 or
                any(ch not in "0123456789abcdef" for ch in seg_id) or
                a is None or b is None or a >= b or a < last_end):
            raise ValueError("Invalid source KEEP interval")
        duration = b - a
        if index > 0 and a - last_end >= 350 and duration >= rule["min_segment_ms"]:
            start=a + min(150,max(0,duration//12))
            end=min(b,start+min(1250,duration-200))
            if end-start>=250:
                proposals.append({
                    "priority": 85 if preset != "dinamico" else 88,
                    "source_output_ms": output_offset+(start-a),
                    "kind":"punch", "segment_id":seg_id,
                    "start_ms":start,"end_ms":end,
                    "start_scale_pct":rule["punch_pct"],
                    "end_scale_pct":rule["punch_pct"],
                    "reason":"cut_boundary",
                    "evidence_ms":a, "evidence_value":a-last_end,
                })

        # A real ASR phrase boundary can be a technical timing cue, not an
        # editorial assertion. Require a sufficiently long, continuous span.
        if duration >= rule["push_ms"]+900:
            for moment in phrases:
                if a+650 <= moment <= b-rule["push_ms"]-150:
                    # One phrase-driven slow move candidate per KEEP region.
                    proposals.append({
                        "priority": 60,
                        "source_output_ms":output_offset+(moment-a),
                        "kind":"slow_push","segment_id":seg_id,
                        "start_ms":moment, "end_ms":moment+rule["push_ms"],
                        "start_scale_pct":100,"end_scale_pct":rule["push_pct"],
                        "reason":"asr_phrase_boundary",
                        "evidence_ms":moment,"evidence_value":1,
                    })
                    break
        # Optional waveform energy is a technical onset, never an emotional
        # importance score. The original PCM envelope already exists locally.
        if peaks and duration >= rule["push_ms"]+900:
            lo=max(4,math.ceil((a+650)*len(peaks)/source_duration_ms))
            hi=min(len(peaks)-1,math.floor((b-rule["push_ms"]-150)*len(peaks)/source_duration_ms))
            if lo<=hi:
                rises=[]
                for j in range(lo,hi+1):
                    baseline=sum(peaks[j-4:j])/4
                    delta=peaks[j]-baseline
                    if peaks[j]>=620 and delta>=330:
                        rises.append((delta,j))
                if rises:
                    delta,j=max(rises)
                    moment=round(j*source_duration_ms/len(peaks))
                    if moment>=a+650 and moment+rule["push_ms"]+150<=b:
                        proposals.append({
                            "priority": 65,
                            "source_output_ms":output_offset+(moment-a),
                            "kind":"slow_push","segment_id":seg_id,
                            "start_ms":moment,"end_ms":moment+rule["push_ms"],
                            "start_scale_pct":100,
                            "end_scale_pct":rule["push_pct"],
                            "reason":"measured_waveform_rise",
                            "evidence_ms":moment,"evidence_value":round(delta),
                        })
        output_offset += duration
        last_end=b
    # The budget is a maximum, not a quota. Empty is success.
    total_budget=min(MAX_CANDIDATES,
        math.ceil(output_offset*rule["max_per_min"]/60000)) if output_offset else 0
    proposals.sort(key=lambda c:(-c["priority"],c["source_output_ms"],
                                 c["segment_id"],c["kind"]))
    chosen = []
    for item in proposals:
        if len(chosen) >= total_budget:
            break
        if any(abs(item["source_output_ms"]-prev["output_time_ms"]) < rule["gap_ms"]
               for prev in chosen):
            continue
        if any(item["segment_id"] == fx.get("segment_id") and
               item["start_ms"] < fx.get("end_ms",0) and
               item["end_ms"] > fx.get("start_ms",0) for fx in existing
               if isinstance(fx,dict)):
            continue
        signature=tuple((key,rule[key]) for key in sorted(CUSTOM_LIMITS))
        effect_id=_identity((ENGINE,media_sha256,preset,signature,audio_enabled,
                             item["segment_id"],item["start_ms"],item["kind"]))
        effect={key:item[key] for key in (
            "segment_id","start_ms","end_ms","kind","start_scale_pct",
            "end_scale_pct"
        )}
        effect.update({
            "id":effect_id,"anchor_x_pct":50,"anchor_y_pct":48
        })
        chosen.append({
            "candidate_id":effect_id, "effect":effect,
            "score_0_100":item["priority"],
            "output_time_ms":item["source_output_ms"],
            "evidence":{"kind":item["reason"],"source_ms":item["evidence_ms"],
                        "value":item["evidence_value"]},
        })
    chosen.sort(key=lambda c:c["output_time_ms"])
    return {
        "engine": ENGINE, "preset":preset,"base_revision":base_revision,
        "media_sha256":media_sha256,
        "effective_profile": {key:rule[key] for key in CUSTOM_LIMITS},
        "audio_energy_used": bool(peaks),
        "missing_signals":(["waveform_energy"] if audio_enabled and not peaks else []) +
                          ["semantic_prosody","face_tracking","scene_detection"] +
                          ([] if phrases else ["asr_phrases"]),
        "total_output_ms":output_offset,
        "candidates":chosen,
    }
