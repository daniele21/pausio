# Speech adapter contract (proposed; not implemented)

Keep a stable provider-neutral result shape in a future module, e.g.:

`{
  "schema_version": 1,
  "source_duration_ms": 15000,
  "language": "it",
  "engine": {"name": "faster-whisper", "model": "example", "revision": "pinned"},
  "words": [
    {"start_ms": 1000, "end_ms": 1330, "text": "Oggi", "confidence": 0.91}
  ],
  "speech_intervals": [{"start_ms": 850, "end_ms": 2200}],
  "warnings": []
}`

This is **illustrative**, not the current API or a promise that confidences are calibrated. Source timestamps must be monotonic with stated overlap policy, and output must indicate where alignment is unavailable. Distinguish measured confidence from heuristic scores.

Candidate upstream implementations to investigate and pin before coding:
- https://github.com/SYSTRAN/faster-whisper
- https://github.com/m-bain/whisperX
- https://github.com/snakers4/silero-vad

Benchmarks: transcription errors on Italian speech, speech missed in quiet clips, drift from resampling, CPU memory and latency, reproducible model provenance. Download and cache policies must be explicit.
