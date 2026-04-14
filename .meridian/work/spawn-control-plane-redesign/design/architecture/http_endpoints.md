# HTTP Endpoints

Realizes `spec/http_surface.md` (HTTP-001 .. HTTP-005) and the HTTP halves
of `spec/cancel.md` + `spec/inject.md` + `spec/interrupt.md`.

## Endpoint table

| Method | Path | Handler | Spec |
|---|---|---|---|
| GET | `/api/spawns` | existing list | unchanged |
| POST | `/api/spawns` | existing create | unchanged |
| GET | `/api/spawns/{id}` | existing detail | unchanged |
| POST | `/api/spawns/{id}/inject` | `inject_message` (rewritten) | INJ-005, INT-005 |
| POST | `/api/spawns/{id}/cancel` | `cancel_spawn` (new) | CAN-004 |
| ~~DELETE~~ | ~~`/api/spawns/{id}`~~ | REMOVED | CAN-005 |

Any other method/path under `/api/spawns/{id}/...` returns 404 with
`{"detail": "endpoint not found"}` (HTTP-005). FastAPI's default routing
already does this once the offending routes are deleted.

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
    record = _require_spawn(spawn_id)                      # 404 if missing
    _require_not_terminal(record)                          # 409 / 410
    _require_not_finalizing(record)                        # 503
    manager = _require_active_manager(spawn_id)            # 404 if no session

    if request.interrupt:
        result = await manager.interrupt()
        return {"ok": True, "inbound_seq": result.inbound_seq, "noop": result.noop}

    result = await manager.inject(request.text)  # text is str here per validator
    return {"ok": True, "inbound_seq": result.inbound_seq}
```

- Inject is **not** authorization-gated (INJ-006). No `AuthorizationGuard`
  call in this handler.
- Interrupt **is** authorization-gated — handled by a dependency, see
  `authorization_guard.md`.

## `POST /api/spawns/{id}/cancel`

```python
@router.post("/api/spawns/{spawn_id}/cancel",
             dependencies=[Depends(require_authorization)])
async def cancel_spawn(spawn_id: str):
    record = _require_spawn(spawn_id)                      # 404
    outcome = await signal_canceller.cancel(SpawnId(spawn_id))
    return {
        "ok": True,
        "status": outcome.status,
        "origin": outcome.origin,
        "forced": outcome.forced,
        "already_terminal": outcome.already_terminal,
    }
```

No request body. `SignalCanceller` handles idempotency — repeated calls to
the same endpoint return `already_terminal=True` on the second call.

## Error-mapping table (HTTP-004)

| Condition | Status | `detail` |
|---|---|---|
| Body fails pydantic validation | 422 | FastAPI default |
| `text` and `interrupt` both set (semantic) | 400 | `"text and interrupt are mutually exclusive"` |
| `text` empty and `interrupt` false | 400 | `"provide text or interrupt: true"` |
| Spawn id not in `spawns.jsonl` | 404 | `"spawn not found"` |
| Inject against terminal spawn | 410 | `"spawn already terminal"` |
| Cancel against terminal spawn | 200 | `{already_terminal: true, origin: <existing>}` |
| Spawn in `finalizing` | 503 + `Retry-After: 2` | `"spawn finalizing; retry"` |
| Legacy `DELETE /api/spawns/{id}` | 405 | `"method not allowed; use POST /api/spawns/{id}/cancel"` |
| Unauthorized | 403 | `"caller is not authorized for this spawn"` |

For legacy `DELETE` we explicitly register a 405 handler rather than relying
on "no route" (which would yield 404) so the operator gets a clear "you're
calling the removed endpoint" message.

## Manager lookup

Today `_require_active_manager` does a dict lookup in the app-server
process. That's correct because inject/interrupt are cooperative: only the
process owning the `SpawnManager` can route the command. If the spawn was
launched by a different app-server worker (multi-worker FastAPI), the
request must go to that worker. **Out of scope**: the app server runs
single-worker by default; multi-worker scaling is a separate design.

## Observability

Every handler logs:

```python
logger.info("spawn_control", extra={
    "spawn_id": spawn_id,
    "operation": "inject" | "interrupt" | "cancel",
    "auth_mode": "operator" | "ancestor" | "self",
    "outcome": "ok" | "denied" | "error",
})
```

Tests assert on these log lines to verify AUTH-001 "Observable" semantics.

## OpenAPI

Pydantic models feed FastAPI's OpenAPI schema. The generated schema is the
source of truth for client SDKs; `docs/api.md` references the live schema
rather than hand-written JSON.

## Test plan

- **Unit**: `InjectRequest` validates the four combinations (text / interrupt
  / both / neither) correctly.
- **Smoke**: scenario 9a — `POST /inject` with `{"text": "hi"}` works.
- **Smoke**: scenario 9b — `POST /inject` with `{"interrupt": true}` works.
- **Smoke**: scenario 9c — `POST /inject` with both rejected as 400.
- **Smoke**: scenario 14 — `POST /cancel` end-to-end transitions spawn to
  `cancelled` with origin `runner` (or `cancel` on fallback).
- **Smoke**: scenario 15 — `DELETE /api/spawns/{id}` returns 405.
