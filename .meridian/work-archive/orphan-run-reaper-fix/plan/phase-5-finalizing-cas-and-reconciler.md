# Phase 5 — Finalizing CAS and Reconciler

## Scope and Boundaries

Close the structural fix by adding atomic `running -> finalizing`, the
reconciler admissibility guard, finalizing-specific orphan classification, and
the invariant that late status updates never downgrade a terminal row. This is
the concurrency-sensitive phase that turns the earlier scaffolding into the full
Round 2 lifecycle protocol.

Do not extend `finalizing` to non-runner writers, rewrite `is_process_alive`,
or collapse the reconcile call graph. Those are explicit design fences.

## Touched Files / Modules

- `src/meridian/lib/state/spawn_store.py`
- `src/meridian/lib/state/reaper.py`
- `src/meridian/lib/launch/runner.py`
- `src/meridian/lib/launch/streaming_runner.py`
- `src/meridian/lib/core/spawn_lifecycle.py`
- `tests/test_state/test_spawn_store.py`
- `tests/test_state/test_reaper.py`
- `tests/exec/test_streaming_runner.py`
- `tests/ops/test_spawn_read_reconcile.py`
- `tests/smoke/spawn/lifecycle.md`
- `tests/smoke/state-integrity.md`

## Claimed EARS Statement IDs

- `S-LC-004`
- `S-LC-005`
- `S-LC-006`
- `S-RN-001`
- `S-RP-002`
- `S-RP-003`
- `S-RP-008`
- `S-PR-006`
- `S-OB-003`

## Touched Refactor IDs

- `R-03`
- `R-04` (remainder)
- `R-01` (lifecycle-validator wiring slice)
- `R-09` (reaper classification slice)

## Dependencies

- `Phase 1`
- `Phase 2`
- `Phase 4`

## Tester Lanes

- `@verifier`
- `@smoke-tester`
- `@unit-tester`

## Exit Criteria

- `mark_finalizing(state_root, spawn_id) -> bool` performs the check and append
  under `spawns.jsonl.flock` and tolerates CAS misses without turning them into
  runner failures.
- Reconciler-origin terminal writes re-check projected state under the same
  flock and drop only the missing-row / already-terminal cases; stale
  `finalizing` rows still close as `orphan_finalization`.
- Late `SpawnUpdateEvent.status` rows never downgrade a terminal projection.
- Runner finalizing transition resets heartbeat at the lifecycle handoff point.
- Unit tests cover CAS races, late-update projection, and admissibility edges.
- Smoke tests cover both failure windows called out in pre-planning:
  `orphan_run` only after heartbeat silence beyond 120s, and
  `orphan_finalization` only when a runner dies inside the cleanup window.
