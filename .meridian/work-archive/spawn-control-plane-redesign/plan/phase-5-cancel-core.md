# Phase 5 — Cancel Core

## Scope and boundaries

This phase lands the shared cancel semantics and removes the old
control-socket cancel path. It owns `SignalCanceller` core behavior for
CLI-launched spawns plus the idempotency/finalizing/PID-reuse rules that
both cancel lanes share. It intentionally stops short of the new HTTP
endpoint and cross-process app-cancel bridge; Phase 6 finishes that
convergence work.

## Touched files/modules

- `src/meridian/lib/streaming/signal_canceller.py`
- `src/meridian/lib/ops/spawn/api.py`
- `src/meridian/lib/streaming/control_socket.py`
- `src/meridian/lib/streaming/spawn_manager.py`
- `src/meridian/cli/spawn_inject.py`
- `src/meridian/cli/spawn.py`

## Claimed EARS statement IDs

- `CAN-001`
- `CAN-003`
- `CAN-006`
- `CAN-007`
- `CAN-008`

## Touched refactor IDs

- `R-03`
- `R-06`

## Dependencies

- Phase 1 `foundation-primitives`
- Phase 2 `transport-auth`

## Tester lanes

- `@verifier`: run cancel-path static checks and CLI command regression.
- `@unit-tester`: cover `SignalCanceller` finalizing gate, PID-reuse
  guard, grace-expiry behavior, and idempotency.
- `@smoke-tester`: verify CLI cancel on running spawns and stable reject
  behavior for control-socket cancel attempts.

## Exit criteria

- `SignalCanceller` exists and owns CLI-lane cancel semantics.
- `spawn inject --cancel` and control-socket `type="cancel"` are gone.
- Finalizing cancel never escalates to SIGKILL and follows the bounded
  wait behavior from the spec.
- Terminal/idempotent cancel behavior is stable for the shared canceller
  core before HTTP convergence begins.
