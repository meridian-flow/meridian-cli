# Phase 2 — Finalizing Status Foundation

## Scope and Boundaries

Introduce `finalizing` as a first-class lifecycle state in the core type and
transition layer. This phase is the PR2 foundation: it widens the status
literals, centralizes active / terminal membership, and makes the lifecycle
table authoritative before any writer or consumer starts depending on the new
state.

Do not yet change terminal writers, projection rules, or reaper admissibility
logic. This phase is about the source-of-truth lifecycle contract.

## Touched Files / Modules

- `src/meridian/lib/core/domain.py`
- `src/meridian/lib/core/spawn_lifecycle.py`
- `tests/lib/test_spawn_lifecycle.py`

## Claimed EARS Statement IDs

- `S-LC-001`
- `S-LC-002`
- `S-LC-003`

## Touched Refactor IDs

- `R-01` (foundation slice)

## Dependencies

- `Phase 1`

## Tester Lanes

- `@verifier`
- `@unit-tester`

## Exit Criteria

- `SpawnStatus` includes `finalizing`.
- `ACTIVE_SPAWN_STATUSES`, `TERMINAL_SPAWN_STATUSES`, and
  `_ALLOWED_TRANSITIONS` treat `finalizing` as the single source of truth.
- Lifecycle tests prove the legal / illegal transition table directly.
- The repo remains lint-clean and type-clean after the literal widening.
