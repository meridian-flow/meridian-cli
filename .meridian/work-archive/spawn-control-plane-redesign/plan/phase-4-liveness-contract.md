# Phase 4 — Liveness Contract

## Scope and boundaries

This phase moves app-managed spawns onto the same liveness contract as
CLI-managed spawns: durable `runner_pid`, manager-owned heartbeat, and
single-writer finalize ownership. It does not add HTTP control endpoints
and does not change cancel dispatch.

## Touched files/modules

- `src/meridian/lib/streaming/spawn_manager.py`
- `src/meridian/lib/app/server.py`
- `src/meridian/lib/state/spawn_store.py`

## Claimed EARS statement IDs

- `LIV-001`
- `LIV-002`
- `LIV-003`
- `LIV-004`
- `LIV-005`
- `LIV-006`

## Touched refactor IDs

- `R-07`

## Dependencies

- Phase 1 `foundation-primitives`

## Tester lanes

- `@verifier`: run state/reaper/static verification.
- `@unit-tester`: cover heartbeat task lifecycle and app-managed finalize
  single-writer behavior.
- `@smoke-tester`: verify app-managed spawns keep heartbeat fresh, avoid
  `missing_worker_pid`, and reconcile correctly when the worker dies.

## Exit criteria

- App-managed running spawns always persist `runner_pid` and
  `launch_mode="app"`.
- `SpawnManager` owns heartbeat start/stop for app-managed sessions.
- App-managed finalize writes `origin="runner"` exactly once.
- Reaper behavior remains unchanged while recognizing the new durable
  signals.
