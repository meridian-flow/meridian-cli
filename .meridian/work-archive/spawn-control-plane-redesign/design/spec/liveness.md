# Liveness — One Reaper Contract Across Surfaces

The reaper trusts a single signal: there is a process tagged as the
**spawn host** (recorded in `runner_pid`) and that process is alive **and**
keeps a heartbeat fresh. Both halves are required; either half alone is
ambiguous. There is one contract; CLI- and app-launched spawns satisfy it
the same way.

## EARS Statements

### LIV-001 — Every active spawn has a non-null `runner_pid`

**When** any code path transitions a `SpawnRecord` to status `running`,
**the writer shall** populate `runner_pid` with the PID of the process
that owns the live harness connection (CLI runner for streaming-serve,
FastAPI worker for app spawns).

**Observable.** No `SpawnRecord` row has `status="running"` and
`runner_pid is None` simultaneously.

### LIV-002 — The owning process keeps `heartbeat` fresh

**When** a process is the registered `runner_pid` for active spawns,
**that process shall** touch each spawn's `heartbeat` artifact at least
every `_HEARTBEAT_INTERVAL_SECS` (30s) for the spawn's connection
lifetime.

**Observable.** `heartbeat` mtime advances continuously while running.

### LIV-003 — Heartbeat ownership lives in `SpawnManager`

**When** `SpawnManager.start_spawn` registers a new session,
**the manager shall** start a per-session asyncio heartbeat task.

**Observable.** Per-session heartbeat task created in `start_spawn`,
cancelled in `_cleanup_completed_session` / `stop_spawn`. Legacy
`_run_heartbeat_task` in runners removed; ownership in one place.

### LIV-004 — Reaper never finalizes while heartbeat is fresh

**When** `decide_reconciliation` runs against a `SpawnRecord` with active
status and fresh heartbeat,
**the reaper shall** return `Skip(reason="recent_activity")`.

**Observable.** Existing rule, preserved. LIV-001 ensures `runner_pid`
is present for the alive-check as defence-in-depth.

### LIV-005 — App-managed spawn finalize is single-writer

**When** the FastAPI worker's `SpawnManager` `wait_for_completion`
resolves,
**the app shall** finalize with `origin="runner"` exactly once.

**v2 change.** Origin changed from `"launcher"` to `"runner"` because
the FastAPI worker IS the runner for app-managed spawns (D-03). No dual
finalize ownership; the app process is the single writer.

**Observable.** No double-finalize for app-launched spawns. The
`missing_worker_pid` / `succeeded launcher` pair from #30 stops.

### LIV-006 — `spawn_id` env propagation to child processes

**When** a runner forks a harness subprocess,
**the runner shall** set `MERIDIAN_SPAWN_ID=<spawn_id>` in the child env.

**Observable.** P7 verified this is already plumbed via `command.py:44`.
Contract test verifies the env var for both CLI and app launches.

## Verification plan

### Unit tests
- Heartbeat helper touches the file at configured interval.
- SpawnManager start/stop heartbeat is idempotent; no leaked task.

### Smoke tests
- Scenario 12: app-launched spawn, wait 60s, no `missing_worker_pid`.
- Scenario 13: app-launched spawn, kill FastAPI worker; reaper takes
  over within `heartbeat_window`.

### Fault-injection tests
- **Heartbeat stall**: block heartbeat touch; verify reaper detects
  the stall after `heartbeat_window` and reconciles.
