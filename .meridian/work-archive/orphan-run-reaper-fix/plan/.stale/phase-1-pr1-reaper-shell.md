# Phase 1 — PR1 Reaper Shell

## Scope and boundaries

- Extract the pure reconciliation decider and keep I/O, logging, and event
  emission in the `reconcile_active_spawn` shell.
- Move the `MERIDIAN_DEPTH > 0` short-circuit into `reconcile_active_spawn` so
  both batch and single-row reads inherit it.
- Keep this phase schema-free: no `finalizing`, no origin field, no projection
  override logic.

## Touched files/modules

- `src/meridian/lib/state/reaper.py`
- targeted reaper unit/smoke coverage for batch and single-row read paths

## Claimed EARS statement IDs

- `S-RP-006`
- `S-RP-007`
- `S-RP-009`

## Touched refactor IDs

- `R-04` (minimal PR1 slice)
- `R-05`

## Dependencies

- none

## Tester lanes

- `@verifier`
- `@unit-tester`
- `@smoke-tester`

## Exit criteria

- `reconcile_active_spawn` is the single read-path depth gate for reconciliation.
- `read_spawn_row` and every batch call path inherit the gate without duplicated
  conditionals.
- The pure decider is unit-tested across skip/finalize/report branches.
- Smoke coverage shows `MERIDIAN_DEPTH > 0` nested reads no longer stamp active
  spawns.
