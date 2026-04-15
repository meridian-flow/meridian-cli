# Phase 6 — PR2 Repair Evidence

## Scope and boundaries

- Finish the remaining consumer/API surfacing tied to the new lifecycle.
- Land the observability promises around `orphan_finalization` and reconciler
  CAS-miss logging.
- Prove historical poisoned rows self-repair on read, including the live
  incident set named in the design package.

## Touched files/modules

- `src/meridian/lib/ops/spawn/api.py`
- `src/meridian/lib/ops/spawn/models.py`
- `src/meridian/lib/state/reaper.py`
- test fixtures and verification that exercise historical incident rows

## Claimed EARS statement IDs

- `S-CF-003`
- `S-OB-001`
- `S-OB-002`
- `S-OB-003`
- `S-BF-001`
- `S-BF-002`

## Touched refactor IDs

- `R-01` (API stats slice)
- `R-09` (API/observability slice)

## Dependencies

- `phase-5-pr2-authority-core`

## Tester lanes

- `@verifier`
- `@unit-tester`
- `@smoke-tester`

## Exit criteria

- `api.get_spawn_stats` counts `finalizing` under the active umbrella.
- `spawn show` renders `orphan_finalization` distinctly and no surface depends
  on `exited_at` for lifecycle classification.
- Reaper logs include heartbeat/reason context and CAS-miss drops.
- Unit coverage proves the historical poisoned incidents project as `succeeded`
  on read without any `spawns.jsonl` rewrite, and smoke coverage demonstrates
  the same behavior through Meridian CLI reads.
