# Server Lifecycle

## One Server Per Repo

Each repo gets at most one `meridian app` server process. The server binds to a port, serves the web UI, and manages spawn connections for that repo's `.meridian/` state root.

## State Files

### Repo-level lockfile: `.meridian/app/server.json`

Written atomically on server start, deleted on clean shutdown. Contains everything needed to reconnect to or validate a running server.

```json
{
  "pid": 12345,
  "port": 8420,
  "host": "127.0.0.1",
  "repo_root": "/home/user/project",
  "started_at": "2026-04-09T14:30:00Z"
}
```

This file answers: "is there already a server for this repo, and how do I reach it?"

### User-level server registry: `~/.meridian/app/servers/`

One JSON file per running server, named `<hex12>.json` where `hex12` is the first 12 characters of the SHA-256 hash of the absolute repo_root path. Written atomically on server start, deleted on clean shutdown.

File contents are identical to the repo-level lockfile.

This directory answers: "what servers are running across all my repos?"

Example:
```
~/.meridian/app/servers/
  a1b2c3d4e5f6.json    # /home/user/project-alpha (port 8420)
  7890abcdef01.json    # /home/user/project-beta (port 8421)
```

## Startup Flow (`meridian app`)

The entire startup flow is serialized under a file lock (`.meridian/app/server.flock`) to prevent two concurrent `meridian app` invocations from racing on the same repo. The lock is held from step 1 through step 6 (server bind), then released — the running server doesn't hold the lock after startup completes.

```
0. Acquire flock on .meridian/app/server.flock (blocking, with 10s timeout)
1. Resolve repo_root for current directory
2. Read .meridian/app/server.json
   ├── File exists → validate server
   │   ├── PID alive AND GET /api/health succeeds
   │   │   → Release flock
   │   │   → Print "Server already running at http://host:port"
   │   │   → Open browser to existing URL (unless --no-browser)
   │   │   → Exit 0
   │   └── PID dead OR health check fails
   │       → Delete stale lockfile
   │       → Delete stale user-level registry entry
   │       → Continue to step 3
   └── File missing → continue to step 3
3. Select port (bind-and-hold: see Port Selection below)
4. Write lockfile (.meridian/app/server.json) with actual bound port
5. Write user-level registry entry (~/.meridian/app/servers/<hash>.json)
6. Release startup flock
7. Start uvicorn server (using the pre-bound socket)
8. Open browser (unless --no-browser)
```

If flock acquisition times out (10 seconds), print an error suggesting another `meridian app` instance is starting and exit.

### Port Selection — Bind-and-Hold

To eliminate the race between port probing and uvicorn binding, the startup flow binds a TCP socket and holds it open through lockfile creation:

```python
def bind_server_socket(host: str, port: int | None, start: int = 8420, count: int = 10) -> socket.socket:
    """Bind and return a listening socket. Caller owns the socket."""
    if port is not None:
        # Explicit --port: bind exactly, fail on error
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        return sock
    # Auto-port: probe range
    for p in range(start, start + count):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, p))
            return sock
        except OSError:
            sock.close()
            continue
    raise RuntimeError(f"No available port in range {start}-{start + count - 1}")
```

The bound socket's port is read via `sock.getsockname()[1]` and written to the lockfile. The socket is then passed to uvicorn as a file descriptor (via `uvicorn.Config(fd=sock.fileno())`), so there is no window where the port is unowned. If uvicorn startup fails, the socket is closed and the lockfile is cleaned up.

## Shutdown Flow

### Clean shutdown (Ctrl-C / SIGTERM)

```
1. uvicorn receives signal
2. FastAPI lifespan __aexit__ fires
3. Set draining flag — reject new POST /api/sessions with 503
4. Wait for in-flight session creation requests to complete (up to 5s)
5. SpawnManager.shutdown() stops all active spawn connections
6. Delete .meridian/app/server.json
7. Delete ~/.meridian/app/servers/<hash>.json
8. Process exits
```

The draining flag is an `asyncio.Event` checked at the top of `POST /api/sessions`. This prevents the race where a spawn is created during shutdown but before `SpawnManager.shutdown()` iterates `_sessions`.

### Crash (SIGKILL / OOM / power loss)

