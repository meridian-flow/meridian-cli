# Fix: WebSocket 403 + Control Socket Race

Two bugs from smoke testing.

## Bug 1: WebSocket endpoint returns 403 (BLOCKER)

`meridian app` starts fine, REST API works, but WebSocket connections to `/api/spawns/{spawn_id}/ws` get rejected with HTTP 403.

Root cause identified by smoke tester: the `websocket: object` type annotation in the WS endpoint function signature breaks FastAPI's WebSocket detection. FastAPI needs `websocket: WebSocket` (from `starlette.websockets`).

Check `src/meridian/lib/app/ws_endpoint.py` — find the endpoint function and fix the type annotation.

The smoke tester confirmed the fix works in an isolated test:
- With `websocket: object` → 403
- With `websocket: WebSocket` → connection accepted

## Bug 2: Control socket appears too slowly (MEDIUM)

`meridian streaming serve` starts the spawn and events flow, but the control socket at `.meridian/spawns/<id>/control.sock` doesn't appear fast enough for `meridian spawn inject` when called shortly after.

Check `src/meridian/lib/streaming/spawn_manager.py` — the control socket server should be started before `start_spawn` returns, or there should be a wait mechanism. The inject CLI should also handle "socket not yet available" more gracefully (retry with backoff instead of immediate failure).

Check `src/meridian/cli/spawn_inject.py` — add a brief retry loop (e.g., 3 attempts, 1s apart) when the socket doesn't exist yet.

## After fixing

```bash
uv run ruff check .
uv run pyright
uv run pytest-llm
```

Then smoke test:

1. Start `uv run meridian app --no-browser --port 8420` in background
2. `curl -s http://localhost:8420/api/spawns` should return `[]`
3. Create a spawn via POST
4. Connect WebSocket — should NOT get 403 anymore
5. Events should flow

For the control socket:
1. Start `uv run meridian streaming serve --harness claude -p "Hello"`
2. Immediately try `uv run meridian spawn inject <id> "test"` 
3. Should succeed (possibly after a brief retry) instead of failing with "socket not found"
