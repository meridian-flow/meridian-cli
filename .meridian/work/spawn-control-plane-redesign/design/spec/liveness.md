# Liveness — One Reaper Contract Across Surfaces

The reaper trusts a single signal: there is a process tagged as the
**spawn host** (recorded in `runner_pid`) and that process is alive **and** is
keeping a heartbeat fresh. Both halves are required; either half alone is
ambiguous. There is one contract; CLI- and app-launched spawns satisfy it
the same way.

## EARS Statements

### LIV-001 — Every active spawn has a non-null `runner_pid`

**When** any code path transitions a `SpawnRecord` to status `running`,
**the writer shall** populate `runner_pid` with the PID of the process that
owns the live harness connection (CLI runner for streaming-serve, FastAPI
worker for app spawns, in-process orchestrator for any future surface).

**Observable.** No `SpawnRecord` row ever has `status="running"` and
`runner_pid is None` simultaneously. Unit test reads every event in
`spawns.jsonl` and asserts the invariant per state transition.

### LIV-002 — The owning process keeps `heartbeat` fresh

**When** a process is the registered `runner_pid` for one or more active
spawns,
**that process shall** touch each spawn's `heartbeat` artifact at least
every `_HEARTBEAT_INTERVAL_SECS` (currently 30s) for the lifetime of the
spawn's connection.

**Observable.** `heartbeat` mtime advances continuously while the spawn is
running. The recent-activity check in `reaper._recent_runner_activity`
returns `("heartbeat", mtime)` within the heartbeat window for any
non-stopped spawn.

### LIV-003 — Heartbeat ownership lives in `SpawnManager`

**When** `SpawnManager.start_spawn` registers a new session,
**the manager shall** start a per-session asyncio heartbeat task that
performs LIV-002 for that spawn until the session is torn down.

**Observable.** A per-session heartbeat task is created in
`SpawnManager.start_spawn` and cancelled in `_cleanup_completed_session` /
`stop_spawn`. The legacy `_run_heartbeat_task` in `runner.py` and
`streaming_runner.py` is removed; ownership lives in exactly one place.

### LIV-004 — Reaper never finalizes while heartbeat is fresh

**When** `decide_reconciliation` runs against a `SpawnRecord` with
`status in {"running", "queued"}` and the heartbeat is fresh inside
`_HEARTBEAT_WINDOW_SECS`,
**the reaper shall** return `Skip(reason="recent_activity")` regardless of
`runner_pid_alive`, regardless of `runner_pid is None`, and regardless of
startup grace.

**Observable.** Existing rule, preserved. The fix to LIV-001 ensures
`runner_pid` is always present so the alive-check can run as a secondary
defence-in-depth.

### LIV-005 — App-managed spawn finalize is single-writer

**When** the FastAPI worker observes its `SpawnManager` `wait_for_completion`
resolve (background-finalize task),
**the app shall** finalize the spawn store with `origin="launcher"` exactly
once and **shall not** race with the runner (because the app **is** the
runner for this surface).

**Observable.** No double-finalize for app-launched spawns. The smoke
scenario 9a stops producing the conflicting "failed missing_worker_pid"
followed by "succeeded launcher" pair.

### LIV-006 — `spawn_id` env propagation to child processes is preserved

**When** a CLI runner forks a harness subprocess,
**the runner shall** continue to set `MERIDIAN_SPAWN_ID=<spawn_id>` in the
child env (today's behavior; called out as a stability requirement because
authorization in `spec/authorization.md` depends on it).

**Observable.** Existing test in `lib/launch/command.py` continues to pass.
A new contract test verifies the env var is set for both CLI and app
launches.
