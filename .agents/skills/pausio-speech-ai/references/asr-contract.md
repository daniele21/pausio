# ClosedRoom ASR contract (verified source code; live E2E pending)

Upstream owner: https://github.com/daniele21/closedroom/tree/dev
Important sources:
- [router](https://github.com/daniele21/closedroom/blob/dev/src/local_asr_server/routers/transcriptions.py)
- [request schema](https://github.com/daniele21/closedroom/blob/dev/src/local_asr_server/schemas.py)
- [provider boundary](https://github.com/daniele21/closedroom/blob/dev/src/local_asr_server/asr_provider.py)
- [ASR app service](https://github.com/daniele21/closedroom/blob/dev/src/local_asr_server/services/transcription_service.py)

Current service is typically on \`http://127.0.0.1:1236\` (see upstream \`runtime/models.py\`). Pausio POSTs JSON:

\`\`\`json
{
  "file": "/absolute/path/to/temporary/audio.wav",
  "language": "it",
  "task": "transcribe",
  "response_format": "verbose_json",
  "word_timestamps": true,
  "asr_provider": "local",
  "diarization_provider": "disabled",
  "vad_guided": true,
  "vad_post_filter": true
}
\`\`\`

Upstream response (simplified for documentation, **not** live-generated):

\`\`\`json
{
  "text": "Ciao dal modello",
  "language": "it",
  "asr_provider": "local",
  "backend": "mlx-whisper",
  "model": "mlx-community/whisper-large-v3-turbo",
  "segments": [{"start": 0.25, "end": 1.75, "text": "Ciao dal modello"}]
}
\`\`\`

Source and optional per-word \`start\`/\`end\` values are in seconds. Pausio's \`src/pausio/closedroom_asr.py\` converts available timestamps to integer milliseconds, records model/backend, and sets \`word_timestamps_available=false\` if no aligned words were actually returned.

**Do not equate a requested flag with available alignment.** Current responses may lack words depending on model or backend, and speaker metadata is not assumed. Original-source→audio-offset mapping and real model responses must be verified with real footage. Preserve transcript and source timeline even if edit rendering subsequently removes segments.

Future changes to this transport contract must be coordinated with ClosedRoom upstream. Reuse its VAD and caching logic; no standalone Whisper/Silero runtime in Pausio.
