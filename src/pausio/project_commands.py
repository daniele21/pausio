"""Portable, versioned, deterministic editing instructions for Pausio Studio.

The UI sends *commands*, never an untracked changed timeline. This module
validates and replays every event without FFmpeg, ASR, browser or file access.
A .pausio.json is data, not executable instructions or a source path.
"""

from __future__ import annotations

import copy
import re
import uuid
from dataclasses import dataclass
from typing import Any

from pausio.captions import (
    CAPTION_STYLES, MAX_CAPTIONS, MAX_CAPTION_LENGTH,
    default_caption_config, validate_caption_config
)
from pausio.domain import EditPlan, Interval
from pausio.visual_transitions import compile_dips, MAX_TRANSITIONS
from pausio.graphic_overlays import validate_graphic, validate_graphics
from pausio.planner import CUT_PRESETS, validate_cut_settings

FORMAT = "pausio.project"
VERSION = 5
PREVIOUS_VERSION = 4
V3_VERSION = 3
MIGRATION_VERSION = 2
LEGACY_VERSION = 1
MAX_COMMANDS = 2000
MAX_REVISION = 2_147_483_647
MAX_SEGMENTS = 200
_MAX_NAME = 160
_HEX = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[0-9a-f]{32}$")
_TYPES = frozenset({
    "analysis.propose",
    "timeline.replace",
    "segment.update",
    "segment.remove",
    "segment.insert",
    "timeline.restore_suggestion",
    "timeline.keep_all",
    "timeline.approve",
    "caption.set",
    "caption.correct",
    "caption.retime",
    "caption.style",
    "caption.configure",
    "caption.clear",
    "audio.add",
    "audio.update",
    "audio.remove",
    "audio.mixer.configure",
    "audio.clip.mix",
    "graphic.overlay.add",
    "graphic.overlay.update",
    "graphic.overlay.remove",
    "video.transform.add",
    "video.transform.update",
    "video.transform.remove",
    "video.transition.add",
    "video.transition.update",
    "video.transition.remove",
})
UI_COMMANDS = frozenset(_TYPES - {"analysis.propose", "timeline.replace"})


class ProjectFormatError(ValueError):
    """Reject malformed, stale or unsupported editing instructions."""


