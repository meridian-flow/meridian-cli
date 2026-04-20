# Session Registry

## What a Session Is

A session is a metadata layer — a URL-addressable alias for a spawn in a specific project workspace. It maps a random, globally unique ID to a `(project_key, spawn_id, repo_root, work_id)` tuple.

This indirection exists because:

1. **Spawn IDs are sequential and predictable** (`p1`, `p2`, ...) — unsuitable for URLs that might be shared or bookmarked.
2. **Spawn IDs are only unique within a project** — with a single server handling multiple repos, session IDs must be globally unambiguous across all projects.
3. **URLs should be opaque** — exposing spawn IDs in URLs leaks information about spawn count and ordering.

Every session maps to exactly one spawn in one project. A spawn may have zero or one sessions (spawns created through the CLI have no session; spawns created through the app always have one).

### Sessions and Work Items

Sessions can optionally be attached to a work item. Work attachment is **nullable** — sessions can exist without work (quick exploration) and can be attached to work later.

```
Session (session_id)
  ├── project_key, spawn_id, repo_root  — always present
  └── work_id [nullable]                — optional work attachment
```

Work attachment on sessions reflects the underlying `chat_id → work_id` mapping in the session store. The app session registry denormalizes this for display.

### Sessions Are Metadata, Not Storage Boundaries

Sessions do not define runtime directory structure. Runtime state is keyed by `project_key` and `spawn_id`, not `session_id`:

```text
~/.meridian/projects/<project_key>/spawns/<spawn_id>/    # YES
~/.meridian/projects/<project_key>/sessions/<session_id>/  # NO
```

Similarly, `chat_id` is harness-level resumable-session metadata for continuations, not a storage key. Two spawns in the same resumable chat still get two runtime directories if they are separate Meridian runs.

### Primary Sessions Have Spawn IDs

"Primary sessions" — spawns launched through the app UI rather than the CLI — also have Meridian `spawn_id`s. The app creates a spawn via `reserve_spawn_id()` just like CLI spawns, then associates a session ID with it. There is no separate app-session run identity.

## Session ID Format

8-character lowercase hexadecimal string, generated via `secrets.token_hex(4)`.

Examples: `a7f3b2c1`, `0e9d4f8a`, `b3c71e50`

This gives 2^32 (~4.3 billion) possible IDs — far more than a local dev tool will ever generate. The format is URL-safe, case-insensitive, and trivially generated without external dependencies.

## Storage

### On-Disk Session Registry: `~/.meridian/app/sessions.jsonl`

User-level, append-only JSONL. Each line records one session creation:

```json
{"session_id": "a7f3b2c1", "project_key": "3f8a2b1c9d4e", "spawn_id": "p42", "repo_root": "/home/user/project-alpha", "work_id": "auth-middleware", "harness": "claude", "model": "claude-opus-4-6", "created_at": "2026-04-09T14:30:00Z"}
```

Fields:

- `session_id` — random URL-safe session identifier
- `project_key` — stable project-scoped Meridian namespace
- `spawn_id` — Meridian run identifier, unique within the project
- `repo_root` — workspace root for harness launch and UI display
- `work_id` — attached work item slug (nullable)
- `harness` — harness used (denormalized for listing)
- `model` — model used, if known (denormalized)
- `created_at` — ISO 8601 timestamp

`project_key` is what lets the server find project-scoped spawn records and runtime artifacts under `~/.meridian/projects/<project_key>/...`. `repo_root` is retained because the harness still needs a concrete workspace root and the dashboard still benefits from showing the actual repo path. `work_id` is denormalized from the session store for efficient listing.

This file is the source of truth for session-to-spawn mappings. It is loaded on server start to rebuild the in-memory registry.

**Update events:** Sessions support update events for work attachment changes:

```json
{"event": "update", "session_id": "a7f3b2c1", "work_id": "auth-middleware", "updated_at": "2026-04-09T15:00:00Z"}
```

### In-Memory Registry: `AppSessionRegistry`

