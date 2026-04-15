# Phase 2 — PR1 Runner Heartbeat

## Scope and boundaries

- Add the runner-owned periodic heartbeat for the full live runner window,
  independent of harness output cadence.
- Teach the reaper activity snapshot to consult `heartbeat` first and artifact
  mtimes second.
- Keep this phase schema-free: no `finalizing` state, no origin plumbing, no
  projection override work.

## Touched files/modules

- `src/meridian/lib/launch/runner.py`
- `src/meridian/lib/launch/streaming_runner.py`
- `src/meridian/lib/state/reaper.py`
- targeted heartbeat lifecycle unit/smoke coverage

## Claimed EARS statement IDs

- `S-RN-004`
- `S-RN-006`
- `S-RP-001`

## Touched refactor IDs

- `R-06`

## Dependencies

- `phase-1-pr1-reaper-shell`

## Tester lanes

- `@verifier`
- `@unit-tester`
- `@smoke-tester`

## Exit criteria

- Both runners start a heartbeat no later than `mark_spawn_running` and tick at
  `<=30s` cadence.
- Heartbeat shutdown is owned by an outer `finally` so task cleanup still
  happens if finalization raises.
- Reaper liveness checks prefer `heartbeat` and fall back to
  `output.jsonl`/`stderr.log`/`report.md`.
- Smoke coverage proves healthy silent runs survive the 120s inactivity window
  and genuinely stale runs still reconcile.
