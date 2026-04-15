# Phase 2 — Transport And Auth

## Scope and boundaries

This phase moves the app surface onto AF_UNIX and lands the shared
`AuthorizationGuard` plus CLI/control-socket composition. It owns the
policy and transport substrate, but it does not yet introduce the new
HTTP lifecycle endpoints; Phase 6 consumes the guard when those endpoints
arrive.

## Touched files/modules

- `src/meridian/cli/app_cmd.py`
- `src/meridian/lib/ops/spawn/authorization.py`
- `src/meridian/lib/ops/spawn/api.py`
- `src/meridian/lib/streaming/control_socket.py`
- `src/meridian/cli/spawn_inject.py`
- `src/meridian/cli/spawn.py`

## Claimed EARS statement IDs

- `AUTH-001`
- `AUTH-002`
- `AUTH-003`
- `AUTH-004`
- `AUTH-005`
- `AUTH-006`
- `AUTH-007`
- `HTTP-006`

## Touched refactor IDs

- `R-08`
- `R-10`

## Dependencies

- Phase 1 `foundation-primitives`

## Tester lanes

- `@verifier`: run the CLI/app command regression slice and static checks.
- `@unit-tester`: cover `authorize()`, ancestry bounds, env parsing, and
  peercred failure handling.
- `@smoke-tester`: start the app over AF_UNIX, verify no default TCP bind,
  and exercise CLI/control-socket auth accept/deny paths.

## Exit criteria

- Primary app launch uses AF_UNIX rather than `--host`/`--port`.
- `AuthorizationGuard` exists as a pure policy module and is enforced on
  CLI lifecycle/interrupt surfaces plus the control socket.
- `depth > 0` with missing caller denies by default.
- No new HTTP lifecycle surface is exposed without the guard available
  for Phase 6 to compose.
