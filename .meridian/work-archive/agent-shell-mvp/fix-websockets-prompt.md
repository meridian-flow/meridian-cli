# Fix: websockets 16.0 API compatibility in connection adapters

## The Bug

The Claude and Codex connection adapters use `.closed` on websocket objects, but websockets 16.0 doesn't have a `.closed` attribute. It has `.state` which is a `websockets.connection.State` enum with values: `CONNECTING=0`, `OPEN=1`, `CLOSING=2`, `CLOSED=3`.

This crashes immediately on first real use:
```
AttributeError: 'ServerConnection' object has no attribute 'closed'
```

## Files to Fix

1. **`src/meridian/lib/harness/connections/claude_ws.py`** — Two `.closed` references:
   - Line 409: `if self._ws is not None and not self._ws.closed:`
   - Line 418: `if ws is None or ws.closed:`

2. **`src/meridian/lib/harness/connections/codex_ws.py`** — One `.closed` reference:
   - Line 52: `return bool(self._ws.closed)`

## The Fix

Replace `.closed` checks with the websockets 16.0 API:

```python
from websockets.connection import State as WsState

# Instead of: ws.closed
# Use: ws.state is not WsState.OPEN
# Or for "is closed": ws.state is WsState.CLOSED
```

## Also Check

- **`src/meridian/lib/harness/connections/opencode_http.py`** — Verify it doesn't use `.closed` on any websocket object (it uses HTTP, so probably clean, but verify).
- Any other websockets API assumptions that don't match v16.0 — check `.send()`, `.recv()`, `.close()`, `websockets.serve()` usage against the actual asyncio API.
- The `websockets>=14.0` pin in `pyproject.toml` — if the code requires v16 API, the pin should reflect that. Or make the code work with both 14+ and 16.

## After Fixing

Run:
```bash
uv run ruff check .
uv run pyright
uv run pytest-llm
```

Then attempt the real smoke test:
```bash
uv run meridian streaming serve --harness claude -p "List files in the current directory"
```

Report what happens — does it get past the initial send? Does it receive events? If it fails at a different point, report the new error.
