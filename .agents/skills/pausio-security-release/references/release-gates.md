# Privacy & release decision log template

Before every external release, record:
- Version, commit hash, Python/FFmpeg versions, macOS/Linux/Windows targets.
- Full first-party license decision, transitive dependency notices and any source obligations.
- FFmpeg binary provenance, configure flags and linked codec licenses if bundling.
- Local ASR/VAD model provenance, revision, cache behavior and allowed redistribution.
- Fonts, music, sound effects, screenshot/media source license and attribution.
- Input/output/temporary-media retention, permissions and cleanup behavior.
- No unexpected network traffic, API key exposure, telemetry or auto-download.
- Negative test: source never overwritten; partial export not published.
- E2E audio/video sync and subtitle safe-area human review.
- Rollback route and known limitations.

Keep release steps manual until a stable, signed distribution process is designed. PyPI publishing can later use trusted OIDC instead of storing long-lived publishing tokens:
https://docs.pypi.org/trusted-publishers/using-a-publisher/

Do not treat this document as legal advice. Verify actual applicable licenses prior to distribution.
