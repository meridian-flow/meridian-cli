# Authorization Guard

Realizes `spec/authorization.md` (AUTH-001 .. AUTH-006).

## Module

New file: `src/meridian/lib/ops/spawn/authorization.py`.

Kept under `ops/spawn/` because it is policy, not state mechanism. The
guard never writes and only reads the existing `spawns.jsonl` projection.

```python
_AUTH_ANCESTRY_MAX_DEPTH = 32

@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    reason: str          # "operator" | "self" | "ancestor" | "not_in_ancestry" | "missing_target"
    caller_id: SpawnId | None
    target_id: SpawnId

def authorize(
    *,
    state_root: Path,
    target: SpawnId,
    caller: SpawnId | None,
) -> AuthorizationDecision:
    """Pure function. No side effects."""
    if caller is None or str(caller) == "":
        return AuthorizationDecision(True, "operator", None, target)

    target_record = spawn_store.get_spawn(state_root, target)
    if target_record is None:
        return AuthorizationDecision(False, "missing_target", caller, target)

    if caller == target:
        return AuthorizationDecision(True, "self", caller, target)

    # Walk parent chain from target upward.
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


def caller_from_env() -> SpawnId | None:
    raw = os.environ.get("MERIDIAN_SPAWN_ID", "").strip()
    return SpawnId(raw) if raw else None
```

## Surface composition

**CLI** (`src/meridian/cli/spawn_cancel.py`, `spawn_inject.py` for
`--interrupt`):

```python
decision = authorize(state_root=paths.state_root(),
                     target=spawn_id,
                     caller=caller_from_env())
logger.info("spawn_auth", extra={"decision": asdict(decision)})
if not decision.allowed:
    typer.echo(f"Error: caller {decision.caller_id} is not authorized to "
               f"{action} {spawn_id}", err=True)
    raise typer.Exit(code=2)
```

**HTTP** — FastAPI dependency `require_authorization(spawn_id: str,
request: Request)`:

```python
async def require_authorization(spawn_id: str, request: Request):
    caller = _caller_from_http(request)  # env at app startup; see below
    decision = authorize(state_root=app_state.state_root,
                         target=SpawnId(spawn_id),
                         caller=caller)
    request.state.auth = decision
    if not decision.allowed:
        raise HTTPException(
            status_code=403,
            detail="caller is not authorized for this spawn",
        )
```

Applied as a dependency on `/cancel` and on the interrupt branch of
`/inject` (either by inlining the guard after parsing the body, or by
splitting the interrupt branch into a separate inner handler that depends
on `require_authorization`).

**Control socket** — `ControlSocketServer` handles `interrupt` only (cancel
is already removed). Before dispatching:

```python
caller = _caller_from_socket_peer(peer_creds)  # SO_PEERCRED / SCM_CREDENTIALS
decision = authorize(state_root=self._state_root,
                     target=self._spawn_id, caller=caller)
if not decision.allowed:
    await self._write(writer, {"ok": False,
                               "error": "interrupt requires caller authorization"})
    return
```

Peer credentials come from the SO_PEERCRED option on AF_UNIX sockets. The
peer PID lets us read `/proc/<pid>/environ` for `MERIDIAN_SPAWN_ID`. That
same mechanism is used by `SpawnManager` today to reject unknown peers; we
extend it to extract the caller id.

**Agent tool** surfaces go through the CLI or HTTP entrypoints; they do not
grow a separate code path (AUTH-006).

## How caller id reaches each surface

| Surface | Source |
|---|---|
| CLI (user, cron, systemd) | `MERIDIAN_SPAWN_ID` env of the CLI process |
| CLI spawned by another spawn | `MERIDIAN_SPAWN_ID` env inherited from parent via `command.py` |
| HTTP inside same process | `MERIDIAN_SPAWN_ID` of the FastAPI worker process |
| HTTP called by a spawned subagent | that subagent's env propagates via headers? **No.** The FastAPI server is loopback-only; we read the *connecting process's* env by finding the caller PID through SO_PEERCRED on the TCP socket (Linux has this; macOS needs a fallback). |
| Control socket | SO_PEERCRED on the AF_UNIX socket |

**Fallback for macOS TCP peercred**: the app server refuses to apply
authorization when the peer PID cannot be determined and logs
`auth_mode="unknown"`. We tighten later if/when we grow a network deployment
story. In practice all development targets Linux; macOS local-dev usage is
a single-user machine so operator mode is safe.

## Why not a header?

A `MERIDIAN-Caller-Id` header would be trivially forgeable. Env-based
identification is also forgeable by anyone with `fork + exec + setenv`, but
the threat model (AUTH §threat model) is "a spawned subagent shells out to
cancel" — that agent inherits its own env honestly; there is no adversary
*within* meridian's process tree trying to pose as its parent.

If we ever grow remote auth, we replace the `caller_from_*` helpers without
touching the core `authorize()` function. That boundary is why
`authorize()` is a pure function taking a `SpawnId | None`, not an HTTP
request.

## Agent profiles and allowlists

An agent profile wanting to deny a subagent lifecycle control over its
siblings simply removes `spawn-cancel` / `spawn-interrupt` from the
tool allowlist. The guard still runs for agents that do have the tool;
removing the tool is the belt, the guard is the suspenders.

## Test plan

- **Unit**: `authorize()` for (caller=None, caller=self, caller=parent,
  caller=grandparent, caller=sibling, caller=stranger, target=missing,
  cycle in chain).
- **Unit**: `caller_from_env()` handles unset, empty, padded strings.
- **Smoke**: scenario 16 — child spawn cancels itself → allowed. Child
  cancels sibling → 403 (HTTP) / exit 2 (CLI).
- **Smoke**: scenario 17 — operator shell (no env) cancels any spawn →
  allowed.
- **Smoke**: scenario 18 — control-socket interrupt from non-ancestor →
  rejected with stable error; no inbound event written; no send to harness.
