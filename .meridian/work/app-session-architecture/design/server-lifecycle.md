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

```
1. Resolve repo_root for current directory
2. Read .meridian/app/server.json
   ├── File exists → validate server
   │   ├── PID alive AND GET /api/health succeeds
   │   │   → Print "Server already running at http://host:port"
   │   │   → Open browser to existing URL (unless --no-browser)
   │   │   → Exit 0
   │   └── PID dead OR health check fails
   │       → Delete stale lockfile
   │       → Delete stale user-level registry entry
   │       → Continue to step 3
   └── File missing → continue to step 3
3. Select port
   ├── --port flag provided → use that port (fail if taken)
   └── No --port flag → probe starting from 8420
       → Try 8420, 8421, ..., 8429
       → Use first available port
       → Fail if none available in range
4. Write lockfile (.meridian/app/server.json)
5. Write user-level registry entry (~/.meridian/app/servers/<hash>.json)
6. Start uvicorn server
7. Open browser (unless --no-browser)
```

### Port Selection

Port probing uses a TCP socket bind test:

```python
def find_available_port(host: str, start: int = 8420, count: int = 10) -> int:
    for port in range(start, start + count):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No available port in range {start}-{start + count - 1}")
```

When `--port` is explicitly provided, no probing occurs — the server attempts to bind on that exact port and fails with a clear error if it's taken.

### Lockfile Write Ordering

The lockfile is written BEFORE starting uvicorn, using the selected port. There's a theoretical race between port probing and uvicorn binding, but for a local dev tool this is negligible. If uvicorn fails to bind (port taken in the interim), the lockfile is cleaned up and the error propagates.

## Shutdown Flow

### Clean shutdown (Ctrl-C / SIGTERM)

```
1. uvicorn receives signal
2. FastAPI lifespan __aexit__ fires
3. SpawnManager.shutdown() stops all active spawn connections
4. Delete .meridian/app/server.json
5. Delete ~/.meridian/app/servers/<hash>.json
6. Process exits
```

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

**Two users/terminals run `meridian app` for the same repo simultaneously.** The second invocation finds the lockfile, validates it, and opens the browser to the existing server. No conflict.

**Server crashes while spawns are running.** Spawn state is already persisted to `output.jsonl` and `spawns.jsonl` by the drain loop. On next server start, the spawn store shows them in their last recorded state. Active WebSocket connections from the browser break — the frontend shows "disconnected" status.

**User deletes `.meridian/app/` while server is running.** The server continues running with in-memory state. On next `meridian app` from another terminal, the missing lockfile causes a new server to start on the next available port. The old server is orphaned until killed. This is an edge case that doesn't need special handling — deleting state files while the process is running is user error.

**Lockfile points to wrong port (manual edit or corruption).** Health check fails, lockfile is treated as stale, cleaned up, and a new server starts. Crash-only design handles this automatically.

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
