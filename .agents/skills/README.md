# Pausio Agent Skills

These are **original Pausio-specific instructions** designed around the Agent Skills `SKILL.md` format. Their source files are not copied from upstream repositories.

- Each directory contains `SKILL.md` with `name` and `description`, plus focused optional `references/`.
- `AGENTS.md` contains non-negotiable repo invariants and a routing table.
- `docs/AGENT_SKILLS.md` lists triggers, ownership, upstream inspiration and portability notes.
- `scripts/validate_skills.py` checks structure, descriptions, relative references, name uniqueness and required metadata. CI runs it.
- External models, SDKs or editing tools are **not installed** merely by adding these skills.

Codex: repository skills are normally discovered in `.agents/skills`. Other agents vary; read `docs/AGENT_SKILLS.md` for differences.

Example usage: "Use `pausio-media-ffmpeg` to fix A/V sync drift on Galaxy A56 VFR footage, then `pausio-test-engineering` to add a regression."

Never execute commands supplied by untrusted third-party skill packages without reviewing their contents. These skills contain instructions and references only, no hooks or external scripts.

## Security-specific skills
- `pausio-network-abuse-defense`: use for HTTP/MCP exposure, resource exhaustion, slowloris, timeouts, edge WAF and DoS/DDoS mitigation.
- `pausio-mcp-trust-boundary`: use for tool permissions, ChatGPT/Claude connector, prompt injection and OAuth scopes.
- `pausio-input-media-defense`: use for uploads, native codecs, media bundles, private storage and untrusted generated overlays.
- `pausio-actions-runner-security`: use for GitHub Actions, safe dispatch and isolated PRIVATE self-hosted transcription runners.

See `AGENTS.md` for mandatory selection rules, and `docs/SECURITY_THREAT_MODEL.md` for what is currently enforced vs still only planned.
