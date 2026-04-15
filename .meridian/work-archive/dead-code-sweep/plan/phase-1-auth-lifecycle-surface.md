# Phase 1 — Auth and Lifecycle Surface

## Scope and Boundaries

Delete the authorization feature and all caller-identity plumbing, remove
lifecycle cancel/interrupt from the MCP agent-tool surface, remove the last
shipped cancel control-plane leftovers, and update the archived redesign
artifacts to reflect the reversion.

This phase keeps AF_UNIX transport intact. It does not remove unrelated
state/schema ballast or orphaned modules; those land in later phases once the
auth surface is gone.

## Touched Files / Modules

- `src/meridian/lib/app/authorization.py`
- `src/meridian/lib/app/ws_endpoint.py`
- `src/meridian/lib/app/server.py`
- `src/meridian/lib/ops/spawn/api.py`
- `src/meridian/lib/ops/manifest.py`
- `src/meridian/server/main.py`
- `src/meridian/lib/streaming/types.py`
- `src/meridian/lib/streaming/control_socket.py`
- `src/meridian/cli/spawn_inject.py`
- `src/meridian/cli/spawn.py`
- `src/meridian/lib/launch/errors.py`
- auth-related tests under `tests/`
- `.meridian/work/dead-code-sweep/requirements.md`
- `.meridian/work/dead-code-sweep/decisions.md`
- `.meridian/work-archive/spawn-control-plane-redesign/design/spec/authorization.md`
- `.meridian/work-archive/spawn-control-plane-redesign/design/architecture/authorization_guard.md`

## Claimed EARS Statement IDs

- `S-AUTH-001`
- `S-AUTH-002`
- `S-AUTH-003`
- `S-AUTH-004`
- `S-AUTH-005`
- `S-AUTH-006`
- `S-AUTH-007`
- `S-TOOL-001`
- `S-TOOL-002`
- `S-DEL-001`
- `S-DEL-002`
- `S-DEL-003`
- `S-DEL-004`
- `S-DEL-016`

## Touched Refactor IDs

- `R-01`
- `R-02`
- `R-03`

## Dependencies

- None

## Tester Lanes

- `@verifier`
- `@smoke-tester`
- `@unit-tester`

## Exit Criteria

- `AuthorizationGuard`, its module, and every `authorize()` / caller-identity
  call site are gone.
- SO_PEERCRED, `/proc/<pid>/environ`, and the auth-specific
  `MERIDIAN_SPAWN_ID` read paths are removed.
- `caller_from_env()`, `_caller_from_http()`, `_caller_from_socket_peer()`, and
  the WebSocket env fallback are removed.
- MCP tool registration no longer exposes cancel or interrupt lifecycle actions,
  while cooperative text inject remains available.
- `CancelControl`, the control-socket cancel shim, the CLI `--cancel` inject
  path, and the legacy `DELETE /api/spawns/{id}` surface are deleted.
- Archived auth design docs are removed, `D-25` records the reversion of
  `D-06`, `D-14`, and `D-19`, and success criterion 5 is restated to match the
  reduced MCP surface.
- Smoke and unit coverage prove AF_UNIX transport still works without auth and
  that lifecycle cancel is no longer reachable through the agent-tool surface.
