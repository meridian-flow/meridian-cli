# Phase 2: Transport + Auth (R-10, R-08)

Implement AF_UNIX transport for the app server and the AuthorizationGuard.

## R-10: AF_UNIX Transport

### `src/meridian/cli/app_cmd.py`
- Replace `--host`/`--port` with `--uds` parameter.
- Default socket path: `state_root / "app.sock"`.
- Use uvicorn's `uds=` parameter instead of `host=`/`port=`.
- Remove browser auto-open (no TCP port to open).
- Add a `--proxy` option or note for browser access (can be minimal — just document the pattern, don't need to implement a full proxy server yet).
- Print the socket path instead of URL.

### `src/meridian/lib/app/server.py`
- No transport-level changes needed in server.py itself — uvicorn handles AF_UNIX binding.

## R-08: AuthorizationGuard

### Create `src/meridian/lib/ops/spawn/authorization.py`
```python
_AUTH_ANCESTRY_MAX_DEPTH = 32

@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    reason: str  # "operator" | "self" | "ancestor" | "not_in_ancestry" | "missing_target" | "missing_caller_in_spawn"
    caller_id: SpawnId | None
    target_id: SpawnId

def authorize(*, state_root: Path, target: SpawnId, caller: SpawnId | None, depth: int = 0) -> AuthorizationDecision:
    # D-14: depth > 0 with missing caller is deny
    if (caller is None or str(caller) == "") and depth > 0:
        return AuthorizationDecision(False, "missing_caller_in_spawn", None, target)
    # AUTH-002: operator at depth 0
    if caller is None or str(caller) == "":
        return AuthorizationDecision(True, "operator", None, target)
    # Check target exists
    target_record = spawn_store.get_spawn(state_root, target)
    if target_record is None:
        return AuthorizationDecision(False, "missing_target", caller, target)
    # Self check
    if caller == target:
        return AuthorizationDecision(True, "self", caller, target)
    # Walk parent chain from target upward
    current = target_record
    for _ in range(_AUTH_ANCESTRY_MAX_DEPTH):
        if current.parent_id is None:
            break
        if current.parent_id == caller:
            return AuthorizationDecision(True, "ancestor", caller, target)
        current = spawn_store.get_spawn(state_root, current.parent_id)
        if current is None:
            break
    return AuthorizationDecision(False, "not_in_ancestry", caller, target)

def caller_from_env() -> tuple[SpawnId | None, int]:
    raw = os.environ.get("MERIDIAN_SPAWN_ID", "").strip()
    depth = int(os.environ.get("MERIDIAN_DEPTH", "0").strip() or "0")
    return (SpawnId(raw) if raw else None, depth)

class PeercredFailure(Exception):
    pass

def _caller_from_peercred(request) -> tuple[SpawnId | None, int]:
    """Extract caller identity from AF_UNIX SO_PEERCRED. D-19: raises PeercredFailure on failure."""
    # Implementation per architecture/authorization_guard.md
```

### Compose at CLI surfaces
- `src/meridian/cli/spawn.py` — add `--operator-override` flag for cancel subcommand.
- `src/meridian/cli/spawn_inject.py` — add auth check for `--interrupt` (not for text inject per INJ-006/D-07).

### Compose at control socket
- `src/meridian/lib/streaming/control_socket.py` — add auth check for interrupt type using `_caller_from_socket_peer` (reads SO_PEERCRED from the AF_UNIX control socket).

## EARS Statements

AUTH-001 through AUTH-007, HTTP-006

## Key Decisions

- D-06: Authorization by env-derived caller id
- D-14: depth > 0 with missing caller is deny
- D-19: Peercred failure → DENY (not operator fallback)
- D-11: AF_UNIX socket for app server

## What NOT to Change

- Do NOT add POST /cancel endpoint (Phase 5/6)
- Do NOT change SpawnManager cancel logic (Phase 5)
- Do NOT modify _terminal_event_outcome (Phase 3)
- Do NOT change runner_pid or heartbeat ownership (Phase 4)

## Verification

```bash
uv run ruff check .
uv run pyright
uv run pytest-llm
```
