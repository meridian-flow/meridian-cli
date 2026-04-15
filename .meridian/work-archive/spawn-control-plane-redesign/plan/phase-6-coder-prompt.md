# Phase 6: HTTP Surface Convergence (R-05, R-09)

Final phase. Complete the HTTP control-plane surface and cross-process cancel bridge.

## What to Build

### R-05: Reshape HTTP spawn-control surface in `src/meridian/lib/app/server.py`

1. **Rewrite InjectRequest with pydantic model_validator:**
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
```

2. **Custom exception handler for semantic validation (D-17):**
   - Add exception handler that catches `ValueError` from `model_validator` and returns HTTP 400.
   - FastAPI's default pydantic handler covers schema errors → 422.

3. **Add `POST /api/spawns/{id}/cancel` endpoint (CAN-004):**
```python
@router.post("/api/spawns/{spawn_id}/cancel")
async def cancel_spawn(spawn_id: str):
    # Auth check via require_authorization dependency
    record = _require_spawn(spawn_id)
    if _spawn_is_terminal(record.status):
        raise HTTPException(409, detail=f"spawn already terminal: {record.status}")
    
    canceller = SignalCanceller(
        state_root=app_state.state_root,
        manager=app_state.manager,  # in-process cancel for app spawns
    )
    outcome = await canceller.cancel(SpawnId(spawn_id))
    
    if outcome.finalizing:
        raise HTTPException(503, detail="spawn is finalizing", headers={"Retry-After": "2"})
    if outcome.already_terminal:
        raise HTTPException(409, detail=f"spawn already terminal: {outcome.status}")
    
    return {"ok": True, "status": outcome.status, "origin": outcome.origin}
```

4. **Remove `DELETE /api/spawns/{id}` (CAN-005):**
   - Add 405 handler: `{"detail": "use POST /api/spawns/{id}/cancel for lifecycle cancel"}`

5. **Update inject endpoint for interrupt parity:**
   - Inject with `interrupt: true` → call `manager.interrupt()` (with auth check)
   - Inject with `text` → call `manager.inject()` (NO auth check, per INJ-006)
   - Terminal spawn → 410
   - Finalizing spawn → 503

6. **Auth dependency for lifecycle operations:**
   - Cancel endpoint: use `require_authorization` dependency (from Phase 2)
   - Interrupt in inject endpoint: check auth
   - Text inject: NO auth check (INJ-006)

### R-09: Cross-process cancel bridge in `src/meridian/lib/streaming/signal_canceller.py`

The `_cancel_app_spawn` method's cross-process path (`self._manager is None`):
- Connect to `.meridian/app.sock` AF_UNIX socket
- Send `POST /api/spawns/{id}/cancel`
- Parse response: 200 → success, 409 → already terminal, 503 → finalizing
- Use `aiohttp` or `httpx` with Unix socket support, or raw `asyncio` streams

Check if `httpx` or `aiohttp` is already a dependency — if so, use it. If neither, use raw asyncio connection to the Unix socket.

### Error mapping table (HTTP-004)

| Condition | Code | Detail |
|---|---|---|
| Schema validation | 422 | FastAPI default |
| text + interrupt both | 400 | "text and interrupt are mutually exclusive" |
| neither set | 400 | "provide text or interrupt: true" |
| Spawn not found | 404 | "spawn not found" |
| Inject on terminal | 410 | "spawn already terminal" |
| Cancel on terminal | 409 | "spawn already terminal: <status>" |
| Finalizing | 503 | "spawn is finalizing" |
| Legacy DELETE | 405 | "use POST /cancel" |
| Unauthorized | 403 | "caller is not authorized" |

## EARS Statements

CAN-002, CAN-004, CAN-005, INT-005, INT-006, INJ-005, INJ-006, HTTP-001..HTTP-005

## What NOT to Change

- Do not change the cancel core (SignalCanceller) except to add the cross-process HTTP bridge
- Do not change the authorization guard logic
- Do not change the classifier or liveness contract

## Verification

```bash
uv run ruff check .
uv run pyright
uv run pytest-llm
```
