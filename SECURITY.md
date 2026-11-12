# Security and privacy

Pausio is local-first. The CLI has no telemetry, API keys or default remote model calls. The browser-based **Pausio Studio** has a local import endpoint for the browser, bound only to `127.0.0.1`; this is **not** a cloud upload service. Mutating HTTP calls require the Studio header and reject unrecognized Origin values. Do not expose it through reverse proxies or a public interface.

## Local data retention

- Studio now auto-saves one active project **and a private copy of the original imported video** for restart/crash recovery. Closing Studio does **not** delete this copy. The UI must clearly show that persistence is enabled and offer **Elimina dati locali**.
- Default directories: macOS `~/Library/Application Support/Pausio/Studio`; Linux `~/.local/share/pausio/studio` or XDG_DATA_HOME. `pausio studio --data-dir <path>` changes this location.
- Persistent media is kept in the user's private workspace, file permissions 0600 and folder permissions 0700 on POSIX. Project checkpoints are written atomically and one previous checkpoint is retained for rollback. Do not write private media to source control or app logs.
- A per-workspace OS file lock prevents two Studio instances from modifying the same active autosave concurrently.
- Session recovery verifies media SHA-256 and edit-plan schema/command history before loading. On failure, leave files intact and expose an actionable recovery error.
- The portable `.pausio.json` project **never embeds video or transcript**; importing it requires the identical source media hash. ClosedRoom transcripts currently live only in the process memory in Studio and are not recovered after restart.
- The user's explicit **Elimina dati locali** action removes cached media and checkpoints. Avoid silent automatic deletion of damaged backups; warn instead.

## Secure engineering

- Do not commit recorded videos/audio, complete transcripts, secrets or model weights.
- Use FFmpeg argument arrays, never shell strings, and protect source paths against overwriting.
- Validate all typed editing commands, revisions, timeline bounds, imported project versions and source fingerprints on the server. Never execute JSON project instructions as code.
- Review proposed edit plans manually: silence detection may clip quiet speech. Output must be explicitly approved.
- Report security issues privately to the repository owner, not via public sensitive reproductions.
- Before distributing applications, review FFmpeg codec licenses, model/weight licenses and bundled dependencies.

## API/network security posture (2026-11-12)

**Current local transports:** Studio HTTP uses only `127.0.0.1`. The new `pausio mcp` command is a local stdio process that talks to Studio over loopback; it is **not** an authenticated Internet endpoint. The Capture page on GitHub Pages is static and contains no server-side Pausio editor. Never expose the local HTTP API by port forwarding or opening a public tunnel.

The local server has bounded JSON/media sizes, privacy headers, post-origin checks and one active editor workspace; the changes in the security-hardening PR add strict Host checks, socket timeouts and active connection limits. These reduce local abuse and DNS rebinding exposure; they **do not** make Pausio DDoS-proof.

**Future MCP gateway is a separate security gate:** require OAuth identity + audience/scope/project authorization, HTTPS, API quotas and global rate limiting, bounded jobs/uploads and edge DDoS/WAF protections. Until implemented, remote ChatGPT browser MCP is **not available**. See `docs/SECURITY_THREAT_MODEL.md` and `.agents/skills/pausio-network-abuse-defense/SKILL.md`.

**Self-hosted ASR runner:** keep runner workloads in a separately controlled private repo rather than on the public Pausio repository, per `.agents/skills/pausio-actions-runner-security/SKILL.md`. Runner dispatch, network transfer, consent and time budgets are not yet implemented; no agent can currently trigger that workflow through Pausio.

If abuse occurs: disable remote ingress/connector, revoke tokens, stop active jobs, preserve minimal metadata-only evidence, inspect logs/costs, patch and rotate before restoring service. A public Pages site is subject to the hosting platform's own abuse controls.
