# Phase 4 — PR2 Origin Plumbing

## Scope and boundaries

- Add the explicit `origin` field to finalize events and make
  `finalize_spawn(..., origin=...)` mandatory.
- Update every currently-known terminal writer to pass an explicit origin label.
- Keep CAS/projection authority and backfill behavior out of scope; this phase
  only establishes the schema and complete writer fanout.

## Touched files/modules

- `src/meridian/lib/state/spawn_store.py`
- `src/meridian/lib/app/server.py`
- `src/meridian/cli/streaming_serve.py`
- `src/meridian/lib/launch/process.py`
- `src/meridian/lib/launch/runner.py`
- `src/meridian/lib/launch/streaming_runner.py`
- `src/meridian/lib/ops/spawn/api.py`
- `src/meridian/lib/ops/spawn/execute.py`
- `src/meridian/lib/state/reaper.py`
- targeted writer-surface unit coverage

## Claimed EARS statement IDs

- `S-RN-002`
- `S-RN-003`
- `S-RN-005`
- `S-RP-005`

## Touched refactor IDs

- `R-02`

## Dependencies

- `phase-2-pr1-runner-heartbeat`

## Tester lanes

- `@verifier`
- `@unit-tester`
- `@smoke-tester`

## Exit criteria

- New code cannot call `finalize_spawn` without an explicit `origin`.
- All eleven writer sites are updated and covered by tests or targeted greps.
- Reconciler remains the single non-authoritative writer.
- No phase-owned consumer logic depends on inferring origin from `error`.
