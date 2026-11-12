# Self-hosted runner / workflow dispatch gate

**Critical:** keep untrusted Pausio public-repo pull requests away from a personal Mac runner. GitHub documentation cautions that public-repository self-hosted runners can be persistently compromised by untrusted PR code: https://docs.github.com/en/actions/reference/security/secure-use

Proposed architecture:
`approved local Pausio job -> scoped broker -> GitHub workflow_dispatch in PRIVATE runner repo -> dedicated self-hosted macOS runner -> Pausio-owned MLX Whisper -> authenticated, content-addressed result -> Pausio workspace`.

Mandatory fields: opaque job ID, media SHA-256, owner/project binding, locale, pinned model ID/revision, bounded audio duration. Never pass literal media path via workflow inputs. Require signature/binding on stored results.

Security checklist:
- [ ] Repo private; runner label unique and restricted to the private repo/runner group
- [ ] No public PR events, pull_request_target, untrusted workflow_run chaining
- [ ] dispatch token read/write minimum permission, stored outside project JSON, rotate/revoke
- [ ] GitHub Actions `permissions:` minimal, `timeout-minutes`, `concurrency` and max jobs per project
- [ ] No arbitrary shell commands/tools in agent-provided input; fixed scripts under trusted protected branch
- [ ] No public media artifact, no transcript in logs; storage 0600/0700, private job scratch cleanup
- [ ] Runner is unprivileged, secrets isolated, host firewall and network egress reviewed
- [ ] Offline/timeout/invalid source hash and duplicate dispatch fail safely
- [ ] Human can see pending/running/failed jobs and revoke connector permissions
- [ ] Manual real runner acceptance on sample fixture before reporting automated transcription works

Supply-chain posture: review actions and lock to immutable commit SHAs when feasible; use trusted OIDC where appropriate, avoid long-lived admin PAT.