```python
ProjectKey = str

@dataclass
class AppSessionEntry:
    session_id: str
    project_key: ProjectKey
    spawn_id: SpawnId
    repo_root: Path
    work_id: str | None
    harness: str
    model: str | None
    created_at: str

class AppSessionRegistry:
    def __init__(self, app_state_dir: Path):
        self._app_state_dir = app_state_dir  # ~/.meridian/app/
        self._sessions: dict[str, AppSessionEntry] = {}
        self._spawn_to_session: dict[tuple[ProjectKey, SpawnId], str] = {}
        self._work_to_sessions: dict[str, set[str]] = {}  # work_id -> session_ids
        self._load()

    def create(
        self,
        spawn_id: SpawnId,
        project_key: ProjectKey,
        repo_root: Path,
        harness: str,
        model: str | None,
        work_id: str | None = None,
    ) -> str:
        """Create a new session, persist it, return session_id."""

    def attach_work(self, session_id: str, work_id: str) -> None:
        """Attach a session to a work item."""

    def detach_work(self, session_id: str) -> None:
        """Detach a session from its work item."""

    def get(self, session_id: str) -> AppSessionEntry | None:
        """Look up a session by ID."""

    def get_by_spawn(
        self, project_key: ProjectKey, spawn_id: SpawnId
    ) -> AppSessionEntry | None:
        """Look up a session by its project + spawn ID."""

    def list_all(self) -> list[AppSessionEntry]:
        """Return all sessions, ordered by creation time."""

    def list_by_work(self, work_id: str) -> list[AppSessionEntry]:
        """Return sessions attached to a work item."""

    def list_unattached(self) -> list[AppSessionEntry]:
        """Return sessions not attached to any work item."""
```

Key properties:

- The registry is keyed by `session_id` for external lookup.
- The reverse lookup is keyed by `(project_key, spawn_id)` because that is the true internal run identity.
- Work-to-sessions index enables efficient work-scoped queries.
- Both `project_key` and `repo_root` are stored — `project_key` for runtime/spawn state, `repo_root` for workspace shaping and display.

The registry is instantiated once per server and shared across request handlers via `app.state`. It is an app-layer concern, not the primary spawn-state store.

### Collision Handling

If `secrets.token_hex(4)` generates a duplicate (astronomically unlikely), `create()` retries with a new random ID up to 5 attempts. On failure it raises an error.

## Session API

The session API is the primary frontend interface. It wraps the existing spawn machinery with session-level addressing.

### `POST /api/sessions` — Create Session

Request:

```json
{
  "harness": "claude",
  "prompt": "Implement the auth middleware...",
  "model": "claude-opus-4-6",
  "agent": null,
  "repo_root": "/home/user/project-alpha",
  "work_id": "auth-middleware"
}
```

`repo_root` is required. The server has no default repo. The CLI resolves it from `cwd`; the frontend includes it from repo context.

`work_id` is optional. If provided, the session is attached to that work item. If omitted, the session is unattached (quick exploration).

Validation:

- `repo_root` must be an absolute path
- `repo_root` must exist as a directory
- `repo_root` must identify a Meridian-enabled project
- If `work_id` is provided, it must exist as a work item in that repo

Response:

