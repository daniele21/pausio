# Pausio security threat model and adoption gates

**Status:** 2026-11-12, security-hardening phase. This is a living threat model, not penetration-test certification. The four dedicated skill files are version-controlled in `.agents/skills`. See `SECURITY.md`, `AGENTS.md`, `docs/AGENTIC_EDITING_PLAN.md` and CI tests.

## What is exposed today?

| Surface | Exposure | Current assets and trust | Security posture |
| --- | --- | --- | --- |
| GitHub Pages Capture | Public GitHub-managed HTTPS/static hosting | Browser camera/mic permission and local browser Blob; no video backend on Pages | No Pausio Python process behind Pages; GitHub platform handles edge availability. Never add static secrets. |
| Pausio Studio | `127.0.0.1:<port>` on user's Mac | Private video, ASR transcript, project autosave, FFmpeg jobs, imported music | Loopback only; same-origin POST guard; bounded uploads; Host validation, connection cap and socket idle timeout added by hardening PR. Local programs can still access localhost. |
| Local MCP stdio | Local child process connected to Studio | Read state/transcript and limited edits/render preview | Tool allowlist; no shell; not a public service; not itself account identity isolation. |
| GitHub Actions CI / Pages | Public repo hosted ephemeral runners | Tests/build and public static publishing | No personal media/runner secrets, branch/PR scoped jobs. |
| Planned self-hosted ASR | Not available yet | Private Mac with cached ASR model and user media | MUST use separate PRIVATE dispatch repo with restricted runner, allowlisted workflow and explicit consent. |
| Planned remote MCP | **Not implemented** | Would bridge a remote chat account to local editor/media | HARD BLOCK until independent authenticated HTTPS gateway, scoped authorization, quotas, WAF/edge protection, strong data minimization, security review. |

## Adversaries and threats
1. **Malicious website + DNS rebinding**: tricks browser into same-origin calls to a local service after a domain resolves to 127.0.0.1. Defense: strict Host on all verbs, true loopback bind, same-origin mutations; no public reverse proxy.
2. **Local hostile process / overeager agent**: can send many valid requests on localhost, start render/transcription, consume CPU/memory/disk. Defense: per-request and per-connection limits, job serialization, timeout and explicit action scope. Local user/OS still form trust boundary.
3. **Distributed public traffic**: a future Internet-facing MCP gateway can be saturated from many IPs. Local Python thread cap alone does not stop DDoS; must have edge/WAF/bandwidth/connection mitigation, global rate and per-identity/tenant quotas, bounded queues, circuit breakers and operational monitoring.
4. **Stolen MCP token / confused deputy**: attacker crosses project/user scope or uses a connector with excessive permissions. Defense: OAuth audience-bound tokens, strict allowlisted resources/operations, revocation, identity/project checks *on every operation*.
5. **Prompt injection inside video/subtitles/asset metadata**: instructs AI chat to exfiltrate, publish or override permissions. Treat media text as data; Pausio enforces server-side command and privilege limits.
6. **Malformed native media + asset bombs**: FFmpeg crashes/consumes resources, SVG script/remote references, zip-bomb, filename traversal. Defense: intake caps, private scratch, format/codec probing, no arbitrary URL/filter and ingestion budget.
7. **Public-repo PR attacks against self-hosted runner**: PR author can execute untrusted code on a persistent private Mac if runner attached to public repo. Keep dedicated private workflow repo, isolated runner and hard limits.
8. **Supply chain and release**: compromised actions/packages or unsafe artifact publication. Restrict token permissions, review/pin Actions revisions, immutable release refs, scanner/test gates and protected branches.

## Engineering baseline vs not implemented

**Already present before the security-hardening PR:** loopback bind, privacy headers/CSP/no CORS, POST Origin & client header, JSON size 4 MiB / audio 60 MiB / video 2 GiB, single active job per workspace, SHA256 source fingerprint, portable typed edit commands, 0600/0700 private persistence, local MCP allowlist, existing CI and Playwright.

**This PR:** explicit Host allowlist for every HTTP method, bounded local worker concurrency/backlog, idle socket read timeout, negative regression tests; four security domain skills with references, mandatory AGENTS routing and validator/CI coverage.

**NOT implemented:** hosted HTTPS/OAuth MCP gateway, global/per-client quotas, DDoS WAF, direct ChatGPT web access, runner dispatch, media sandbox isolation, antivirus scanning, full app security audit. Do not claim these exist.

## Change and release gates
- Design: inventory data, actor, external endpoint, auth, file movement, expensive action, resource budget and abuse scenarios *before* implementing a new tool.
- Build: use matching `.agents/skills/*/SKILL.md`; update tests and read-only/tool-level permission model; keep standard Python library where practical and no cloud model keys.
- Verify: `python scripts/validate_skills.py`, `python -m unittest discover -s tests -v`, `python -m compileall -q src scripts`, Playwright when web/UI changes, actual FFmpeg and hardware checks as relevant.
- Public deployment: block until authenticated gateway, edge rate limiting/DDoS protection, per-identity & global budgets, secure observability, incident response, failure tests and user consent for private data transfer.
- Runner: block until separate private repo, scoped credentials, hardened persistent Mac, limits and real end-to-end verification.

## Incident response runbook
1. Determine which surface is involved (Pages vs local Studio vs future remote gateway); avoid conflating unrelated failures.
2. If remote surface exists, disable ingress, disconnect tunnel, revoke credentials and pause dispatch. For local Studio stop it and disconnect untrusted local clients.
3. Preserve *minimal non-content* evidence: timestamps, request counts, status, resource saturation, command type, token identifier hash, relevant git SHA, **never raw video/transcript/token**.
4. Review logs, resource pressure, affected data and potential leak; patch, retest, rotate credentials, re-enable only after verified controls.
5. Document lessons in a private incident record; do not publicize credentials or exploit details.

## References (inspiration, no code copied)
- OWASP API4 Unrestricted Resource Consumption: https://api-security.owasp.org/editions/2023/en/0xa4-unrestricted-resource-consumption/
- MCP Security Best Practices: https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices
- GitHub Actions Secure Use, self-hosted runner warnings: https://docs.github.com/en/actions/reference/security/secure-use
