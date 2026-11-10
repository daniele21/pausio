# Quality test matrix

| Layer | Cases | Assertion | Trigger |
| --- | --- | --- | --- |
| Pure core | invalid ms, overlap, source resolution, round trip | typed invariants and versioning | every PR |
| Planner | long/short silence, edge silence, tiny voice between gaps | protect meaningful speech | every PR |
| CLI | missing FFmpeg/source, bad plan, output collision, dry-run | actionable errors; no destructive writes | every PR |
| FFmpeg E2E | synthetic audio+video, no audio, multiple clips | playable MP4, dimensions, streams, basic duration | every PR |
| Real phone fixtures | A56 VFR, rotation, Bluetooth/mic, abrupt noise | cuts visually/aurally correct; drift checked | opt-in before release |
| ASR/VAD | Italian jargon, whispering, traffic, hallucination | WER, timing errors, misses | when ML adapter changes |
| Subtitles | timing after cuts, safe area, font fallback | automated mapping + human preview | when subtitle adapter changes |
| Privacy | offline default, no background uploads | no network use without opt-in | security review |

Record FFmpeg version, OS, Python version, fixture provenance/consent and model revision for reproducible bug reports.

The acceptance thresholds in `docs/ROADMAP.md` are targets to evaluate, **not** accomplished results. A CI pass cannot certify natural pacing or A/V fidelity on all user media.
