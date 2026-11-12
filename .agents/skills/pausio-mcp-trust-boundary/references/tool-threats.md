# MCP trust matrix

| Data / action | Trust | Allowed by default? | Enforcement |
| --- | --- | --- | --- |
| Tool registry/manifest | Pausio-controlled | Yes, local stdio | Static allowlist; no untrusted plugin code |
| Video/transcript/asset text | Untrusted user/third-party data | Only explicitly requested | Never instructions/role escalation; output escaping |
| Project snapshot | Private data | Local read only | Project isolation, filtered fields, response-size limit |
| Generated overlay SVG/HTML/text | Untrusted programmatic data | Validated typed asset only | Sanitize/convert offline; forbid scripts/foreignObject/external references |
| Edit command | Untrusted model output | Limited supported types | Revision, source hash, schema, limits, undo history |
| Runner job | Expensive and privileged | Not in initial MCP | Approved ID, quotas, least token scopes, explicit confirmation |
| Export MP4 | User-visible high impact | Not in initial MCP | Explicit review/approval, controlled destination |
| Arbitrary URL/Shell/FFmpeg expression | Dangerous | NEVER | Reject; no generic executor |

## Attack patterns / response
- **Prompt injection** hidden in a subtitle/overlay instructs an assistant to publish secrets -> typed tool cannot grant new authority; no publish/secret tool available; sensitive read separated.
- **Confused deputy** public gateway forwards a request using a different user's Studio privileges -> verify identity + audience + exact project grants at every hop, not only at login.
- **MCP token passthrough** to an upstream service -> forbidden; mint separate scoped credentials or broker privileged actions server-side.
- **DNS rebinding** in local desktop Studio -> enforce Host on read and write, loopback-only; no public tunnel of localhost HTTP.
- **Exfiltration via asset URL**: do not accept arbitrary `https://...` as a server-to-server fetch destination; explicit user download/import with type checks.
- **Tool loops causing cost exhaustion**: per-user/global quotas, async job limits, cooldown and previews bounded by duration/size.
- **Stale project output**: reject a write against outdated project revision/source hash and provide refresh/re-propose instruction, never reinterpret silently.

References: https://modelcontextprotocol.io/specification/ and https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices (verify relevant version), OWASP API Security Top 10. An MCP JSON-RPC stdio process does not itself create an Internet-accessible endpoint.
