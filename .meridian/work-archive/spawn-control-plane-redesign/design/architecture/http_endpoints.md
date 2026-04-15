# HTTP Endpoints (v2r2)

Realizes `spec/http_surface.md` (HTTP-001..HTTP-006) and the HTTP halves
of `spec/cancel.md`, `spec/inject.md`, `spec/interrupt.md`.

## Transport: AF_UNIX (v2 change, D-11)

The app server binds to `.meridian/app.sock` via uvicorn's `--uds`
support:

```python
# app_cmd.py (revised)
def run_app(
    uds: str | None = None,      # replaces --host/--port
    no_browser: bool = False,
    debug: bool = False,
    allow_unsafe_no_permissions: bool = False,
) -> None:
    socket_path = uds or str(state_root / "app.sock")
    uvicorn_module.run(app, uds=socket_path, log_level="info")
```

Browser access uses a `--proxy` subcommand that starts a TCP-to-UDS
reverse proxy (tiny asyncio bridge). CLI and agent callers connect
directly to the Unix socket.

`--host` is removed. No `--host 0.0.0.0` exposure (resolves BL-6).

## Endpoint table

| Method | Path | Handler | Spec |
|---|---|---|---|
| GET | `/api/spawns` | existing list | unchanged |
| POST | `/api/spawns` | existing create | unchanged |
| GET | `/api/spawns/{id}` | existing detail | unchanged |
| POST | `/api/spawns/{id}/inject` | `inject_message` (rewritten) | INJ-005, INT-005 |
| POST | `/api/spawns/{id}/cancel` | `cancel_spawn` (new) | CAN-004 |
| ~~DELETE~~ | ~~`/api/spawns/{id}`~~ | REMOVED | CAN-005 |

Any other path returns 404 (HTTP-005).

## `POST /api/spawns/{id}/inject`

```python
class InjectRequest(BaseModel):
    text: str | None = None
    interrupt: bool = False

    @model_validator(mode="after")
    def _exactly_one(self) -> "InjectRequest":
        text_set = self.text is not None and self.text.strip() != ""
        if text_set and self.interrupt:
            raise ValueError("text and interrupt are mutually exclusive")
        if not text_set and not self.interrupt:
            raise ValueError("provide text or interrupt: true")
        return self

@router.post("/api/spawns/{spawn_id}/inject")
async def inject_message(spawn_id: str, request: InjectRequest):
    record = _require_spawn(spawn_id)
    _require_not_terminal(record)                          # 410 for inject/interrupt
    _require_not_finalizing(record)                        # 503
    manager = _require_active_manager(spawn_id)            # 404

    if request.interrupt:
        _require_authorization(spawn_id, request_obj)      # AUTH gate
        result = await manager.interrupt(typed_id, source="rest")
        return {"ok": True, "inbound_seq": result.inbound_seq,
                "noop": result.noop}

    # Inject is NOT gated (INJ-006)
    result = await manager.inject(typed_id, request.text, source="rest")
    return {"ok": True, "inbound_seq": result.inbound_seq}
```

## `POST /api/spawns/{id}/cancel` (v2r2 — two-lane aware)

```python
@router.post("/api/spawns/{spawn_id}/cancel",
             dependencies=[Depends(require_authorization)])
async def cancel_spawn(spawn_id: str):
    record = _require_spawn(spawn_id)
    if _spawn_is_terminal(record.status):
        raise HTTPException(409, detail=f"spawn already terminal: {record.status}")

    # v2r2: SignalCanceller accepts optional manager for in-process
    # app-spawn cancel (D-03 two-lane). When the cancel endpoint runs
    # inside the FastAPI worker, it can cancel app-managed spawns directly.
    canceller = SignalCanceller(
        state_root=app_state.state_root,
        manager=app_state.manager,   # enables in-process cancel for app spawns
    )
    outcome = await canceller.cancel(SpawnId(spawn_id))

    if outcome.finalizing:
        raise HTTPException(503, detail="spawn is finalizing",
                           headers={"Retry-After": "2"})
    if outcome.already_terminal:
        raise HTTPException(409, detail=f"spawn already terminal: {outcome.status}")

    return {"ok": True, "status": outcome.status, "origin": outcome.origin}
```

