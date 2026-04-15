# Phase 1 — Defensive Reconciler Hardening

## Scope and Boundaries

Deliver the preventive PR1 path without changing the event schema. The phase
adds runner-owned heartbeat ticks, recent-activity gating in the reaper, depth
gate coverage inside `reconcile_active_spawn`, and the first half of the
reconciler split so the heartbeat policy lives in a pure decision path instead
of the existing monolith.

Do not introduce `finalizing`, `origin`, `terminal_origin`, or
`mark_finalizing` in this phase. Projection semantics remain unchanged here.

## Touched Files / Modules

- `src/meridian/lib/state/reaper.py`
- `src/meridian/lib/launch/runner.py`
- `src/meridian/lib/launch/streaming_runner.py`
- `tests/test_state/test_reaper.py`
- `tests/exec/test_streaming_runner.py`
- `tests/exec/test_lifecycle.py`
- `tests/smoke/spawn/lifecycle.md`
- `tests/smoke/state-integrity.md`

## Claimed EARS Statement IDs

- `S-RN-004`
- `S-RN-006`
- `S-RP-001`
- `S-RP-006`
- `S-RP-007`
- `S-RP-009`
- `S-OB-002`

## Touched Refactor IDs

- `R-04` (partial)
- `R-05`
- `R-06`

## Dependencies

- None

## Tester Lanes

- `@verifier`
- `@smoke-tester`
- `@unit-tester`

## Exit Criteria

- Runner heartbeat touches `heartbeat` no later than `running` entry and keeps
  ticking until the outer runner frame exits, including failures in terminal
  finalization.
- Recent `heartbeat` / `output.jsonl` / `stderr.log` / `report.md` activity
  suppresses bogus orphan stamping inside the 120s window.
- `MERIDIAN_DEPTH > 0` skips reconciliation on both batch and single-row read
  paths through `reconcile_active_spawn`.
- The reaper split is in place far enough that heartbeat gating lives in the
  pure decision path, not inlined inside write logic.
- Unit tests cover heartbeat gating and depth-gate coverage.
- Smoke tests exercise nested reads and confirm no new `orphan_run` row is
  stamped while a healthy runner is still active.
