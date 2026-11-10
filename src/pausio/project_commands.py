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

from pausio.domain import EditPlan, Interval

FORMAT = "pausio.project"
VERSION = 1
MAX_COMMANDS = 2000
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


@dataclass(frozen=True)
class ProjectView:
    segments: tuple[dict, ...] = ()
    suggested: tuple[dict, ...] | None = None
    approved: bool = False


def _replay(media: dict, commands: tuple[dict, ...]) -> ProjectView:
    duration = media["duration_ms"]
    current: list[dict] = []
    suggestion: list[dict] | None = None
    approved = False
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
            _object(payload, {"segments", "engine", "policy", "noise_db"}, kind)
            if payload["engine"] != "ffmpeg.silencedetect" or payload["policy"] != "ai-natural":
                raise ProjectFormatError("unsupported analysis engine or policy")
            if not isinstance(payload["noise_db"], int) or isinstance(payload["noise_db"], bool):
                raise ProjectFormatError("noise_db must be integer")
            if not -90 <= payload["noise_db"] <= -5:
                raise ProjectFormatError("noise_db out of bounds")
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
            row = _object(payload["segment"], {"id", "start_ms", "end_ms"}, "segment")
            current = sorted([*current, copy.deepcopy(row)], key=lambda s: s["start_ms"])
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

    return ProjectView(
        segments=tuple(copy.deepcopy(current)),
        suggested=tuple(copy.deepcopy(suggestion)) if suggestion is not None else None,
        approved=approved,
    )


class ProjectTape:
    """Validated immutable-by-convention project with event replay and media binding."""

    def __init__(self, media: dict, commands: list[dict] | tuple[dict, ...] = ()) -> None:
        self.media = _validate_media(media)
        if not isinstance(commands, (list, tuple)) or len(commands) > MAX_COMMANDS:
            raise ProjectFormatError(f"commands must be an array of at most {MAX_COMMANDS}")
        self.commands = tuple(copy.deepcopy(list(commands)))
        self.view = _replay(self.media, self.commands)

    @property
    def revision(self) -> int:
        return len(self.commands)

    def append(self, kind: str, payload: dict, *, event_id: str | None = None) -> ProjectTape:
        if len(self.commands) >= MAX_COMMANDS:
            raise ProjectFormatError("command history limit reached; create a new project")
        if kind not in _TYPES:
            raise ProjectFormatError(f"unsupported command type: {kind}")
        return ProjectTape(
            self.media,
            (*self.commands, {"id": event_id or uuid.uuid4().hex, "type": kind,
                              "payload": copy.deepcopy(payload)}),
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
        }

    @classmethod
    def from_dict(cls, document: Any) -> ProjectTape:
        obj = _object(document, {"format", "schema_version", "media", "commands"}, "project")
        if obj["format"] != FORMAT or type(obj["schema_version"]) is not int or obj["schema_version"] != VERSION:
            raise ProjectFormatError("unsupported project format or schema version")
        return cls(obj["media"], obj["commands"])

    def require_media(self, *, sha256: str, duration_ms: int, has_audio: bool) -> None:
        if (
            self.media["sha256"] != sha256
            or self.media["duration_ms"] != duration_ms
            or self.media["has_audio"] != has_audio
        ):
            raise ProjectFormatError(
                "Il progetto si riferisce a un altro video: importa il file originale corretto."
            )
