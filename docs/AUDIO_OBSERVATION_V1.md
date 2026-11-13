# Audio observation v1 — short actual WAV excerpts through Pausio MCP

**Status:** implemented in PR branch `daniele/mcp-audio-observation-v1`.
Ship only after CI + Playwright pass and PR merges. Audio in MCP still
requires a **real ChatGPT tunnel smoke test**: a local JSON-RPC test cannot
guarantee every chat client can play or interpret MCP audio blocks.

## What it provides

The new read-only tool `pausio_get_audio_context` returns a genuine audio
excerpt captured by FFmpeg from **source**, current **preview** or current
short **range preview** with the edited mix. This is for hearing whether
a voice, riser, music or cut works, not for adding audio (the existing
asset/typed mixer tools remain separate).

It returns the standardized MCP
`content:[{type:"text",...},{type:"audio",mimeType:"audio/wav",data:"..."}]`
and `structuredContent` with source/revision/clock and actual PCM RMS/peak
**dBFS**, rather than the full base64 payload. An RMS or peak sample check
is **not** an integrated LUFS, voice-intelligibility or "viral" score.

- Exactly **one sample per call**, from **500 to 6000 milliseconds**.
- FFmpeg decodes to **16 kHz mono PCM WAV**, <=192 KiB + header, no new media
  codec packages and no transcoding outside Pausio.
- Per Studio session: **four excerpts per minute**, at most one active
  extraction, a 30s subprocess timeout, source/preview revision checks and
  no arbitrary filename, URL, path, filter expression, external API or
  full MP4 download.
- The WAV audio sent to a connected chat client **can contain private speech,
  names or other sensitive audio**. Nothing is automatically uploaded.

## Independent consent in the local UI

Open **Studio → Video FX → Fotogrammi per ChatGPT · consenso** and check
**Condividi brevi audio con ChatGPT (questa sessione)**. This checkbox is
independent of **Condividi fotogrammi con ChatGPT**. Turning on images does
not grant audio access and vice versa.

Consent is held only in memory; the chat agent **cannot enable it**, because
Studio requires the actual browser's same-origin POST to
`/api/observation/audio-consent`. It resets when importing a new source,
clearing the session, or restarting Studio, and is never in the exported
portable project, transcript or recovery checkpoint.

## Correct usage from ChatGPT

1. Retrieve `pausio_get_project` (current `media_id`,
   `project_revision`, opt-in and preview status).
2. For edited audio, render `pausio_preview_range` first and check
   `pausio_get_job_status` until **completed**.
3. Request a small interval of **edited output**; `source` uses original
   timestamps, and `range` uses absolute edited timestamps, **not relative
   offsets into the small clip**.

Example (IDs/revision are placeholders, always fetch actual values):

```json
{
  "revision": 73,
  "media_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "scope": "range",
  "start_ms": 17500,
  "duration_ms": 3500
}
```

If a creator corrects a caption, changes a mix or edits a cut, the previous
preview is invalid and the agent must regenerate it before inspecting edited
audio. The output can be used to compare original/edited passages and
review music, FX, voice levels and timing. Quality is reviewed by the creator,
who retains approval and MP4 export control.

**Limitations:** no automatic loudness normalization, stereo analysis,
diarization, subjective speech intelligibility scoring, full soundtrack
upload, music generation, automatic stock search or agent-enabled audio
consent. Mono audio is for reviewing balance/words, not checking stereo
spatialization. Loudness data is PCM RMS/peak dBFS, not LUFS.

## Code and regression

- `audio_observation.py`: small FFmpeg/stdlib WAV boundary.
- `mcp_audio_observation.py`: validated args, RMS/peak dBFS and MCP audio.
- `local_mcp.py`: narrow loopback WAV adapter (never general HTTP access).
- `studio.py`: consent, 4/min quota, revision/preview/audio window gates and
  dedicated audio endpoint; no persistent or cloud service.
- `visual_observation_ui.js`: both independent opt-in toggles without
  another standalone editor widget.
- `tests/test_audio_observation.py`: negative cases, actual FFmpeg source
  and rendered audio, consent/revocation/rate limits, MCP wire.
- Browser Playwright: independently enable/disable audio and reset on import.

The next useful step after a successful real tunnel audio smoke test is
a small, editor-facing **audio preflight** that can flag clipping and
obviously overpowered music while showing reference LUFS. Do not equate
that with a finished professional mastering engine.
