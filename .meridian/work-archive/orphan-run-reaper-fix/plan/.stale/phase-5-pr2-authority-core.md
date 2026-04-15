# Phase 5 — PR2 Authority Core

## Scope and boundaries

- Implement `mark_finalizing` as the flock-scoped CAS transition and wire the
  runner finalize path around it.
- Add authority-aware projection, `terminal_origin`, the legacy read-only shim,
  and the reconciler write guard.
- Finalize the reaper's status-based terminal semantics for `running` versus
  `finalizing`.

## Touched files/modules

- `src/meridian/lib/state/spawn_store.py`
- `src/meridian/lib/state/reaper.py`
- `src/meridian/lib/launch/runner.py`
- `src/meridian/lib/launch/streaming_runner.py`
- targeted projection/CAS unit coverage and race-oriented smoke coverage

## Claimed EARS statement IDs

- `S-LC-004`
- `S-LC-005`
- `S-LC-006`
- `S-RN-001`
- `S-RP-002`
- `S-RP-003`
- `S-RP-004`
- `S-RP-008`
- `S-PR-001`
- `S-PR-002`
- `S-PR-003`
- `S-PR-004`
- `S-PR-005`
- `S-PR-006`

## Touched refactor IDs

- `R-03`
- `R-04` (authority/cross-check slice)
- `R-07`
- `R-09` (reaper semantics slice)

## Dependencies

- `phase-3-pr2-lifecycle-surfacing`
- `phase-4-pr2-origin-plumbing`

## Tester lanes

- `@verifier`
- `@unit-tester`
- `@smoke-tester`

## Exit criteria

- `mark_finalizing` performs a locked compare-and-swap from `running` only.
- Reconciler-origin terminal writes drop only for missing/already-terminal rows;
  `finalizing` remains writable for stale-cleanup failure classification.
- Projection replaces reconciler-origin terminal tuples with later
  authoritative-origin terminal tuples and never lets a late status update
  downgrade a terminal row.
- Unit and smoke coverage exercise runner/reconciler races and confirm the
  authority rule, without rewriting `spawns.jsonl`.
