---
name: pausio-network-abuse-defense
description: Use whenever changing Pausio Studio HTTP, MCP transport, tunnels, remote gateways, public endpoints, uploads, polling, rendering jobs, rate limiting, timeouts or DoS/DDoS exposure. Require resource budgets, safe local bind, and adversarial tests.
---

# Network boundary, denial-of-service and abuse defense

## Trigger and operating model
Load this skill **before** modifying `src/pausio/studio.py`, `src/pausio/local_mcp.py`, connection setup, HTTP/API middleware, preview jobs, or any tunnel/public endpoint. Combine with `pausio-mcp-trust-boundary` for tools, `pausio-input-media-defense` for media ingestion and `pausio-security-release` for release gates.

**Different surfaces have different threats:** `github.io/pausio/` is a *static page* hosted by GitHub Pages, not a Pausio Python backend. Studio and stdio MCP bind to `127.0.0.1` locally. A **future remote MCP gateway** would be an Internet-facing service and **must be designed independently**, not by simply tunnelling Studio's local HTTP port.

## Mandatory review steps
1. Draw client -> DNS/CDN/WAF -> gateway -> authenticated capability -> local broker -> Studio/FFmpeg; list each trust boundary and network direction. Default to **no inbound Internet listener** on the Mac.
2. Establish per-operation resource budgets: connection concurrency, header/body bytes, socket idle/read deadlines, batch size, output size, job count, FFmpeg wall time, memory/disk usage, previews per minute and artifact retention. Prevent slowloris, slow uploads, upload bombs and repeated expensive job launches.
3. For *local Studio*: reject unrecognized `Host` on **GET, HEAD and POST** (DNS-rebinding protection), bind loopback, require same-origin for mutations, maintain CSP/no CORS and bound concurrent sockets. A static `X-Pausio-Client` header is **not authentication**; never reuse it as a remote bearer credential.
4. For *remote MCP*: require HTTPS + edge reverse-proxy/WAF or equivalent, tested authentication and project-scoped authorization; authenticate **before** hitting expensive work; place rate/connection limits at the edge and origin; protect token-based limits against per-IP evasion, and global limits against distributed floods. Use bounded queues; shed load with 429/503 and `Retry-After`, avoid unbounded workers.
5. Never proxy a raw source video, transcript, private paths or render bytes without explicit user consent and time-limited, least-privilege scope. Avoid reflected Origin / permissive CORS / public localhost proxy / arbitrary URL fetch / shell.
6. Separate CPU-intensive jobs from HTTP request threads; impose quotas, cancellation and idempotency; prefer one active render/ASR per workspace with explicit saturation behavior. Lock down any self-hosted runner dispatch separately.
7. Threat-model a malicious website, DNS rebinding, compromised MCP client, high-rate unauthenticated traffic, authenticated abusive agent loops, large media and slow TCP connections. Use `references/resource-budgets.md`.

## Acceptance / proof
- Tests for Host and Origin rejection, loopback-only bind, bounded workers/idle timeout and request body limits.
- Test throttling/repeated render requests and auth before dispatch **when implemented**. Do not claim edge DDoS mitigation exists in a local Python server.
- No PII, tokens, transcript or private file paths in logs. Record only safe counters, latency, total requests, rejected requests and bounded failure codes for operations.
- For public release, include edge DDoS protections, firewall/egress restrictions, incident response and traffic-monitoring plan.
- Verify the exact deployment surface: GitHub Pages CDN vs local Studio vs future gateway. A green GitHub Pages action does **not** mean a public Pausio API exists.

Read [resource budgets & abuse test matrix](references/resource-budgets.md). Also use OWASP API4 unrestricted resource consumption and current MCP security recommendations as conceptual sources, not pasted code.
