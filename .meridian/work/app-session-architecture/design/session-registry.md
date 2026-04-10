# Session Registry

## What a Session Is

A session is a URL-addressable alias for a spawn. It maps a random, globally unique ID to a repo-scoped spawn_id. This indirection exists because:

1. **Spawn IDs are sequential and predictable** (`p1`, `p2`, ...) — unsuitable for URLs that might be shared or bookmarked.
2. **Spawn IDs are only unique within a repo** — when `--host` is added later, a session ID must be globally unambiguous.
3. **URLs should be opaque** — exposing spawn IDs in URLs leaks information about spawn count and ordering.

Every session maps to exactly one spawn. A spawn may have zero or one sessions (spawns created through the CLI have no session; spawns created through the app always have one).

## Session ID Format

8-character lowercase hexadecimal string, generated via `secrets.token_hex(4)`.

Examples: `a7f3b2c1`, `0e9d4f8a`, `b3c71e50`

This gives 2^32 (~4.3 billion) possible IDs — far more than a local dev tool will ever generate. The format is URL-safe, case-insensitive, and trivially generated without external dependencies.

## Storage

### On-disk: `.meridian/app/sessions.jsonl`

Append-only JSONL file. Each line records one session creation:

```json
{"session_id": "a7f3b2c1", "spawn_id": "p42", "harness": "claude", "model": "claude-opus-4-6", "created_at": "2026-04-09T14:30:00Z"}
```

Fields:
- `session_id` — the random session ID
- `spawn_id` — the spawn this session maps to
- `harness` — harness used (denormalized for fast listing)
- `model` — model used, if known (denormalized)
- `created_at` — ISO 8601 timestamp

This file is the source of truth for session-to-spawn mappings. It's loaded on server start to rebuild the in-memory lookup.

No update or delete events are needed. Sessions are immutable — the spawn behind them has its own lifecycle tracked in `spawns.jsonl`.

### In-memory: `SessionRegistry`

```python
@dataclass
class AppSessionEntry:
    session_id: str
    spawn_id: SpawnId
    harness: str
    model: str | None
    created_at: str

class AppSessionRegistry:
    def __init__(self, state_root: Path):
        self._state_root = state_root
        self._sessions: dict[str, SessionEntry] = {}  # session_id → entry
        self._spawn_to_session: dict[SpawnId, str] = {}  # spawn_id → session_id
        self._load()
    
    def _load(self) -> None:
        """Load session mappings from .meridian/app/sessions.jsonl"""
    
    def create(self, spawn_id: SpawnId, harness: str, model: str | None) -> str:
        """Create a new session, persist it, return session_id."""
    
    def get(self, session_id: str) -> SessionEntry | None:
        """Look up a session by ID."""
    
    def get_by_spawn(self, spawn_id: SpawnId) -> SessionEntry | None:
        """Look up a session by its spawn ID."""
    
    def list_all(self) -> list[SessionEntry]:
        """Return all sessions, ordered by creation time."""
```

The registry is instantiated once per server and shared across all request handlers via `app.state`. The class lives in `src/meridian/lib/app/session_registry.py` — it's an app-layer concern (URL-addressable aliases), not a state-layer concern like `spawn_store`.

### Collision Handling

If `secrets.token_hex(4)` generates a duplicate (astronomically unlikely), the `create()` method retries with a new random ID, up to 5 attempts. On failure (implies a broken random source), it raises an error.

## Session API

The session API is the primary interface for the frontend. It wraps the existing spawn infrastructure with session-level addressing.

### `POST /api/sessions` — Create Session

Request:
```json
{
  "harness": "claude",
  "prompt": "Implement the auth middleware...",
  "model": "claude-opus-4-6",
  "agent": null
}
```

Same fields as the existing `POST /api/spawns`.

Response:
```json
{
  "session_id": "a7f3b2c1",
  "spawn_id": "p42",
  "harness": "claude",
  "state": "connected",
  "capabilities": {
    "midTurnInjection": "queue",
    "supportsSteer": true,
    "supportsInterrupt": true,
    "supportsCancel": true,
    "runtimeModelSwitch": false,
    "structuredReasoning": true
  }
}
```