Lockfiles remain on disk. Next startup detects and cleans them via the PID-alive + health check validation in step 2 of the startup flow. This is crash-only design — recovery is startup behavior.

## Server Discovery (`meridian app list`)

```
1. Read all JSON files in ~/.meridian/app/servers/
2. For each file:
   a. Parse server metadata (pid, port, host, repo_root)
   b. Check if PID is alive (os.kill(pid, 0))
   c. If PID alive, try GET http://host:port/api/health
   d. If health check passes → server is live, include in output
   e. If PID dead or health check fails → stale entry, delete file
3. Print table of live servers:
   REPO                      PORT   URL
   /home/user/project-alpha  8420   http://127.0.0.1:8420
   /home/user/project-beta   8421   http://127.0.0.1:8421
```

If no servers are running, print a message indicating that.

## Server Stop (`meridian app stop`)

```
1. Determine target server:
   ├── No arguments → use current repo's .meridian/app/server.json
   ├── --port flag → find server on that port from user-level registry
   └── --repo flag → use that repo's .meridian/app/server.json
2. If no server found → print error, exit 1
3. Send SIGTERM to server PID
4. Wait up to 5 seconds for process to exit
5. If still alive after 5s → send SIGKILL
6. Clean up lockfile + registry entry if still present
```

## Health Endpoint

`GET /api/health` returns server identity and status:

```json
{
  "status": "ok",
  "repo_root": "/home/user/project",
  "repo_name": "project",
  "port": 8420,
  "host": "127.0.0.1",
  "pid": 12345,
  "active_sessions": 2,
  "active_spawns": 1,
  "uptime_secs": 123.4
}
```

This endpoint is unauthenticated (even when `--host` auth is added later) so that `meridian app list` can probe servers without a token.

## Edge Cases

**Two users/terminals run `meridian app` for the same repo simultaneously.** The startup flock serializes them. The first invocation acquires the lock, binds the port, writes the lockfile, and releases the lock. The second invocation acquires the lock, finds the lockfile, validates the running server, and opens the browser to the existing instance. If both arrive before any lockfile exists, the flock serializes them so only one starts a server.

**Server crashes while spawns are running.** Spawn state is already persisted to `output.jsonl` and `spawns.jsonl` by the drain loop. On next server start, the spawn store shows them in their last recorded state. Active WebSocket connections from the browser break — the frontend shows "disconnected" status.

**User deletes `.meridian/app/` while server is running.** The server continues running with in-memory state. On next `meridian app` from another terminal, the missing lockfile causes a new server to start on the next available port. The old server is orphaned until killed. This is an edge case that doesn't need special handling — deleting state files while the process is running is user error.

**Lockfile points to wrong port (manual edit or corruption).** Health check fails, lockfile is treated as stale, cleaned up, and a new server starts. Crash-only design handles this automatically.

**Crash between lockfile and registry write.** If the server crashes after writing `.meridian/app/server.json` but before writing `~/.meridian/app/servers/<hash>.json`, the repo-level lockfile exists but the user-level entry doesn't. `meridian app` for that repo still works (reads the repo-level lockfile). `meridian app list` won't show the server — it reads the user-level registry. Reconciliation rule: `meridian app list` also checks the current repo's lockfile (if running from a repo) and includes it if valid. This handles the "missing registry entry" case without adding complexity.

**Orphan registry entry (repo lockfile deleted, registry entry remains).** `meridian app list` validates each registry entry with PID + health check. An orphan entry fails validation and is deleted. No special repair logic needed.

### Authoritative files

- **`meridian app` (for current repo)**: `.meridian/app/server.json` is authoritative. It's the primary check for "is there a server for this repo."
- **`meridian app list` (cross-repo discovery)**: `~/.meridian/app/servers/` is the primary index. Reconciled with PID + health check on each read.
- **`meridian app stop`**: reads the authoritative file for the target repo (lockfile), falls back to registry if `--port` is used.

## File Layout

```
.meridian/
  app/
    server.json           # Server lockfile (runtime only, not tracked)
    sessions.jsonl        # Session registry (see session-registry.md)

~/.meridian/
  app/
    servers/
      <hash>.json         # One file per running server across all repos
```

The `.meridian/app/` directory is created on first `meridian app` invocation. It's automatically covered by the existing `.meridian/.gitignore` (`*` ignores everything not explicitly tracked).
