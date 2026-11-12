---
name: pausio-mcp-trust-boundary
description: Use for Pausio MCP tools, ChatGPT/Claude Chat connectors, remote authentication, scopes, agent permission prompts, instruction bundles, generated assets, prompt injection, token handling and tool-result data safety.
---

# Agent tool security — ChatGPT / Claude Chat are untrusted clients

## When to use
Before any tool added to `local_mcp.py`, any future hosted MCP, ChatGPT/Claude Chat connector, remote asset transfer or tool that can mutate a project, start expensive work, read media, dispatch a runner or export. Combine with `pausio-network-abuse-defense` for availability and `pausio-edit-command-schema` for replay consistency.

## Required contract
1. **Pausio never invokes GPT/Claude inference APIs.** The user's chat session is the creative agent. Chat content, transcripts, generated SVG/code, tool arguments, "system" instructions embedded in a video, and external media metadata are all untrusted *data*.
2. Inventory capabilities by risk: read project metadata; read sensitive transcript; request frames/audio; mutate timeline/overlay/audio; import asset; launch ASR/render; approve/export; external publish. Grant only capabilities the user intentionally enabled; human approval for high-impact operations.
3. A tool's `readOnlyHint` / `destructiveHint` annotation is **advisory**, not enforcement. The handler must validate exact parameters, IDs, bounds, source SHA-256, project revision, ownership/scope, operation allowlist and per-user quotas.
4. Treat `X-Pausio-Client: studio` as a local-CSRF guard, **never as authentication**. Remote MCP must use a separate authenticated gateway with audience-bound OAuth-style token validation, project/operation scopes, expiration/revocation and secure session correlation. No bearer tokens in exported projects or log text.
5. Never implement a generic `execute_shell`, `run_ffmpeg_filter`, `fetch_url`, unrestricted file read, arbitrary Python, arbitrary GitHub workflow dispatch, or `http_request` tool. Use narrow typed actions and exact allowlisted inputs.
6. Prevent prompt injection: text inside frames/transcripts/code/music tags may mention "ignore previous instructions"; the assistant may see it, but Pausio must **not** treat it as authority. Validate even "trusted" tool results; escaping/safe rendering for text/SVG; pin/canonicalize generated asset bytes, not freeform references.
7. Tool output must not include private absolute paths, credential values, raw media or transcript content unless the user explicitly invoked the scoped read. Never return a full project snapshot if its fields contain unexpected secrets; prefer allowlisted projections.
8. All mutating operations go through the **same project reducer** as the UI, with dry-run, atomic apply, optimistic revision, idempotency and undo/redo. No silent approval, auto publish, or permanent permissions from the agent alone.

## Verification
- Negative tests: unknown tool, unknown argument, malicious payload, stale revision, wrong media fingerprint, forged token/scope (future gateway), cross-project ID, URL/path traversal, and prompt injection strings.
- Test no network or model-API call for ordinary editing. Test explicit privacy consent for sending frames/transcripts to remote chat.
- Real ChatGPT/Claude Chat integration must be smoke-tested on the user's account/client: do not claim support merely because a local MCP stdio handshake passes.
- Failed tools return bounded, non-sensitive errors; no stack trace, host credentials, private file path or proxy headers.

Read [MCP authorization, trust and prompt-injection cases](references/tool-threats.md).
