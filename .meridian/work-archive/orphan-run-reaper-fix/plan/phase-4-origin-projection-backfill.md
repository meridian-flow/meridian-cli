# Phase 4 — Origin, Projection, and Backfill

## Scope and Boundaries

Add explicit finalize origins and make projection authority depend on origin
data instead of `error` heuristics. This phase also updates every terminal
writer site, adds `terminal_origin`, exposes the `finalizing` stats bucket, and
ships the read-only legacy shim that self-repairs poisoned historical rows on
read.

Do not add `mark_finalizing` or reconciler CAS semantics here. Reconciler
admissibility against `finalizing` remains Phase 5.

## Touched Files / Modules

- `src/meridian/lib/state/spawn_store.py`
- `src/meridian/lib/state/reaper.py`
- `src/meridian/lib/launch/process.py`
- `src/meridian/lib/launch/runner.py`
- `src/meridian/lib/launch/streaming_runner.py`
- `src/meridian/cli/streaming_serve.py`
- `src/meridian/lib/app/server.py`
- `src/meridian/lib/ops/spawn/execute.py`
- `src/meridian/lib/ops/spawn/api.py`
- `tests/test_state/test_spawn_store.py`
- `tests/ops/test_spawn_api.py`
- `tests/test_app_server.py`
- `tests/test_launch_process.py`
- `tests/smoke/state-integrity.md`

## Claimed EARS Statement IDs

- `S-RN-002`
- `S-RN-003`
- `S-RN-005`
- `S-RP-004`
- `S-RP-005`
- `S-PR-001`
- `S-PR-002`
- `S-PR-003`
- `S-PR-004`
- `S-PR-005`
- `S-CF-003`
- `S-BF-001`
- `S-BF-002`

## Touched Refactor IDs

- `R-02`
- `R-07`
- `R-01` (stats slice)
- `R-09` (API slice)

## Dependencies

- `Phase 2`

## Tester Lanes

- `@verifier`
- `@smoke-tester`
- `@unit-tester`

## Exit Criteria

- `finalize_spawn(..., origin=...)` is mandatory and every one of the 11 writer
  sites passes an explicit origin.
- Projection derives and preserves `terminal_origin`, with authoritative-origin
  terminal events able to supersede prior reconciler-origin terminal events only
  in the designed direction.
- The legacy shim is isolated to `origin is None` rows and unit-tested so it is
  never consulted for new events.
- Unit tests assert the live poisoned rows `p1711`, `p1712`, `p1731`, and
  `p1732` project to `succeeded`, plus any additional poisoned rows found in
  the current `.meridian/spawns.jsonl` inventory at execution time.
- Smoke tests cover at least one real success path and one cancel / launch-path
  path so writer tagging is exercised against real filesystem state.
