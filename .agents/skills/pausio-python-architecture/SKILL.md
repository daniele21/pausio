---
name: pausio-python-architecture
description: Use when modifying Pausio Python domain models, versioned JSON edit plans, CLI commands, public interfaces, architecture, refactoring or packaging. Maintain pure core and explicit adapter boundaries; do not use for media tuning alone.
---

# Pausio Python architecture

## Objective
Keep the package simple, typed, testable and independently evolvable; do not build a generic framework before a second real use case.

## Procedure
1. Read `docs/ARCHITECTURE.md`, `docs/DECISIONS.md` and current modules before proposing new packages.
2. Draw the dependency direction: `domain.py` and `planner.py` must **not** import `media.py`, CLI, ML libraries, FFmpeg or UI. Adapters may import the domain.
3. Preserve `EditPlan` v1 contract: integer milliseconds, `Interval` semantics [start_ms, end_ms), ordered non-overlap, duration bounds, mandatory human-review step. If incompatible, introduce versioned parsing and migration with tests rather than silently altering v1.
4. Use Python 3.11+ typing and standard library by default. Keep errors actionable, avoid hidden global state, make file-system side effects explicit. Never execute shell strings.
5. Keep CLI operations discoverable and non-destructive: `doctor`, `inspect`, `plan`, `render` currently exist; proposed commands are not implemented.
6. For a new adapter, define a small protocol and normalized DTO first. Inject the adapter into the orchestration layer; isolate platform-specific behavior.
7. Include positive/negative tests and update README/ADR when observable behavior or public contracts change.

## Definition of done
- Pure core independent of heavyweight optional dependencies.
- Backwards-compatible edit plan or explicit documented migration.
- No duplicate policy logic in adapters/CLI; error paths are tested.
- `python -m unittest discover -s tests -v` and `python -m compileall -q src` pass (or limitations disclosed).

See [contracts](references/contracts.md) for exact ownership and migration rules.
