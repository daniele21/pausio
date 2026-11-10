---
name: pausio-pr-review
description: Use when reviewing Pausio pull requests, investigating regressions, triaging bugs or proposing a safe refactor plan. Prioritize correctness and safety findings with file/line evidence, minimal fix scope and explicit test coverage.
---

# Pausio code review and systematic debugging

## Review procedure
1. Read the PR diff and affected contracts, compare to `AGENTS.md` and `docs/ARCHITECTURE.md`. Review behavior, not just formatting.
2. For a regression: reproduce with an exact command/input shape, note expected vs actual, isolate the first failing layer (domain/policy/media/CLI/ML/UI).
3. Check all changed boundary cases: missing audio, VFR timestamps, cut edge math, output overwrite, no-model fallback, bad JSON, privacy and license obligations.
4. Raise findings by severity with path + line + concrete failure scenario. Distinguish **verified defect** from suspected risk. Suggest the smallest fix and regression test.
5. A PR that changes editing behavior must show a before/after human review plan, not just passing tests. New dependencies require licensing and local-first rationale.
6. Update an ADR if an architectural boundary or public schema changes; require docs reflecting *actual* shipped behavior.
7. Summarize review verdict, commands run, results and remaining uncertainties; never report checks as passed if they were not run.

## PR readiness
A scoped change with reproducible evidence and tests is better than a broad unreviewed rewrite. Avoid grading the product's naturalness from metadata alone.

See [review checklist](references/review-checklist.md).
