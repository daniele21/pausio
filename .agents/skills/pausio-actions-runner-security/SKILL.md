---
name: pausio-actions-runner-security
description: Use for Pausio GitHub Actions workflows, permissions, runner installation, self-hosted transcription, workflow_dispatch, upload/download artifacts, release CI, secrets, supply-chain provenance and scheduled automation.
---

# Safe GitHub Actions and self-hosted transcription

## Scope
Pausio's repository is **public**. Its CI and Pages jobs use GitHub-hosted runners. The planned MLX Whisper transcription job uses a *user-controlled self-hosted Mac*. These security domains **must not be conflated**. Load before any .github/workflows edits, runner setup, repository secret/permission change or transcription dispatch. Combine with network-abuse and MCP trust skills for agent-controlled jobs.

## Rules
1. **Never attach a persistent self-hosted runner to an untrusted public repository** with PR-triggered workloads. Public forks/PRs are untrusted, and self-hosted runners retain local secrets/network access across jobs. Put private transcription dispatch in a **separate private workflow repository** with limited collaborators; use a dedicated unprivileged macOS runner with explicit labels.
2. Keep public CI on `ubuntu-latest` (hosted, ephemeral), no privileged secrets in PR workflows and no `pull_request_target` checkout/exec of untrusted PR content. Never execute `github.event.*` or PR title/body as shell.
3. For `workflow_dispatch`, permit only opaque preapproved job IDs and a small set of validated settings: `project_id`, `media_sha256`, language/model variant. Never accept arbitrary shell, repo, URL, command, file path, token or Python script from a chat agent.
4. Runner obtains media from a private approved workspace or authenticated transfer channel. Video/transcripts must not enter git history, public Actions logs, issue comments or generally visible artifacts; clean temporary plaintext as policy requires.
5. Least-privilege `permissions:` per workflow/job; pin third-party actions by reviewed immutable commit SHA when practical, review dependabot updates and `GITHUB_TOKEN` scope. Distinguish `id-token:write` for trusted OIDC from long-lived PATs.
6. Bound jobs by timeout, concurrency group, per-project quota/cooldown and explicit cancellation behavior. Monitor queue length, runner offline state, disk/CPU use and repeated retry storms. Do not allow agent-triggered workflows to self-modify their own workflow definitions.
7. Never expose runner admin permissions or Keychain/Drive tokens to the agent. Protect branch permissions for the private runner repo; audit every workflow change by a trusted human. Make runner egress/network restrictions explicit.
8. A failed Pages deploy because GitHub Pages is disabled is a config issue; enabling it once is not grounds to add admin PATs to the workflow.

## Proof / review
- Check workflow events, checkout ref, permissions, branch/environment protection, action versions, accepted dispatch inputs, secret redaction, runner labels and allowed callers.
- Tests simulate replayed dispatch, invalid input, concurrent job, runner offline and output authenticity/hash mismatch. No claims of isolation without real runner deployment test.
- Record retention/cleanup and incident response: revoke credentials, disable runner, block new dispatch and preserve minimal evidence.

See [runner authorization and dispatch matrix](references/runner-guardrails.md).
