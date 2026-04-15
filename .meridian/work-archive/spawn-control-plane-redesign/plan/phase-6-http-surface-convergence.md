# Phase 6 — HTTP Surface Convergence

## Scope and boundaries

This phase finishes the control-plane redesign at the app surface. It
adds the dedicated `POST /cancel` endpoint, completes the app-managed
cross-process cancel bridge, finalizes inject/interrupt HTTP parity, and
removes the legacy `DELETE` endpoint. It assumes the auth substrate,
cancel core, interrupt semantics, and liveness contract are already in
place.

## Touched files/modules

- `src/meridian/lib/app/server.py`
- `src/meridian/lib/streaming/signal_canceller.py`

## Claimed EARS statement IDs

- `CAN-002`
- `CAN-004`
- `CAN-005`
- `INT-005`
- `INT-006`
- `INJ-005`
- `INJ-006`
- `HTTP-001`
- `HTTP-002`
- `HTTP-003`
- `HTTP-004`
- `HTTP-005`

## Touched refactor IDs

- `R-05`
- `R-09`

## Dependencies

- Phase 2 `transport-auth`
- Phase 3 `interrupt-classifier`
- Phase 4 `liveness-contract`
- Phase 5 `cancel-core`

## Tester lanes

- `@verifier`: run app-surface static checks and endpoint regression.
- `@unit-tester`: cover request validation, error mapping, and
  cross-process cancel response handling.
- `@smoke-tester`: verify AF_UNIX `/inject` text/interrupt parity,
  `POST /cancel`, `DELETE` rejection, and app-managed cross-process
  cancel from a separate process.

## Exit criteria

- `POST /api/spawns/{id}/inject` accepts exactly text xor interrupt with
  the 400/422 split from the spec.
- `POST /api/spawns/{id}/cancel` is the only HTTP lifecycle endpoint and
  maps terminal/finalizing cases to the specified status codes.
- CLI cancel against an app-managed spawn can route across processes to
  the AF_UNIX app server and converge on the same terminal state.
- All remaining HTTP leaves are demonstrably satisfied by smoke and unit
  evidence.
