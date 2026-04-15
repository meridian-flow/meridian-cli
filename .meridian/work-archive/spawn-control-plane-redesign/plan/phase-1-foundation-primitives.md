# Phase 1 — Foundation Primitives

## Scope and boundaries

This phase lands the shared mechanical substrate that later phases build
on: heartbeat helper extraction, inject/interrupt serialization
primitives, and the durable `launch_mode="app"` schema extension. It does
not expose any new lifecycle surface and does not change HTTP behavior.

## Touched files/modules

- `src/meridian/lib/streaming/inject_lock.py`
- `src/meridian/lib/streaming/spawn_manager.py`
- `src/meridian/lib/streaming/control_socket.py`
- `src/meridian/lib/streaming/heartbeat.py`
- `src/meridian/lib/launch/runner.py`
- `src/meridian/lib/launch/streaming_runner.py`
- `src/meridian/lib/state/spawn_store.py`

## Claimed EARS statement IDs

- `INJ-001`
- `INJ-002`
- `INJ-003`
- `INJ-004`
- `INT-007`

## Touched refactor IDs

- `R-01`
- `R-02`
- `R-11`

## Dependencies

- None

## Tester lanes

- `@verifier`: run lint, type-check, and the focused regression subset
  for `spawn_manager`, control-socket replies, and spawn-store typing.
- `@unit-tester`: cover `InjectResult`, `inbound_seq`, lock
  linearization, and `launch_mode="app"` projection behavior.

## Exit criteria

- `inject_lock.py` exists and `SpawnManager` returns `inbound_seq`
  through `InjectResult`.
- Control-socket inject ordering matches durable `inbound.jsonl` order.
- `LaunchMode` and persisted spawn events accept `"app"` cleanly.
- Heartbeat helper extraction is in place without shifting ownership to
  `SpawnManager` yet.