```json
{
  "session_id": "a7f3b2c1",
  "project_key": "3f8a2b1c9d4e",
  "spawn_id": "p42",
  "repo_root": "/home/user/project-alpha",
  "work_id": "auth-middleware",
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

1. Check draining flag — reject with 503 if the server is shutting down.
2. Resolve `project_key` from `repo_root`. See [project-key.md](project-key.md).
3. Reserve the spawn in `~/.meridian/projects/<project_key>/spawns.jsonl`.
4. Create runtime directories under `~/.meridian/projects/<project_key>/spawns/<spawn_id>/`.
5. Start the harness using `repo_root` for workspace shaping.
6. Create the session via `AppSessionRegistry.create(...)` with optional `work_id`.
7. Return the combined response.

**Failure compensation:** If step 6 fails (session JSONL write error), the spawn from steps 3-5 is already running with no session mapping. The handler cancels the orphaned spawn and returns 500. This ensures no app-created spawn is left running without a session URL.

### `GET /api/sessions` — List Sessions

Query params:

- `repo_root` (optional) — filter to sessions from one repo
- `work_id` (optional) — filter to sessions attached to a work item
- `unattached` (optional, boolean) — filter to sessions not attached to any work

Response:

```json
[
  {
    "session_id": "a7f3b2c1",
    "project_key": "3f8a2b1c9d4e",
    "spawn_id": "p42",
    "repo_root": "/home/user/project-alpha",
    "repo_name": "project-alpha",
    "work_id": "auth-middleware",
    "harness": "claude",
    "model": "claude-opus-4-6",
    "status": "running",
    "created_at": "2026-04-09T14:30:00Z",
    "prompt": "Implement the auth middleware..."
  }
]
```

The list endpoint joins session-registry data with the project-scoped spawn store at `~/.meridian/projects/<project_key>/spawns.jsonl`. `repo_name` is derived from the last path component of `repo_root`. `prompt` is truncated if long.

Sessions are returned in reverse chronological order (newest first).

**Repo unavailability:** If `repo_root` no longer exists, the session still appears because the session registry and spawn records are keyed by `project_key`, not by the raw path. Status lookup still works. Workspace-dependent actions should return a repo-unavailable error.

### `GET /api/sessions/{session_id}` — Get Session

Response:

```json
{
  "session_id": "a7f3b2c1",
  "project_key": "3f8a2b1c9d4e",
  "spawn_id": "p42",
  "repo_root": "/home/user/project-alpha",
  "repo_name": "project-alpha",
  "work_id": "auth-middleware",
  "harness": "claude",
  "model": "claude-opus-4-6",
  "status": "running",
  "created_at": "2026-04-09T14:30:00Z",
  "prompt": "Implement the auth middleware...",
  "capabilities": { "...": "..." }
}
```

If the spawn is active, capabilities come from the live connection. If the spawn is completed, capabilities may be null.

Returns 404 if `session_id` is not found.

### `GET /api/sessions/{session_id}/tree` — Get Spawn Tree

Returns the spawn tree for this session, built from `parent_id` relationships.

Response:

```json
{
  "session_id": "a7f3b2c1",
  "root_spawn_id": "p42",
  "spawns": [
    {
      "spawn_id": "p42",
      "parent_id": null,
      "status": "running",
      "agent": "dev-orchestrator",
      "desc": "Implement auth middleware",
      "children": ["p43", "p44"]
    },
    {
      "spawn_id": "p43",
      "parent_id": "p42",
      "status": "succeeded",
      "agent": "coder",
      "desc": "Implement token validation",
      "children": []
    },
    {
      "spawn_id": "p44",
      "parent_id": "p42",
      "status": "running",
      "agent": "reviewer",
      "desc": "Review implementation",
      "children": []
    }
  ]
}
```

The tree is built by querying spawns where `chat_id` matches the session's chat, then constructing the tree from `parent_id` relationships.

### `PATCH /api/sessions/{session_id}` — Update Session

Update session metadata, primarily work attachment.

Request:

```json
{"work_id": "auth-middleware"}
```

Or to detach:

```json
{"work_id": null}
```

Response:

```json
{"ok": true, "session_id": "a7f3b2c1", "work_id": "auth-middleware"}
```

### `DELETE /api/sessions/{session_id}` — Cancel Session

Cancels the spawn behind the session. Delegates to `SpawnManager.cancel()` using `(project_key, spawn_id)`.

Returns `{"ok": true}` on success, 404 if the session is not found, 400 if the spawn is already terminated.

### `POST /api/sessions/{session_id}/inject` — Inject Message

Request:

```json
{"text": "Try a different approach..."}
```

Delegates to `SpawnManager.inject()` using the session's `(project_key, spawn_id)`.

### `WS /api/sessions/{session_id}/ws` — Stream Events

WebSocket endpoint. Resolves `session_id` to `(project_key, spawn_id)` and delegates to the existing spawn-streaming path.

The protocol is identical to the existing `/api/spawns/{spawn_id}/ws` endpoint. The only difference is the addressing layer — `session_id` instead of direct `spawn_id`.

Origin validation and subscriber management work the same way.

## SpawnManager — Project-Scoped Runtime, Repo-Scoped Workspace

The SpawnManager changes to support spawns from multiple repos in one server while keeping runtime state keyed by `project_key`.

### Constructor Change

```python
# Before (per-repo):
class SpawnManager:
    def __init__(self, state_root: Path, repo_root: Path):
        self._state_root = state_root
        self._repo_root = repo_root

