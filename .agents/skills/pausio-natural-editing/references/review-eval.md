# AI Natural editing evaluation

## Internal evaluation set (locally stored; not committed)
Select consented 20–30 smartphone clips containing quiet speech, music/traffic, indoor/outdoor, pauses, false starts, whispering, multiple speakers, microphone clipping and abrupt noise changes.

Each clip should have review labels: valid cut regions, **do not cut** speech spans, natural pauses worth preserving, reviewer notes and a pass/fail rationale. Keep source identities out of logs and Git.

## Metrics
- **False-cut rate:** proposed removals intersecting human-labeled audible/meaningful speech.
- **Boundary loss:** milliseconds/phonemes clipped at start/end of kept segments.
- **Reviewer acceptance:** accepted / reviewed proposed edits.
- **Time saved:** human review minutes to deliver an acceptable export compared with manual CapCut.
- **Subjective naturalness:** blind A/B listener score for rhythm and ambience continuity.

Do not claim quality thresholds have been met until benchmarks are collected. `docs/ROADMAP.md` contains proposed gates; treat them as hypotheses.
