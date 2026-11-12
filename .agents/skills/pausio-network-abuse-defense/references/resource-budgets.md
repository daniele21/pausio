# Resource-budgets and threat tests

**Current baseline (verify actual code before claiming):** Studio is local-loopback only. Existing upload maxima are 2 GiB for video, 60 MiB audio and 4 MiB JSON; current jobs are serialized per workspace. GitHub Pages is static. Local mitigations defend accidental/hostile local clients, **not Internet DDoS**.

| Surface | Proposed enforceable budget / gate | Negative test |
| --- | --- | --- |
| Studio transport | <=24 active client sockets; <=32 pending; 15s idle read/write timeout, close on disconnect | Slow/incomplete request and saturated connection attempts |
| Studio request | strict localhost Host on every HTTP verb; POST same-origin + client header; bounded Content-Length | DNS rebinding Host, missing Origin requirements, forged Host |
| Project JSON | <=4 MiB, strict schema, no arbitrary executable fields | Oversized body, unknown field, stale revision |
| Media upload | current source cap 2 GiB (review disk free space); bounded streamed chunks; private 0600/0700 paths | Huge declared length, truncated body, symlink/path escape |
| Async jobs | max 1 render/transcribe per workspace, bound runtime and output retention | Concurrent job requests, crash, cancellation, retry storm |
| Local MCP | <=1 MiB per incoming JSON-RPC line; <=8 MiB Studio response; bounded tool calls | Oversize tool input, unexpected params, repeated reads |
| Future public MCP | HTTPS + OAuth/audience-bound identity + scope/project auth, per-identity and global rate limits, strict timeouts and quotas; WAF/edge | Unauthed 401; overquota 429; global shedding 503; malicious client cannot fetch others' assets |
| Runner | private preapproved workflow IDs and job/token quota | Agent-provided script/URL/path disallowed |
| GitHub Pages | GitHub-managed static hosting, no server-side processing | No leaked source video/assets; no embedded secrets |

**Numbers are initial local-safe engineering defaults**, not capacity test outcomes. Tune with real video imports and browser recordings. If media processing cannot be rate bounded at an HTTP ingress, do not expose it remotely. Distinguish local denial of service from large distributed attacks: only edge/network-provider controls can address the latter.

**Minimum adversarial fixture set:** wrong Host with valid path; Host swapped to attacker domain; cross-origin POST; incomplete header; TCP idle; >socket cap; overlimit JSON; short body; malformed Range; invalid media; concurrent preview request; repeated MCP tool calls; fallback redirect; no stack trace containing media paths. Tests must run in CI and confirm media source/project unmodified.