Internally:
1. Check draining flag — reject with 503 if server is shutting down
2. Create spawn via existing `reserve_spawn_id()` + `SpawnManager.start_spawn()`
3. Create session via `AppSessionRegistry.create(spawn_id, ...)`
4. Return combined response with session_id

**Failure compensation:** If step 3 fails (session JSONL write error), the spawn from step 2 is already running with no session mapping. The handler calls `SpawnManager.stop_spawn()` to cancel the orphaned spawn and returns 500 to the client. This ensures no spawn runs without a session URL to reach it through.

### `GET /api/sessions` — List Sessions

Response:
```json
[
  {
    "session_id": "a7f3b2c1",
    "spawn_id": "p42",
    "harness": "claude",
    "model": "claude-opus-4-6",
    "status": "running",
    "created_at": "2026-04-09T14:30:00Z",
    "prompt": "Implement the auth middleware..."
  },
  {
    "session_id": "0e9d4f8a",
    "spawn_id": "p41",
    "harness": "codex",
    "model": null,
    "status": "succeeded",
    "created_at": "2026-04-09T14:20:00Z",
    "prompt": "Fix the login bug..."
  }
]
```

Joins session registry data with spawn store data. The `status` field comes from the spawn record (via `spawn_store.get_spawn()`). The `prompt` field is truncated if long.

Sessions are returned in reverse chronological order (newest first).

### `GET /api/sessions/{session_id}` — Get Session

Response:
```json
{
  "session_id": "a7f3b2c1",
  "spawn_id": "p42",
  "harness": "claude",
  "model": "claude-opus-4-6",
  "status": "running",
  "created_at": "2026-04-09T14:30:00Z",
  "prompt": "Implement the auth middleware...",
  "capabilities": { ... }
}
```

If the spawn is active, capabilities are populated from the live connection. If the spawn is completed, capabilities may be null.

Returns 404 if session_id is not found.

### `DELETE /api/sessions/{session_id}` — Cancel Session

Cancels the spawn behind the session. Delegates to `SpawnManager.cancel()`.

Returns `{"ok": true}` on success, 404 if session not found, 400 if spawn is already terminated.

### `POST /api/sessions/{session_id}/inject` — Inject Message

Request:
```json
{"text": "Try a different approach..."}
```

Delegates to `SpawnManager.inject()` using the session's spawn_id.

### `WS /api/sessions/{session_id}/ws` — Stream Events

WebSocket endpoint. Resolves session_id → spawn_id, then delegates to the existing `spawn_websocket()` function.

The WebSocket protocol (AG-UI events, control messages) is identical to the existing `/api/spawns/{spawn_id}/ws` endpoint. The only difference is the addressing — session_id instead of spawn_id.

Origin validation and subscriber management work the same way.

## Session Lifecycle

### Creation

A session is created when the user clicks "Start Spawn" on the dashboard. The `POST /api/sessions` endpoint creates both the spawn and the session atomically.

### Active

While the spawn is running, the session is "active." The browser connects via WebSocket and streams events in real-time. Multiple browser tabs can navigate to the same session URL, but only one tab gets the live WebSocket stream (existing subscriber-exclusivity from `SpawnManager.subscribe()`).

### Completed

When the spawn finishes (succeeded, failed, cancelled), the session remains navigable. On page load:

1. `GET /api/sessions/{session_id}` returns the session with terminal status.
2. The frontend shows the terminal state without attempting WebSocket connection.
3. Future enhancement: replay events from `output.jsonl` for completed sessions.

### Server Restart

After a server restart, the `SessionRegistry` reloads from `.meridian/app/sessions.jsonl`. Bookmarked session URLs continue to work:

- If the spawn is still "running" in spawn store (stale — server crashed), the session shows the last known state.
- If the spawn is terminal, the session shows the terminal state.
- Live streaming is only available for spawns started in the current server process (they need active `SpawnManager` sessions).

## Boundary: What Sessions Don't Do

- Sessions don't replace spawn_id as the internal identifier — SpawnManager, spawn_store, and all internal systems continue to use spawn_id.
- Sessions don't create a new state store — spawn state lives in `spawns.jsonl`, session state is a thin mapping on top.
- Sessions don't support "connecting to an existing CLI spawn" in this version. That's a future feature that would add a `POST /api/sessions/attach` endpoint.
