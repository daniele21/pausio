# Subtitle timing and visual review

Source-to-output time mapping for a word wholly inside a kept interval `[s,e)`:

`output_start = cumulative_duration_of_earlier_kept_intervals + (word_start - s)`

If a word overlaps a removed interval, **do not assume** its whole duration survives. Flag it for manual correction; cutting inside a word is a serious editorial failure.

Initial test cases:
- Source word 10.1–10.5 s retained after a 2.0 s removed segment -> new word 8.1–8.5 s.
- Word crosses cut boundary -> flagged for review.
- Segment starts after an initial removal -> output starts at 0.
- Caption extends past final output -> rejected or truncated with explicit rule.
- Mixed language: "WhisperX", "FFmpeg", "Claude Code", "LLM", "API", "on-device".
- At least one real vertical export reviewed at phone size with subtitles and common platform overlays.

Use `SRT` for portable plain captions and `ASS` only when its advanced styling is required. No subtitle generation exists in Pausio v0.1 yet.
