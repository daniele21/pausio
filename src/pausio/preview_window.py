"""Pure output-timeline window selection for the canonical FFmpeg render graph.

No alternate renderer, no source-time guessing and no optional dependencies.
Windowing runs *after* captions, camera motion, PIP, graphic overlays and mix.
"""
from __future__ import annotations


def validate_window(window: tuple[int, int] | None, total_ms: int) -> None:
    """Bound a preview to 250 ms–10 s inside the edited output timeline."""
    if window is None:
        return
    if (type(window) is not tuple or len(window) != 2
        or type(window[0]) is not int or type(window[1]) is not int
        or window[0] < 0 or not 250 <= window[1] <= 10_000
        or window[0] + window[1] > total_ms):
        raise ValueError("Intervallo output non valido: scegli 0,25–10 secondi.")


def append_window_filters(
    filters: list[str], window: tuple[int, int] | None, *,
    audio_label: str | None,
) -> tuple[str, str | None]:
    """Append a deterministic bounded trim to the final composed A/V outputs.

    Input is already validated by validate_window(); labels are internal
    constants, never untrusted project data.
    """
    if window is None:
        return "[outv]", audio_label
    start, duration = window
    first, last = start / 1000, (start + duration) / 1000
    filters.append(
        f"[outv]trim=start={first:.3f}:end={last:.3f},"
        "setpts=PTS-STARTPTS[rangev]"
    )
    if audio_label is not None:
        filters.append(
            f"{audio_label}atrim=start={first:.3f}:end={last:.3f},"
            "asetpts=PTS-STARTPTS[rangea]"
        )
    return "[rangev]", "[rangea]" if audio_label else None
