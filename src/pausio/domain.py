"""Stable, dependency-free edit decision model (all timestamps in milliseconds)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class Interval:
    start_ms: int
    end_ms: int

    def __post_init__(self) -> None:
        if not isinstance(self.start_ms, int) or isinstance(self.start_ms, bool):
            raise ValueError("start_ms must be an integer")
        if not isinstance(self.end_ms, int) or isinstance(self.end_ms, bool):
            raise ValueError("end_ms must be an integer")
        if self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise ValueError("an interval requires 0 <= start_ms < end_ms")

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    def as_dict(self) -> dict[str, int]:
        return {"start_ms": self.start_ms, "end_ms": self.end_ms}


@dataclass(frozen=True, slots=True)
class EditPlan:
    source: str
    source_duration_ms: int
    segments: tuple[Interval, ...]
    has_audio: bool
    preset: str = "ai-natural"
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"unsupported edit plan schema: {self.schema_version}")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("source must be a non-empty path")
        if not isinstance(self.source_duration_ms, int) or self.source_duration_ms <= 0:
            raise ValueError("source_duration_ms must be positive")
        if not isinstance(self.has_audio, bool):
            raise ValueError("has_audio must be a boolean")
        if self.preset != "ai-natural":
            raise ValueError("unknown preset; only ai-natural is supported")
        if not self.segments:
            raise ValueError("plan must retain at least one segment")
        previous_end = 0
        for seg in self.segments:
            if seg.start_ms < previous_end or seg.end_ms > self.source_duration_ms:
                raise ValueError("segments must be ordered, non-overlapping and within duration")
            previous_end = seg.end_ms

    @property
    def output_duration_ms(self) -> int:
        return sum(seg.duration_ms for seg in self.segments)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": self.source,
            "source_duration_ms": self.source_duration_ms,
            "has_audio": self.has_audio,
            "preset": self.preset,
            "segments": [seg.as_dict() for seg in self.segments],
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> EditPlan:
        if not isinstance(value, dict):
            raise ValueError("plan must be a JSON object")
        raw_segments = value.get("segments")
        if not isinstance(raw_segments, list):
            raise ValueError("segments must be a list")
        try:
            segments = tuple(Interval(**item) for item in raw_segments)
            return cls(
                source=value["source"],
                source_duration_ms=value["source_duration_ms"],
                has_audio=value["has_audio"],
                preset=value.get("preset", "ai-natural"),
                schema_version=value["schema_version"],
                segments=segments,
            )
        except (KeyError, TypeError) as exc:
            raise ValueError(f"invalid edit plan: {exc}") from exc

    def resolved_source(self, plan_file: Path) -> Path:
        """Resolve relative media paths from the plan's directory, not shell CWD."""
        source = Path(self.source).expanduser()
        return (source if source.is_absolute() else plan_file.parent / source).resolve()
