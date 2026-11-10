---
name: pausio-security-release
description: Use for Pausio privacy, local-first behavior, secrets, subprocess/file safety, dependency licenses, model weights, sound/font asset provenance, supply-chain CI, packaging and release-readiness decisions.
---

# Local-first security, supply chain and releases

## Procedure
1. Check `SECURITY.md`, `docs/DEPENDENCIES.md`, current `pyproject.toml` and release/CI config before adding dependencies or platform binaries.
2. Confirm raw video, transcripts and local artifacts do not leave machine by default; no telemetry, cloud APIs or weight downloads without explicit informed consent and settings.
3. Validate untrusted JSON and media path assumptions. Use FFmpeg as a subprocess argument list, never a shell. Protect against overwriting input, directory traversal in a future workspace, symlink races, stale project writes and unexpected output collisions.
4. New model/backend: document exact source, pinned revision, runtime version, weight cache, memory constraints and model license. New assets: provenance, license and attribution obligations.
5. Before bundling FFmpeg, audit **the actual binary build** and transitive codec licenses, not just FFmpeg source license. Do not import GPL/AGPL third-party code by accident.
6. Use scoped GitHub Actions permissions, review action versions and untrusted PR contexts; never expose secrets in logs. Do not publish from arbitrary PR workflows.
7. Block external release until Pausio's **own license** is selected intentionally. This repository currently contains no `LICENSE` and public visibility alone grants no right to reuse it.

## Release gate
- Tests and skill validation pass; documentation matches implemented behavior.
- Human media-quality sign-off on multiple real clips.
- Privacy/permissions/asset-license checklist reviewed.
- Version/changelog and artifact hashes available for distribution.
- No distribution/publication claimed until release pipeline actually exists.

See [release gates](references/release-gates.md).
