# Server Lifecycle

## One Server Per Machine

The entire machine gets at most one `meridian app` server process. The server binds to a port, serves the web UI, and manages spawn connections across all repos. Any `meridian app` invocation from any repo either starts the global server or opens the browser to the existing instance.

This is the Jupyter model — one dashboard at localhost:8420 showing everything.

## State Files

### User-Level Lockfile: `~/.meridian/app/server.json`

Written atomically on server start, deleted on clean shutdown. Contains everything needed to reconnect to or validate the running server.

```json
{
  "pid": 12345,
  "port": 8420,
  "host": "127.0.0.1",
  "started_at": "2026-04-09T14:30:00Z"
}
```

This answers: "Is there already a server running on this machine, and how do I reach it?"

No `repo_root` or `project_key` field — the server is machine-scoped, not project-scoped. Sessions carry project/workspace context.

### No Server Registry Directory

With a single-server model, `~/.meridian/app/servers/` is unnecessary. There is at most one server, tracked by one lockfile. `meridian app list` reads the single lockfile.

## Startup Flow (`meridian app`)

The startup flow is serialized under `~/.meridian/app/server.flock` to prevent concurrent starts from racing. The lock is held from stale-check through bind + lockfile write, then released before the server begins serving requests.

```text
0. Ensure ~/.meridian/app/ exists
1. Acquire flock on ~/.meridian/app/server.flock
2. Read ~/.meridian/app/server.json
   - If PID alive: open existing server and exit
   - If PID dead: delete stale lockfile and continue
3. Bind listening socket
4. Write ~/.meridian/app/server.json
5. Release startup flock
6. Start uvicorn using the pre-bound socket
7. Open browser unless --no-browser
```

If flock acquisition times out, print an error suggesting another `meridian app` is starting and exit.

### Stale Server Detection

A lockfile is stale if and only if the PID is dead (`os.kill(pid, 0)` raises `ProcessLookupError`). If the PID is alive, the server is considered running even if the health check fails — it may still be in the startup window.

### Port Selection — Bind and Hold

To avoid a race between port probing and uvicorn binding, startup binds the socket first and hands that file descriptor to uvicorn. This removes the gap where the lockfile names a port that is not yet owned.

## Shutdown Flow

### Clean Shutdown

```text
1. uvicorn receives signal
2. FastAPI lifespan shutdown begins
3. Set draining flag — reject new POST /api/sessions
4. Wait for in-flight session-creation requests to finish (10s safety timeout)
5. SpawnManager.shutdown() stops active harness connections
6. Delete ~/.meridian/app/server.json
7. Exit
```

### Crash

If the process is killed, the lockfile remains. The next startup detects the dead PID, deletes the stale file, and proceeds. Recovery is startup behavior.

## Server Discovery (`meridian app list`)

With a single-server model, discovery is simple:

```text
1. Read ~/.meridian/app/server.json
2. If missing: "No server running"
3. If PID dead: delete stale file, "No server running"
4. If PID alive: optionally probe /api/health and print status
```

## Server Stop (`meridian app stop`)

```text
1. Read ~/.meridian/app/server.json
2. If missing or stale: report no server running
3. Send SIGTERM
4. Wait up to 5s
5. If still alive: SIGKILL
6. Clean up lockfile if still present
```

## Health Endpoint

`GET /api/health` returns server identity and status:

```json
{
  "status": "ok",
  "port": 8420,
  "host": "127.0.0.1",
  "pid": 12345,
  "active_sessions": 5,
  "active_spawns": 3,
  "projects": ["project-alpha", "project-beta", "lib-core"],
  "uptime_secs": 123.4
}
```

This endpoint is unauthenticated even when future `--host` auth exists, so discovery probes can still reach it.

## Edge Cases

**Two terminals run `meridian app` simultaneously.** The startup flock serializes them. The first process writes the lockfile; the second finds it and opens the existing server.

**Server crashes while spawns are running.** Spawn state is already persisted to `~/.meridian/projects/<project_key>/spawns.jsonl` and `~/.meridian/projects/<project_key>/spawns/<spawn_id>/...`. On next start, the project-scoped spawn store shows the last recorded state. Browser WebSocket connections break and the frontend shows disconnected status.

**User deletes `~/.meridian/app/` while the server is running.** The server keeps running in memory. A later `meridian app` may start a second server because the lockfile is gone. This is user-induced state corruption and does not need special recovery logic.

**Lockfile points to the wrong port.** If the PID is still alive, the server is treated as running and the client opens the lockfile URL. This is manual corruption of state files; the recovery path is `meridian app stop` and restart.

**Repo is deleted while sessions reference it.** The session still resolves because session metadata and spawn state are keyed by `project_key`, not by the raw path. The server can still read status from `~/.meridian/projects/<project_key>/...`. Operations that need the workspace path should fail with a repo-unavailable error.

**Two spawns from different repos have the same spawn_id.** This is expected. Spawn IDs are project-scoped, not globally unique across the machine. The active-session key is `(project_key, spawn_id)`, and session IDs remain globally unique URL aliases.

## File Layout

```text
~/.meridian/
  app/
    server.json           # Server lockfile
    server.flock          # Startup serialization flock
    sessions.jsonl        # Session registry: session_id → project_key/spawn_id/repo_root
  projects/
    <project_key>/
      spawns.jsonl        # Project-scoped spawn store
      spawns.jsonl.flock  # Spawn-store lock
      spawns/
        <spawn_id>/
          output.jsonl
          inbound.jsonl
          control.sock
          harness.pid
          heartbeat
          report.md
          home/
          config/
```

The `~/.meridian/app/` directory is created on first `meridian app` invocation. Each `~/.meridian/projects/<project_key>/` directory is created on first spawn for that project.

Runtime directories are keyed only by `project_key` and `spawn_id`. Neither app `session_id` nor harness `chat_id` creates its own filesystem taxonomy.
