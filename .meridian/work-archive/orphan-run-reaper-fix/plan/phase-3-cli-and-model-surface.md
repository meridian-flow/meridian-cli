# Phase 3 — CLI and Model Surface

## Scope and Boundaries

Make the user-facing CLI and formatting layer treat `finalizing` and
`orphan_finalization` as literal states rather than heuristics inferred from
`exited_at`. This phase updates the active-view filter, `--status` validation,
post-launch success handling, and text rendering in the lightweight spawn
models.

Do not change `spawn_store.py`, `reaper.py`, or any finalize-writer contract in
this phase. Those remain owned by Phase 4 and Phase 5.

## Touched Files / Modules

- `src/meridian/cli/spawn.py`
- `src/meridian/lib/ops/spawn/models.py`
- `tests/test_cli_spawn.py`
- `tests/ops/test_spawn_read_reconcile.py`
- `tests/smoke/spawn/lifecycle.md`

## Claimed EARS Statement IDs

- `S-CF-001`
- `S-CF-002`
- `S-CF-004`
- `S-OB-001`

## Touched Refactor IDs

- `R-01` (CLI / model consumer slice)
- `R-09` (CLI / formatter slice)

## Dependencies

- `Phase 2`

## Tester Lanes

- `@verifier`
- `@smoke-tester`
- `@unit-tester`

## Exit Criteria

- `meridian spawn list --status finalizing` and the active view both accept the
  new status.
- Post-launch CLI handling treats `finalizing` as a valid non-error state.
- `spawn show` / list formatting no longer uses `running*` or
  "awaiting finalization" heuristics derived from `exited_at`.
- `orphan_finalization` renders with the distinct "report may still be useful"
  guidance required by the spec.
- CLI smoke tests exercise the visible behavior end to end, not just model
  formatting in isolation.
