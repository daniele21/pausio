# Security and privacy

Pausio performs local processing. The initial implementation has **no upload endpoint, telemetry, API keys or remote model calls**. FFmpeg commands are executed as argument arrays, not through a shell.

- Input videos and outputs may contain sensitive personal information; store them locally.
- Do not commit recorded videos, audio, full transcripts, secrets or model weights.
- Do not use untrusted edit plans without checking source paths and expected destination.
- All edit plans must be reviewed; signal-based silence detection can be wrong.
- Report security issues privately to the repository owner rather than posting sensitive examples publicly.
- Before distributing apps, review licensing and supply chain of packaged FFmpeg builds and other components.