**v2 resolution of BL-7.** Already-terminal cancel returns `409`, not
`200`. Spec and architecture agree (D-16).

## Error-mapping table (HTTP-004, v2r2 with D-17 split)

| Condition | Status | `detail` | Source |
|---|---|---|---|
| Body fails pydantic validation (missing fields, wrong types) | 422 | FastAPI default | pydantic |
| text + interrupt both set (semantic) | 400 | `"text and interrupt are mutually exclusive"` | `model_validator` → custom handler |
| text empty + interrupt false (semantic) | 400 | `"provide text or interrupt: true"` | `model_validator` → custom handler |
| Spawn id not found | 404 | `"spawn not found"` | handler |
| Inject against terminal | 410 | `"spawn already terminal"` | handler |
| Cancel against terminal | 409 | `"spawn already terminal: <status>"` | handler |
| Spawn in `finalizing` | 503 + `Retry-After: 2` | `"spawn is finalizing"` | handler |
| Legacy DELETE | 405 | `"use POST /cancel"` | handler |
| Unauthorized | 403 | `"caller is not authorized"` | auth dep |
| Caller identity unavailable (D-19) | 403 | `"caller identity unavailable"` | auth dep |

**v2r2 validation split (D-17).** Semantic validation errors from
`model_validator` raise `ValueError`, which a custom exception handler
remaps to 400. Structural validation (missing fields, wrong types) stays
at 422 via FastAPI's default pydantic handler. This resolves the p1794
finding that INT-006 says 400 but `model_validator` produces 422 by default.

## Authorization extraction via SO_PEERCRED (v2r2 — D-19 deny-on-failure)

```python
async def require_authorization(spawn_id: str, request: Request):
    try:
        caller, depth = _caller_from_peercred(request)
    except PeercredFailure as exc:
        # D-19: peercred failure → DENY for lifecycle ops
        logger.warning("spawn_auth_peercred_failure",
                       extra={"error": str(exc), "spawn_id": spawn_id})
        raise HTTPException(403, detail="caller identity unavailable")

    decision = authorize(
        state_root=app_state.state_root,
        target=SpawnId(spawn_id),
        caller=caller,
        depth=depth,
    )
    if not decision.allowed:
        raise HTTPException(403, detail="caller is not authorized")
```

`_caller_from_peercred` reads the connecting process's PID via
`SO_PEERCRED` on the AF_UNIX socket, then reads
`/proc/<pid>/environ` for `MERIDIAN_SPAWN_ID` and `MERIDIAN_DEPTH`.

**v2r2 (D-19).** On failure — macOS without PID, peer exited before
`/proc` read, permission denied — `_caller_from_peercred` raises
`PeercredFailure` and the dependency returns 403. Operator mode is only
available via CLI env path. This design does not define a fallback
header for peercred-unavailable HTTP callers.

## Manager lookup

`_require_active_manager` does a dict lookup in the app-server process.
Only the process owning the `SpawnManager` can route inject/interrupt.
Multi-worker scaling is out of scope (single-worker default).

## Test plan

### Unit tests
- `InjectRequest` validates four combinations.

### Smoke tests
- Scenario 9a: `POST /inject` with text via AF_UNIX.
- Scenario 9b: `POST /inject` with interrupt via AF_UNIX.
- Scenario 9c: both text and interrupt → 400.
- Scenario 14: `POST /cancel` end-to-end.
- Scenario 15: `DELETE` → 405.
- Scenario 19: app server starts on AF_UNIX socket.

### Fault-injection tests
- **Cancel-during-finalize via HTTP**: verify 503, not 200.
- **Concurrent HTTP cancels**: verify idempotency (409 on second).