# After:
class SpawnManager:
    def __init__(self) -> None:
        self._sessions: dict[SpawnKey, SpawnSession] = {}
```

### Per-Spawn Session State

```python
ProjectKey = str
SpawnKey = tuple[ProjectKey, SpawnId]

@dataclass
class SpawnSession:
    connection: HarnessConnection
    drain_task: asyncio.Task[None]
    subscriber: asyncio.Queue[HarnessEvent | None] | None
    control_server: ControlSocketServer
    started_monotonic: float
    project_key: ProjectKey
    repo_root: Path
```

`project_key` identifies the project-scoped Meridian runtime root. `repo_root` identifies the workspace root the harness should operate in.

Path helpers become project-keyed:

```python
def _spawn_dir(self, spawn_key: SpawnKey) -> Path:
    project_key, spawn_id = spawn_key
    return Path.home() / ".meridian" / "projects" / project_key / "spawns" / str(spawn_id)
```

The same pattern applies to `output.jsonl`, `inbound.jsonl`, `control.sock`, and projected config/home paths.

### `spawn_store` Calls

The spawn store becomes project-scoped:

```python
def _project_state_root(project_key: ProjectKey) -> Path:
    return Path.home() / ".meridian" / "projects" / project_key

spawn_store.reserve_spawn_id(_project_state_root(project_key))
spawn_store.finalize_spawn(_project_state_root(project_key), spawn_id, ...)
```

This keeps the spawn counter and the per-spawn runtime directories in the same namespace. It avoids collisions when multiple checkouts of the same logical project share the same `project_key`.

### `server.py` Changes

In the multi-repo model:

- `SpawnManager()` is constructed with no path arguments.
- `project_key` is resolved once from `repo_root`.
- `reserve_spawn_id()` and other spawn-store calls use the project-scoped state root.
- `ConnectionConfig` carries `repo_root` for workspace shaping.

### Spawn ID Uniqueness

Spawn IDs are unique within one `project_key` namespace, not across the entire machine. The compound key for active sessions is therefore:

```python
SpawnKey = tuple[ProjectKey, SpawnId]
```

The session layer resolves `session_id` to that compound key plus the `repo_root` needed for workspace shaping.

## Session Lifecycle

### Creation

A session is created when the user clicks "Start Spawn". `POST /api/sessions` creates both the spawn and the session atomically enough for app use. The user can optionally specify a `work_id` to attach the session to a work item.

### Active

While the spawn is running, the session is active. The browser connects via WebSocket and streams events in real time. Multiple tabs can navigate to the same session URL, but only one tab gets the live stream (existing subscriber exclusivity).

### Work Attachment

At any point, the user can attach or detach a session from a work item via `PATCH /api/sessions/{session_id}`. This updates both the app session registry and the underlying session store's `active_work_id`.

### Completed

When the spawn finishes, the session remains navigable:

1. `GET /api/sessions/{session_id}` returns metadata and terminal status.
2. The frontend shows the terminal state without attempting a live WebSocket connection.
3. Future enhancement: replay events from `output.jsonl` for completed sessions.

### Server Restart

After a server restart, the `AppSessionRegistry` reloads from `~/.meridian/app/sessions.jsonl`. Bookmarked session URLs continue to work:

- If the spawn was still running and the server died, the session shows the last known state from the project spawn store.
- If the spawn is terminal, the session shows the terminal state.
- Live streaming is only available for spawns started in the current process.

## Boundary: What Sessions Don't Do

- Sessions do not replace `spawn_id` as the Meridian run identity.
- Sessions do not create a session-scoped or chat-scoped runtime taxonomy.
- Sessions do not replace `repo_root` as the workspace selector.
- Sessions do not support "attach to an existing CLI spawn" in this version. That would be a future `POST /api/sessions/attach` flow.