def _object(value: Any, keys: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise ProjectFormatError(f"{label}: expected fields {sorted(keys)}")
    return value


def _integer(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ProjectFormatError(f"{label}: expected integer milliseconds")
    return value


def _id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ProjectFormatError(f"{label}: expected 32 lowercase hex characters")
    return value


def _validate_media(media: Any) -> dict:
    d = _object(media, {"filename", "sha256", "duration_ms", "has_audio"}, "media")
    filename = d["filename"]
    if (
        not isinstance(filename, str) or not 1 <= len(filename) <= _MAX_NAME
        or "/" in filename or "\\" in filename or filename in {".", ".."}
        or "\x00" in filename
    ):
        raise ProjectFormatError("media.filename must be a safe basename (no path)")
    if not isinstance(d["sha256"], str) or not _HEX.fullmatch(d["sha256"]):
        raise ProjectFormatError("media.sha256 must be a lowercase SHA-256 digest")
    duration = _integer(d["duration_ms"], "media.duration_ms")
    if not 0 < duration <= 172_800_000:
        raise ProjectFormatError("media duration must be between 1 ms and 48 hours")
    if not isinstance(d["has_audio"], bool):
        raise ProjectFormatError("media.has_audio must be boolean")
    return copy.deepcopy(d)


def _segments(raw: Any, duration_ms: int) -> list[dict]:
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_SEGMENTS:
        raise ProjectFormatError("segments must be a nonempty list (maximum 200)")
    seen = set()
    cleaned = []
    for row in raw:
        s = _object(row, {"id", "start_ms", "end_ms"}, "segment")
        ident = _id(s["id"], "segment.id")
        if ident in seen:
            raise ProjectFormatError("duplicate segment id")
        seen.add(ident)
        start = _integer(s["start_ms"], "start_ms")
        end = _integer(s["end_ms"], "end_ms")
        try:
            Interval(start, end)
        except ValueError as exc:
            raise ProjectFormatError(str(exc)) from exc
        cleaned.append({"id": ident, "start_ms": start, "end_ms": end})
    _check_timeline(cleaned, duration_ms)
    return cleaned


def _check_timeline(rows: list[dict], duration_ms: int) -> None:
    if not 1 <= len(rows) <= MAX_SEGMENTS:
        raise ProjectFormatError("plan must retain 1..200 segments")
    previous = 0
    for s in rows:
        if s["start_ms"] < previous or s["end_ms"] > duration_ms:
            raise ProjectFormatError("segments must be ordered, non-overlapping, and in bounds")
        previous = s["end_ms"]


def _caption_text(value: Any) -> str:
    if (
        not isinstance(value, str) or not value.strip()
        or len(value) > MAX_CAPTION_LENGTH
        or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)
        or any(ch in value for ch in "{}\\")
    ):
        raise ProjectFormatError("Testo sottotitolo non valido (massimo 300 caratteri).")
    return value.strip()


def _captions(raw: Any, duration_ms: int) -> list[dict]:
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_CAPTIONS:
        raise ProjectFormatError("I sottotitoli devono essere tra 1 e 500.")
    last_end = 0
    ids = set()
    result = []
    for row in raw:
        cue = _object(row, {"id", "start_ms", "end_ms", "text"}, "caption")
        ident = _id(cue["id"], "caption.id")
        start = _integer(cue["start_ms"], "caption.start_ms")
        end = _integer(cue["end_ms"], "caption.end_ms")
        if ident in ids or start < last_end or not start < end <= duration_ms:
            raise ProjectFormatError("Sottotitoli sovrapposti, duplicati o fuori dal video.")
        ids.add(ident)
        last_end = end
        result.append({
            "id": ident, "start_ms": start, "end_ms": end,
            "text": _caption_text(cue["text"])
        })
    return result


def default_audio_mix() -> dict:
    """Canonical default for old projects without mixer events."""
    return {"voice_gain_db": 0, "voice_muted": False,
            "fx_gain_db": 0, "fx_muted": False}


def validate_audio_mix(raw: Any) -> dict:
    mix = _object(raw, set(default_audio_mix()), "audio.mixer.configure")
    for key in ("voice_gain_db", "fx_gain_db"):
        if type(mix[key]) is not int or not -36 <= mix[key] <= 12:
            raise ProjectFormatError(f"{key} must be an integer from -36 to +12 dB")
    for key in ("voice_muted", "fx_muted"):
        if type(mix[key]) is not bool:
            raise ProjectFormatError(f"{key} must be boolean")
    return dict(mix)


def _audio_clip(raw: Any, media_duration: int) -> dict:
    fields = {"id", "asset_sha256", "filename", "start_ms", "duration_ms", "gain_db"}
    if not isinstance(raw, dict) or not fields <= set(raw) or set(raw) - fields - {"muted"}:
        raise ProjectFormatError("audio clip has missing or unknown fields")
    clip = raw
    ident = _id(clip["id"], "audio clip.id")
    digest = clip["asset_sha256"]
    if not isinstance(digest, str) or not _HEX.fullmatch(digest):
        raise ProjectFormatError("audio asset digest must be SHA-256")
    name = clip["filename"]
    if (not isinstance(name, str) or not 1 <= len(name) <= _MAX_NAME
            or "/" in name or "\\" in name or any(ord(ch) < 32 for ch in name)
            or not name.lower().endswith((".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"))):
        raise ProjectFormatError("audio filename not supported")
    start = _integer(clip["start_ms"], "audio.start_ms")
    length = _integer(clip["duration_ms"], "audio.duration_ms")
    gain = clip["gain_db"]
    if not 0 <= start < media_duration or not 0 < length <= 180_000:
        raise ProjectFormatError("audio effect start/duration outside bounds")
    if type(gain) is not int or not -36 <= gain <= 12:
        raise ProjectFormatError("audio gain_db must be between -36 and 12")
    if "muted" in clip and type(clip["muted"]) is not bool:
        raise ProjectFormatError("audio clip.muted must be boolean")
    result = {
        "id": ident, "asset_sha256": digest, "filename": name,
        "start_ms": start, "duration_ms": length, "gain_db": gain
    }
    if "muted" in clip:
        result["muted"] = clip["muted"]
    return result


MAX_VIDEO_FX = 18


def _video_transform(raw: Any, segments: list[dict], duration_ms: int) -> dict:
    """Validate one source-anchored motion event; no FFmpeg expressions allowed."""
    fields = {"id", "segment_id", "start_ms", "end_ms", "kind",
              "start_scale_pct", "end_scale_pct", "anchor_x_pct", "anchor_y_pct"}
    fx = _object(raw, fields, "video transform")
    result = dict(fx)
    _id(fx["id"], "video effect.id")
    _id(fx["segment_id"], "video effect.segment_id")
    segment = next((row for row in segments if row["id"] == fx["segment_id"]), None)
    if segment is None:
        raise ProjectFormatError("Video FX refers to a removed segment")
    start = _integer(fx["start_ms"], "video FX start_ms")
    end = _integer(fx["end_ms"], "video FX end_ms")
    if not (0 <= start < end <= duration_ms and
            segment["start_ms"] <= start and end <= segment["end_ms"]):
        raise ProjectFormatError("Video FX must be inside its source KEEP segment")
    if end - start < 250 or end - start > 60_000:
        raise ProjectFormatError("Video FX must last between 250ms and 60 seconds")
    if type(fx["kind"]) is not str or fx["kind"] not in ("punch", "slow_push", "ease_push", "ratchet", "pulse", "sweep"):
        raise ProjectFormatError("Unsupported video FX kind")
    for key in ("start_scale_pct", "end_scale_pct"):
        value = _integer(fx[key], key)
        if not 100 <= value <= 130:
            raise ProjectFormatError("Video zoom limited to 1.00x-1.30x")
    if fx["kind"] == "ratchet" and end-start < 1200:
        raise ProjectFormatError("Ratchet needs at least 1.2s for three stable steps")
    if fx["kind"] == "pulse" and end-start < 900:
        raise ProjectFormatError("Pulse needs 900ms to rise and return smoothly")
    if fx["kind"] == "sweep" and end-start < 1300:
        raise ProjectFormatError("Sweep needs 1300ms of source KEEP footage")
    if fx["kind"] == "pulse" and fx["start_scale_pct"] != 100:
        raise ProjectFormatError("Pulse must start from 100%; end zoom is its peak")
    if fx["kind"] == "punch" and fx["start_scale_pct"] != fx["end_scale_pct"]:
        raise ProjectFormatError("Punch must have a constant zoom")
    for key in ("anchor_x_pct", "anchor_y_pct"):
        value = _integer(fx[key], key)
        if not 0 <= value <= 100:
            raise ProjectFormatError("Video FX anchor must be 0..100 percent")
    return result


def _validate_video_fx(items: list[dict], segments: list[dict], duration_ms: int) -> None:
    if len(items) > MAX_VIDEO_FX:
        raise ProjectFormatError("Maximum 18 video effects per project")
    unique = set()
    for fx in items:
        _video_transform(fx, segments, duration_ms)
        if fx["id"] in unique:
            raise ProjectFormatError("Duplicate video effect ID")
        unique.add(fx["id"])
    for i, left in enumerate(items):
        for right in items[i + 1:]:
            if (left["segment_id"] == right["segment_id"] and
                    left["start_ms"] < right["end_ms"] and
                    right["start_ms"] < left["end_ms"]):
                raise ProjectFormatError("Overlapping video FX must be resolved before applying")


def _video_transition(raw: Any, segments: list[dict]) -> dict:
    """A dip on a specific ADJACENT original KEEP pair, no A/V overlap."""
    trans = _object(raw, {"id","left_segment_id","right_segment_id",
                          "kind","duration_ms"}, "video transition")
    _id(trans["id"], "transition.id")
    left = _id(trans["left_segment_id"], "transition.left")
    right = _id(trans["right_segment_id"], "transition.right")
    if trans["kind"] != "dip_black" or type(trans["kind"]) is not str:
        raise ProjectFormatError("Unsupported video cut transition")
    duration=_integer(trans["duration_ms"],"transition.duration_ms")
    if not 200<=duration<=600:
        raise ProjectFormatError("Transition must last 200..600 ms")
    pair=next((i for i in range(len(segments)-1)
               if segments[i]["id"]==left and segments[i+1]["id"]==right),None)
    if pair is None:
        raise ProjectFormatError("Transition requires two adjacent KEEP segments")
    return dict(trans)


def _validate_video_transitions(items: list[dict], segments: list[dict]) -> None:
    if len(items)>MAX_TRANSITIONS:
        raise ProjectFormatError("Too many video transitions")
    ids=set()
    pairs=[]
    for item in items:
        row=_video_transition(item,segments)
        if row["id"] in ids:
            raise ProjectFormatError("Duplicate visual transition ID")
        ids.add(row["id"])
        pair=next(i for i in range(len(segments)-1)
                  if segments[i]["id"]==row["left_segment_id"] and
                     segments[i+1]["id"]==row["right_segment_id"])
        pairs.append({"boundary_index":pair,"kind":row["kind"],
                      "duration_ms":row["duration_ms"]})
    try:
        compile_dips(tuple(Interval(s["start_ms"],s["end_ms"]) for s in segments),pairs)
    except ValueError as exc:
        raise ProjectFormatError(str(exc)) from exc


@dataclass(frozen=True)
class ProjectView:
    segments: tuple[dict, ...] = ()
    suggested: tuple[dict, ...] | None = None
    approved: bool = False
    analysis_settings: dict | None = None
    detected_silences: int | None = None
    captions: tuple[dict, ...] = ()
    caption_style: str = "social"
    caption_config: dict | None = None
    audio_clips: tuple[dict, ...] = ()
    audio_mix: dict | None = None
    video_fx: tuple[dict, ...] = ()
    video_transitions: tuple[dict, ...] = ()
    graphic_overlays: tuple[dict, ...] = ()


def _replay(media: dict, commands: tuple[dict, ...]) -> ProjectView:
    duration = media["duration_ms"]
    current: list[dict] = []
    suggestion: list[dict] | None = None
    approved = False
    analysis_settings: dict | None = None
    detected_silences: int | None = None
    captions: list[dict] = []
    caption_style = "social"
    caption_config = default_caption_config()
    audio_clips: list[dict] = []
    audio_mix = default_audio_mix()
    video_fx: list[dict] = []
    video_transitions: list[dict] = []
    graphic_overlays: list[dict] = []
    used_events: set[str] = set()

    for command in commands:
        cmd = _object(command, {"id", "type", "payload"}, "command")
        eid = _id(cmd["id"], "command.id")
        if eid in used_events:
            raise ProjectFormatError("duplicate command id")
        used_events.add(eid)
        kind = cmd["type"]
        if not isinstance(kind, str) or kind not in _TYPES:
            raise ProjectFormatError(f"unknown command type: {kind}")
        payload = cmd["payload"]
        if kind == "analysis.propose":
            legacy_fields = {"segments", "engine", "policy", "noise_db"}
            new_fields = legacy_fields | {"settings", "detected_silences"}
            if not isinstance(payload, dict) or set(payload) not in (legacy_fields, new_fields):
                raise ProjectFormatError("analysis.propose: invalid or incomplete payload")
            if payload["engine"] != "ffmpeg.silencedetect" or payload["policy"] != "ai-natural":
                raise ProjectFormatError("unsupported analysis engine or policy")
            if type(payload["noise_db"]) is not int or not -90 <= payload["noise_db"] <= -5:
                raise ProjectFormatError("noise_db out of bounds")
            if set(payload) == new_fields:
                try:
                    analysis_settings = validate_cut_settings(payload["settings"])
                except ValueError as exc:
                    raise ProjectFormatError(str(exc)) from exc
                if analysis_settings["noise_db"] != payload["noise_db"]:
                    raise ProjectFormatError("analysis noise threshold does not match settings")
                count = payload["detected_silences"]
                if type(count) is not int or not 0 <= count <= 1_000_000:
                    raise ProjectFormatError("detected_silences must be a nonnegative integer")
                detected_silences = count
            else:
                # Legacy proposals omitted full policy parameters.
                settings = {"preset": "custom", **CUT_PRESETS["natural"]}
                settings["noise_db"] = payload["noise_db"]
                if payload["noise_db"] == CUT_PRESETS["natural"]["noise_db"]:
                    settings["preset"] = "natural"
                analysis_settings = settings
                detected_silences = None
            current = _segments(payload["segments"], duration)
            suggestion = copy.deepcopy(current)
            approved = False
        elif kind == "timeline.replace":
            _object(payload, {"segments"}, kind)
            current = _segments(payload["segments"], duration)
            approved = False
        elif kind == "segment.update":
            _object(payload, {"segment_id", "start_ms", "end_ms"}, kind)
            ident = _id(payload["segment_id"], "segment_id")
            start, end = _integer(payload["start_ms"], "start_ms"), _integer(payload["end_ms"], "end_ms")
            if not any(s["id"] == ident for s in current):
                raise ProjectFormatError("segment.update target does not exist")
            current = [
                {**s, "start_ms": start, "end_ms": end} if s["id"] == ident else s
                for s in current
            ]
            _segments(current, duration)
            approved = False
        elif kind == "segment.remove":
            _object(payload, {"segment_id"}, kind)
            ident = _id(payload["segment_id"], "segment_id")
            if not any(s["id"] == ident for s in current):
                raise ProjectFormatError("segment.remove target does not exist")
            current = [s for s in current if s["id"] != ident]
            _check_timeline(current, duration)
            approved = False
        elif kind == "segment.insert":
            _object(payload, {"segment"}, kind)
            row = _segments([payload["segment"]], duration)[0]
            current = sorted([*current, row], key=lambda s: s["start_ms"])
            _segments(current, duration)
            approved = False
        elif kind == "timeline.restore_suggestion":
            _object(payload, set(), kind)
            if suggestion is None:
                raise ProjectFormatError("no analysis suggestion to restore")
            current = copy.deepcopy(suggestion)
            approved = False
        elif kind == "timeline.keep_all":
            _object(payload, set(), kind)
            current = [{"id": eid, "start_ms": 0, "end_ms": duration}]
            approved = False
        elif kind == "timeline.approve":
            _object(payload, set(), kind)
            if not current:
                raise ProjectFormatError("cannot approve an empty timeline")
            approved = True
        elif kind == "caption.set":
            _object(payload, {"cues", "style"}, kind)
            if payload["style"] not in CAPTION_STYLES:
                raise ProjectFormatError("Stile sottotitoli non supportato.")
            captions = _captions(payload["cues"], duration)
            caption_style = payload["style"]
            caption_config = default_caption_config(caption_style)
            approved = False
        elif kind == "caption.correct":
            _object(payload, {"caption_id", "text"}, kind)
            ident = _id(payload["caption_id"], "caption_id")
            text = _caption_text(payload["text"])
            if not any(c["id"] == ident for c in captions):
                raise ProjectFormatError("Sottotitolo non trovato.")
            captions = [
                {**c, "text": text} if c["id"] == ident else c
                for c in captions
            ]
            approved = False
        elif kind == "caption.retime":
            _object(payload, {"caption_id", "start_ms", "end_ms"}, kind)
            ident = _id(payload["caption_id"], "caption_id")
            start = _integer(payload["start_ms"], "caption.start_ms")
            end = _integer(payload["end_ms"], "caption.end_ms")
            if not any(c["id"] == ident for c in captions):
                raise ProjectFormatError("Sottotitolo non trovato.")
            # Validate the COMPLETE proposed cue sequence, not just its target:
            # editing one cue must never create overlaps or leave source bounds.
            proposed = [
                {**cue, "start_ms": start, "end_ms": end} if cue["id"] == ident else cue
                for cue in captions
            ]
            captions = _captions(proposed, duration)
            approved = False
        elif kind == "caption.style":
            _object(payload, {"style"}, kind)
            if payload["style"] not in CAPTION_STYLES or not captions:
                raise ProjectFormatError("Stile sottotitoli non disponibile.")
            caption_style = payload["style"]
            caption_config = default_caption_config(caption_style)
            approved = False
        elif kind == "caption.configure":
            _object(payload, {"config"}, kind)
            if not captions:
                raise ProjectFormatError("Genera prima i sottotitoli.")
            try:
                caption_config = validate_caption_config(payload["config"])
            except ValueError as exc:
                raise ProjectFormatError(str(exc)) from exc
            caption_style = caption_config["preset"]
            approved = False
        elif kind == "caption.clear":
            _object(payload, set(), kind)
            if not captions:
                raise ProjectFormatError("Nessun sottotitolo da rimuovere.")
            captions = []
            approved = False
        elif kind == "audio.add":
            _object(payload, {"clip"}, kind)
            clip = _audio_clip(payload["clip"], duration)
            if len(audio_clips) >= 16 or any(item["id"] == clip["id"] for item in audio_clips):
                raise ProjectFormatError("Maximum 16 audio effects; clip ID must be unique")
            audio_clips.append(clip)
            approved = False
        elif kind == "audio.update":
            _object(payload, {"clip_id", "start_ms", "gain_db"}, kind)
            target = _id(payload["clip_id"], "audio clip.id")
            if not any(item["id"] == target for item in audio_clips):
                raise ProjectFormatError("audio effect not found")
            audio_clips = [
                _audio_clip({**item, "start_ms": payload["start_ms"],
                             "gain_db": payload["gain_db"]}, duration)
                if item["id"] == target else item for item in audio_clips
            ]
            approved = False
        elif kind == "audio.mixer.configure":
            audio_mix = validate_audio_mix(payload)
            approved = False
        elif kind == "audio.clip.mix":
            _object(payload, {"clip_id", "gain_db", "muted"}, kind)
            target = _id(payload["clip_id"], "audio clip.id")
            if not any(item["id"] == target for item in audio_clips):
                raise ProjectFormatError("audio effect not found")
            if type(payload["muted"]) is not bool:
                raise ProjectFormatError("audio clip.muted must be boolean")
            audio_clips = [
                _audio_clip({**item, "gain_db": payload["gain_db"],
                             "muted": payload["muted"]}, duration)
                if item["id"] == target else item for item in audio_clips
            ]
            approved = False
        elif kind == "video.transition.add":
            _object(payload, {"transition"}, kind)
            row=_video_transition(payload["transition"],current)
            video_transitions=[*video_transitions,row]
            _validate_video_transitions(video_transitions,current)
            approved=False
        elif kind == "video.transition.update":
            _object(payload, {"transition"}, kind)
            row=_video_transition(payload["transition"],current)
            if not any(t["id"]==row["id"] for t in video_transitions):
                raise ProjectFormatError("Video transition to update does not exist")
            video_transitions=[row if t["id"]==row["id"] else t
                               for t in video_transitions]
            _validate_video_transitions(video_transitions,current)
            approved=False
        elif kind == "video.transition.remove":
            _object(payload, {"transition_id"}, kind)
            identity=_id(payload["transition_id"],"transition_id")
            if not any(t["id"]==identity for t in video_transitions):
                raise ProjectFormatError("Transition to remove does not exist")
            video_transitions=[t for t in video_transitions if t["id"]!=identity]
            approved=False
        elif kind == "graphic.overlay.add":
            _object(payload, {"graphic"}, kind)
            try:
                item = validate_graphic(payload["graphic"], current, duration)
                validate_graphics([*graphic_overlays, item], current, duration)
            except ValueError as exc:
                raise ProjectFormatError(str(exc)) from exc
            graphic_overlays = [*graphic_overlays, item]
            approved = False
        elif kind == "graphic.overlay.update":
            _object(payload, {"graphic"}, kind)
            try:
                item = validate_graphic(payload["graphic"], current, duration)
            except ValueError as exc:
                raise ProjectFormatError(str(exc)) from exc
            if not any(g["id"] == item["id"] for g in graphic_overlays):
                raise ProjectFormatError("Grafica da modificare inesistente.")
            updated = [item if g["id"] == item["id"] else g for g in graphic_overlays]
            try:
                validate_graphics(updated, current, duration)
            except ValueError as exc:
                raise ProjectFormatError(str(exc)) from exc
            graphic_overlays = updated
            approved = False
        elif kind == "graphic.overlay.remove":
            _object(payload, {"graphic_id"}, kind)
            ident = _id(payload["graphic_id"], "graphic_id")
            if not any(g["id"] == ident for g in graphic_overlays):
                raise ProjectFormatError("Grafica da rimuovere inesistente.")
            graphic_overlays = [g for g in graphic_overlays if g["id"] != ident]
            approved = False
        elif kind == "video.transform.add":
            _object(payload, {"effect"}, kind)
            effect = _video_transform(payload["effect"], current, duration)
            video_fx = [*video_fx, effect]
            _validate_video_fx(video_fx, current, duration)
            approved = False
        elif kind == "video.transform.update":
            _object(payload, {"effect"}, kind)
            effect = _video_transform(payload["effect"], current, duration)
            if not any(row["id"] == effect["id"] for row in video_fx):
                raise ProjectFormatError("Video FX to update does not exist")
            video_fx = [effect if row["id"] == effect["id"] else row for row in video_fx]
            _validate_video_fx(video_fx, current, duration)
            approved = False
        elif kind == "video.transform.remove":
            _object(payload, {"effect_id"}, kind)
            ident = _id(payload["effect_id"], "video effect_id")
            if not any(row["id"] == ident for row in video_fx):
                raise ProjectFormatError("Video FX to remove does not exist")
            video_fx = [row for row in video_fx if row["id"] != ident]
            approved = False
        elif kind == "audio.remove":
            _object(payload, {"clip_id"}, kind)
            target = _id(payload["clip_id"], "audio clip.id")
            if not any(item["id"] == target for item in audio_clips):
                raise ProjectFormatError("audio effect not found")
            audio_clips = [item for item in audio_clips if item["id"] != target]
            approved = False

    _validate_video_fx(video_fx, current, duration)
    _validate_video_transitions(video_transitions,current)
    try:
        validate_graphics(graphic_overlays, current, duration)
    except ValueError as exc:
        raise ProjectFormatError(str(exc)) from exc
    return ProjectView(
        segments=tuple(copy.deepcopy(current)),
        suggested=tuple(copy.deepcopy(suggestion)) if suggestion is not None else None,
        approved=approved,
        analysis_settings=copy.deepcopy(analysis_settings),
        detected_silences=detected_silences,
        captions=tuple(copy.deepcopy(captions)),
        caption_style=caption_style,
        caption_config=copy.deepcopy(caption_config),
        audio_clips=tuple(copy.deepcopy(audio_clips)),
        audio_mix=copy.deepcopy(audio_mix),
        video_fx=tuple(copy.deepcopy(video_fx)),
        video_transitions=tuple(copy.deepcopy(video_transitions)),
        graphic_overlays=tuple(copy.deepcopy(graphic_overlays)),
    )


class ProjectTape:
    """Event history + active cursor; redo tail is preserved in exported v2 projects.

    Undo/redo are structured history operations. Moving the cursor never rewrites
    an existing event, while a new edit after undo forks and discards only the
    inactive redo tail. Revision is a monotonic concurrency token independent
    of command count and cursor.
    """

    def __init__(
        self,
        media: dict,
        commands: list[dict] | tuple[dict, ...] = (),
        *,
        history_cursor: int | None = None,
        revision: int | None = None,
    ) -> None:
        self.media = _validate_media(media)
        if not isinstance(commands, (list, tuple)) or len(commands) > MAX_COMMANDS:
            raise ProjectFormatError(f"commands must be an array of at most {MAX_COMMANDS}")
        self.commands = tuple(copy.deepcopy(list(commands)))
        cursor = len(self.commands) if history_cursor is None else history_cursor
        if type(cursor) is not int or not 0 <= cursor <= len(self.commands):
            raise ProjectFormatError("history_cursor must be inside the command history")
        rev = len(self.commands) if revision is None else revision
        if type(rev) is not int or not len(self.commands) <= rev <= MAX_REVISION:
            raise ProjectFormatError("revision must be monotonic and >= command count")
        # Validate the entire redo tail as well as the active prefix, even if
        # a damaged event is currently invisible on the timeline.
        _replay(self.media, self.commands)
        self.history_cursor = cursor
        self.revision = rev
        self.view = _replay(self.media, self.commands[:cursor])

    @property
    def can_undo(self) -> bool:
        return self.history_cursor > 0

    @property
    def can_redo(self) -> bool:
        return self.history_cursor < len(self.commands)

    @property
    def active_command(self) -> dict | None:
        if self.history_cursor == 0:
            return None
        return copy.deepcopy(self.commands[self.history_cursor - 1])

    def _move(self, target: int) -> ProjectTape:
        if self.revision >= MAX_REVISION:
            raise ProjectFormatError("project revision limit reached")
        return ProjectTape(
            self.media, self.commands,
            history_cursor=target, revision=self.revision + 1,
        )

    def undo(self) -> ProjectTape:
        if not self.can_undo:
            raise ProjectFormatError("non ci sono altre modifiche da annullare")
        return self._move(self.history_cursor - 1)

    def redo(self) -> ProjectTape:
        if not self.can_redo:
            raise ProjectFormatError("non ci sono altre modifiche da ripristinare")
        return self._move(self.history_cursor + 1)

    def append(self, kind: str, payload: dict, *, event_id: str | None = None) -> ProjectTape:
        if self.history_cursor >= MAX_COMMANDS or self.revision >= MAX_REVISION:
            raise ProjectFormatError("command history limit reached; create a new project")
        if not isinstance(kind, str) or kind not in _TYPES:
            raise ProjectFormatError(f"unsupported command type: {kind}")
        if not isinstance(payload, dict):
            raise ProjectFormatError("command payload must be an object")
        new_commands = (
            *self.commands[:self.history_cursor],
            {"id": event_id or uuid.uuid4().hex, "type": kind,
             "payload": copy.deepcopy(payload)},
        )
        return ProjectTape(
            self.media, new_commands,
            history_cursor=len(new_commands), revision=self.revision + 1,
        )

    def edit_plan(self, source: str) -> EditPlan | None:
        if not self.view.segments:
            return None
        return EditPlan(
            source=source,
            source_duration_ms=self.media["duration_ms"],
            has_audio=self.media["has_audio"],
            segments=tuple(Interval(s["start_ms"], s["end_ms"]) for s in self.view.segments),
        )

    def as_dict(self) -> dict:
        return {
            "format": FORMAT,
            "schema_version": VERSION,
            "media": copy.deepcopy(self.media),
            "commands": copy.deepcopy(list(self.commands)),
            "history_cursor": self.history_cursor,
            "revision": self.revision,
        }

    @classmethod
    def from_dict(cls, document: Any) -> ProjectTape:
        if not isinstance(document, dict) or document.get("format") != FORMAT:
            raise ProjectFormatError("unsupported project format")
        version = document.get("schema_version")
        if type(version) is not int:
            raise ProjectFormatError("project schema_version must be an integer")
        if version == LEGACY_VERSION:
            obj = _object(
                document, {"format", "schema_version", "media", "commands"}, "legacy project"
            )
            # V1 files are intentionally read-only inputs; exporting always
            # upgrades to V2 with cursor at the end and preserved event IDs.
            return cls(obj["media"], obj["commands"])
        if version in (MIGRATION_VERSION, V3_VERSION, PREVIOUS_VERSION, VERSION):
            obj = _object(
                document,
                {"format", "schema_version", "media", "commands",
                 "history_cursor", "revision"},
                "project",
            )
            return cls(
                obj["media"], obj["commands"],
                history_cursor=obj["history_cursor"], revision=obj["revision"],
            )
        raise ProjectFormatError("unsupported project format or schema version")

    def require_media(self, *, sha256: str, duration_ms: int, has_audio: bool) -> None:
        if (
            self.media["sha256"] != sha256
            or self.media["duration_ms"] != duration_ms
            or self.media["has_audio"] != has_audio
        ):
            raise ProjectFormatError(
                "Il progetto si riferisce a un altro video: importa il file originale corretto."
            )
