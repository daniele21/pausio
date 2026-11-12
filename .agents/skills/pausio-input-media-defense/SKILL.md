---
name: pausio-input-media-defense
description: Use for Pausio uploads, media import, ffmpeg/ffprobe, audio/music libraries, image/video overlays, SVG/fonts, archive/project bundle parsing, filesystem paths, retention and untrusted media security.
---

# Treat all imported media as adversarial bytes

Read this skill before implementing new video/audio import, user music library, image overlays, waveform extraction, FFmpeg adapters or zip bundles. Combine with `pausio-media-ffmpeg` for rendering correctness and `pausio-network-abuse-defense` for upload load.

## Safety procedure
1. Read upload endpoint and workspace/file handling. Enforce per-type byte caps **before** reading, stream in bounded chunks, check actual file MIME/codec using bounded tools (extension and Content-Type are hints only). Validate track count/duration/resolution/frame-rate/codec constraints and reject huge frame count/duration/memory.
2. Never trust a user-provided filename as a destination. Use random temporary files in private workspace, `O_EXCL` and safe parent paths, reject symlinks and path traversal; atomic commit only after probe, hash and validation. Clean failed staged files. Imported media source remains immutable.
3. Invoke FFmpeg/FFprobe with argument arrays, fixed allowlisted flags and time limits; no shell or agent-provided `-filter_complex` strings, protocols, remote URLs or dangerous concat options. FFmpeg must read only staged local files. Consider sandbox/process limits for hostile codecs/metadata. FFmpeg is a complex native attack surface: keep binaries updated.
4. For still images, animated images, fonts and SVG: cap pixels/frames/decompression ratio; reject scripts, external URLs, `foreignObject` and executable active content. Prefer rasterizing sanitized SVG in an isolated offline worker, or reject SVG until supported safely.
5. For archive/project bundle: reject absolute paths, parent traversal, symlinks/hard links, duplicate/case-colliding names, huge expanded size, excessive file count, ZIP bombs, nested archives and invalid/missing SHA-256. Don't extract untrusted bundles to source tree or shared tmp locations.
6. Media-library assets must retain content hashes, license/provenance and restricted rights; avoid automatic upload of locally indexed media to ChatGPT/Claude without explicit user action.
7. When adding media types, threat-model failed probe, crash, timeout, disk exhaustion and possible data leakage; provide error without private paths. Do not promise a safe decoder on the basis of a file extension.

## Acceptance
- Negative tests for media path traversal, symlink races, invalid codec, huge declared bytes, missing Content-Length, partial upload, repeated/concurrent imports, malformed project JSON and media hash mismatch.
- Tests for long media/huge dimensions once limits implemented; for SVG/zip only after those formats are actually supported.
- Inspect real output with ffprobe, audio listening and snapshot visual checks. No false claims that skills alone validate arbitrary binaries.

See [ingestion abuse cases](references/ingestion-checklist.md).
