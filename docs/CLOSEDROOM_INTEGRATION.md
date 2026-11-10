# ClosedRoom ↔ Pausio transcription integration

## Architecture decision

**ClosedRoom owns ASR. Pausio owns editing.** Reuse [ClosedRoom](https://github.com/daniele21/closedroom) from the existing \`dev\` branch; Pausio does not install, fork or reimplement Whisper/Nemotron/Silero or model caching.

- ClosedRoom: MLX Whisper and Nemotron backends, VAD, model selection and local cache, transcription persistence, service API.
- Pausio: FFmpeg audio extraction from original video, localhost JSON request, response contract validation, source-time millisecond normalization, reviewable sidecar.
- Pausio editing core: independent deterministic \`EditPlan\`, \`planner.py\`, rendering; no automatic transcript-driven cuts today.

## Confirmed upstream API (source inspection)

The \`dev\` router \`src/local_asr_server/routers/transcriptions.py\` implements \`POST /v1/audio/transcriptions/path\`, accepting \`TranscribePathRequest\` in \`schemas.py\`. With \`response_format=verbose_json\`, it returns \`text\`, \`language\`, \`segments\`, \`metadata\`, \`model\`, \`backend\`, \`asr_provider\`, \`stats\` and persistence fields. Pausio forces \`asr_provider=local\` to avoid using ClosedRoom's optional Speechmatics provider.

The local API uses the same filesystem as Pausio. Pausio extracts a temporary 16 kHz mono WAV from video and provides its absolute path. This requires a server running **on the same machine**, not a remote service. Pausio does not try to start ClosedRoom or to download weights.

## How to run

1. Set up and launch the existing ClosedRoom local service according to [its README](https://github.com/daniele21/closedroom/blob/dev/README.md) (usual API host/port: \`127.0.0.1:1236\`). Check it already has the needed model cached/configured.
2. From Pausio (\`pip install -e .\`, FFmpeg installed):

\`\`\`bash
pausio inspect video.mp4
pausio transcribe video.mp4 -o outputs/video.transcript.json
# Optional flags: --language it --model mlx-community/whisper-large-v3-turbo
# --closedroom-url http://127.0.0.1:1236
\`\`\`

3. Review \`outputs/video.transcript.json\`. It contains original-source millisecond segment intervals, optional word intervals, raw text, model/backend provenance and \`word_timestamps_available\`. It **does not** yet modify \`plan.json\` or generate subtitles.

## Contract and safety

- Loopback-only HTTP (IPv4/IPv6), no nonlocal domain, HTTP proxy, redirects, API keys or implicit cloud ASR. Fail explicitly if server is unavailable.
- Request \`response_format=verbose_json\` and \`word_timestamps=true\`, while reporting missing word alignment honestly.
- Use explicit output location, protect against accidental overwrite; source video untouched.
- Temporary WAV is removed on success or exception, with no audio committed to Git.
- Dependency remains outside Pausio's Python install. ClosedRoom remains the sole location for ASR bug fixes, model patches and performance benchmarks.
- ClosedRoom's own model management may download missing weights: to maintain fully offline operation, preinstall/cache them first and confirm upstream server settings. Pausio does not control these side effects.
- Upstream \`dev\` is changing; pin a compatibility-verified ClosedRoom release/commit and introduce contract tests before a user-facing packaged release.

## Pending integration validation

- Live request against a running ClosedRoom \`dev\` instance with actual Whisper/Nemotron output.
- Match source-video timebase with extracted WAV time base, including nonzero initial track PTS and A56 VFR footage.
- Confirm word timestamp support on selected local model and protect alignment around edits.
- Investigate existing VAD evidence as a reusable ClosedRoom API: do not implement second Silero inference.
- Integrate transcript evidence into the human-reviewed AI Natural edit plan after contract stability.
- Add progress/cancellation integration without replicating ClosedRoom's internal job state.

Sources inspected:
- https://github.com/daniele21/closedroom/blob/dev/src/local_asr_server/routers/transcriptions.py
- https://github.com/daniele21/closedroom/blob/dev/src/local_asr_server/asr_provider.py
- https://github.com/daniele21/closedroom/blob/dev/src/local_asr_server/schemas.py
- https://github.com/daniele21/closedroom/blob/dev/src/local_asr_server/services/transcription_service.py
