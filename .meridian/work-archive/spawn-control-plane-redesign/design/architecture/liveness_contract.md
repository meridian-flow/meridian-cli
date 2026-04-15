# Liveness Contract (v2)

Realizes `spec/liveness.md` (LIV-001..LIV-006) and the runner-side half
of `spec/cancel.md`.

## Why this exists

The reaper decides "is this spawn dead?" based on two signals:

1. **`runner_pid`** in `spawns.jsonl` (process that owns finalize).
2. **`heartbeat`** sentinel file, mtime-touched by that owner.

Today, app-managed spawns violate both: no `runner_pid`, no heartbeat
(issue #30).

## Module touch-list

```
src/meridian/lib/streaming/
  spawn_manager.py            # SpawnManager owns heartbeat task
  heartbeat.py                # NEW — touch helper extracted from runner.py
src/meridian/lib/launch/
  runner.py                   # remove inline heartbeat; delegate to helper
  streaming_runner.py         # same
src/meridian/lib/app/
  server.py                   # populate runner_pid; SpawnManager heartbeat
src/meridian/lib/state/
  reaper.py                   # NO logic change; existing rules apply
```

## `heartbeat.py`

Owner-agnostic touch primitive — the only writer to heartbeat files:

```python
async def heartbeat_loop(state_root: Path, spawn_id: SpawnId, interval: float = 30.0):
    sentinel = paths.heartbeat_path(state_root, spawn_id)
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    while True:
        sentinel.touch()
        await asyncio.sleep(interval)
```

Interval = 30s, comfortably below reaper window (120s).

## SpawnManager ownership

SpawnManager gains `_start_heartbeat()` / `_stop_heartbeat()`:

- `_start_heartbeat()` runs once per spawn; idempotent. Triggered by:
  - `streaming_runner.run_streaming_spawn` (delegates instead of own loop)
  - App server's `_run_managed_spawn` (new call site)
- `_stop_heartbeat()` cancels the loop in `stop_spawn` and
  `_cleanup_completed_session`.

Runner (or app server) still sets `runner_pid`. SpawnManager doesn't
write it because PID stabilization is the caller's responsibility.

## App-server changes

### `runner_pid` population

`reserve_spawn_id` adds `runner_pid=os.getpid()`:

```python
spawn_store.start_spawn(
    state_root=state_root,
    spawn_id=spawn_id,
    ...,
    launch_mode="app",       # v2: new value (D-12)
    runner_pid=os.getpid(),  # v2: fixes #30
    status="running",
)
```

### Heartbeat wiring

`_run_managed_spawn` calls `manager._start_heartbeat()` before drain.
`_cleanup_completed_session` calls `_stop_heartbeat()`.

### Finalize as runner (v2 change)

App-server `_background_finalize` now writes `origin="runner"` instead
of `origin="launcher"`:

```python
async def _background_finalize(spawn_id):
    outcome = await spawn_manager.wait_for_completion(spawn_id)
    if outcome is None:
        return
    spawn_store.finalize_spawn(
        state_root, spawn_id,
        status=outcome.status,
        exit_code=outcome.exit_code,
        origin="runner",          # v2: app IS the runner
        duration_secs=outcome.duration_secs,
        error=outcome.error,
    )
```

This eliminates dual finalize ownership. The FastAPI worker is the single
writer for app-managed spawns. The `streaming_serve.py` outer wrapper
path (which writes `origin="launcher"`) is separate and unaffected.

## Spawn PID lineage

| Surface | `runner_pid` | `worker_pid` |
|---|---|---|
| CLI foreground | streaming_runner PID | harness subprocess PID |
| App server | FastAPI worker PID | harness subprocess PID |

`SignalCanceller._resolve_runner_pid` reads `runner_pid` first (CLI spawns
only). For app spawns, `SignalCanceller` detects `launch_mode == "app"`
and routes through in-process `manager.stop_spawn()` or HTTP
`POST /cancel` — no SIGTERM to the shared worker (v2r2 D-03 two-lane).

## Reaper unchanged

Reaper logic does not move. Still:
- `runner_pid <= 0` → `missing_worker_pid` after startup grace.
- Stale heartbeat → confirmation of death.
- Fresh heartbeat → `Skip(reason="recent_activity")`.
- `origin=reconciler`, upgradeable to authoritative.
- `status == "finalizing"` → skip PID alive check.

## `launch_mode` schema change (D-12)

`LaunchMode = Literal["background", "foreground", "app"]`. App server
sets `launch_mode="app"`. Used for:
- Status display (distinguish app-managed from CLI spawns).
- Reaper diagnostics.
- Future tooling.

Used by `SignalCanceller` for cancel dispatch (v2r2 D-03): two-lane
cancel branches on `launch_mode` — SIGTERM for CLI, in-process for app.

## Test plan

### Unit tests
- Heartbeat helper touches file at configured interval.
- SpawnManager start/stop heartbeat is idempotent; no leaked task.

### Smoke tests
- Scenario 12: app-launched spawn, wait 60s, no `missing_worker_pid`.
- Scenario 13: app-launched spawn, kill FastAPI worker; reaper takes over.

### Fault-injection tests
- **Heartbeat stall**: block heartbeat touch; verify reaper detects after
  window and reconciles.
- **Worker restart**: kill FastAPI worker; verify stale `runner_pid` is
  detected by PID-reuse guard in reaper, reconciliation fires.
