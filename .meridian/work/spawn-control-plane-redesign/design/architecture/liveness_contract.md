# Liveness Contract

Realizes `spec/liveness.md` (LIV-001 .. LIV-006) and the runner-side half of
`spec/cancel.md`.

## Why this exists

The reaper is the single arbiter of "is this spawn dead?". Its decision
depends on two signals:

1. **`runner_pid`** in `spawns.jsonl` (process that owns finalize).
2. **`heartbeat`** sentinel file, mtime-touched by that owner.

Today, two-process layouts violate both: the FastAPI worker hosts a
`SpawnManager` but never writes `runner_pid`, and the heartbeat code lives
in `runner.py` / `streaming_runner.py` exclusively, so app-managed spawns
never get a heartbeat. Reaper sees the spawn as missing-pid + stale-mtime
and stamps `missing_worker_pid` (issue #30).

## Module touch-list

```
src/meridian/lib/streaming/
  spawn_manager.py            # SpawnManager owns heartbeat task
  heartbeat.py                # NEW — touch helper extracted from runner.py
src/meridian/lib/launch/
  runner.py                   # remove inline heartbeat task; delegate to module helper
  streaming_runner.py         # same
src/meridian/lib/app/
  server.py                   # populate runner_pid; SpawnManager auto-starts heartbeat
src/meridian/lib/state/
  reaper.py                   # NO logic change; existing rules continue to apply
```

## `heartbeat.py`

A tiny, owner-agnostic touch primitive — the only writer to the heartbeat
file across all processes. Every other module (runner, streaming_runner,
SpawnManager) calls into this:

```python
async def heartbeat_loop(state_root: Path, spawn_id: SpawnId, interval: float = 30.0):
    sentinel = paths.heartbeat_path(state_root, spawn_id)
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    while True:
        sentinel.touch()
        await asyncio.sleep(interval)
```

Interval matches today's runner heartbeat (30s) and stays comfortably below
the reaper window (120s).

## SpawnManager ownership

SpawnManager gains `_start_heartbeat()` and `_stop_heartbeat()`:

- `_start_heartbeat()` runs once per spawn; idempotent on the SpawnManager
  instance. Triggered by:
  - `streaming_runner.run_streaming_spawn` (existing call site, but it now
    delegates instead of running its own loop)
  - The FastAPI app server's `_run_managed_spawn` (new call site)
- `_stop_heartbeat()` cancels the loop in `stop_spawn` and
  `_cleanup_completed_session`.

The runner (or app server) is still responsible for setting `runner_pid`.
SpawnManager doesn't write it because manager creation is not the moment
the OS pid stabilizes — the runner process pid is stable from import time,
but conceptually setting `runner_pid` is the "I am the owner" handshake and
that's policy, not mechanism.

## App-server changes

`reserve_spawn_id` (and the matching helper used by streaming launches)
adds `runner_pid=os.getpid()` to its `spawn_store.start_spawn(...)` call:

```python
spawn_store.start_spawn(
    state_root=state_root,
    spawn_id=spawn_id,
    ...,
    runner_pid=os.getpid(),
    worker_pid=worker_pid,  # may be 0 until harness pid stabilizes
)
```

`_run_managed_spawn` (the task that pumps SpawnManager events to the
subscriber queue) calls `manager._start_heartbeat()` immediately after the
manager is constructed and before the harness drain begins. Symmetric
`_stop_heartbeat()` happens in the existing `_cleanup_completed_session`
finally block.

## Reaper unchanged

The reaper logic in `decide_reconciliation` does not move. It still:

- treats `runner_pid <= 0` as "owner unknown" → `missing_worker_pid` after
  startup grace.
- treats stale heartbeat (`now - mtime > heartbeat_window`) as confirmation.
- skips reconciliation when heartbeat is fresh (LIV-004).

The reaper continues to write `origin=reconciler`. The projection still
upgrades to authoritative when an authoritative event lands later.

## Spawn pid lineage on FastAPI

Foreground CLI: `runner_pid == streaming_runner_process_pid`,
`worker_pid == harness_subprocess_pid`. Already correct.

App server (FastAPI worker): `runner_pid == fastapi_worker_pid`,
`worker_pid == harness_subprocess_pid` once the harness adapter reports it.
SignalCanceller's `_resolve_runner_pid` reads `runner_pid` first → SIGTERM
is delivered to the FastAPI worker, which already has a SIGTERM handler in
its `lifespan` shutdown sequence.

Wait — FastAPI workers handle SIGTERM at the *server* level, not per-spawn.
That's a structural mismatch. We solve it as follows:

- `SpawnManager` registers a per-spawn cancel future during construction.
- `SignalCanceller.cancel(spawn_id)` running inside the FastAPI worker
  process detects that `runner_pid == os.getpid()` and short-circuits to
  in-process cancellation: invoke `manager.stop_spawn(status="cancelled",
  error="cancelled")` directly.
- `SignalCanceller.cancel(spawn_id)` running outside the FastAPI worker
  (CLI invocation) sends SIGTERM as documented; the FastAPI worker
  intercepts SIGTERM via a custom handler that *only* cancels the spawn
  whose id arrives via a small inbound socket. **Rejected** — too much
  surface area for a single-spawn semantic.

The accepted approach: **don't SIGTERM the FastAPI worker**. Instead, the
CLI cancel command in app-managed mode uses the HTTP cancel endpoint
(`POST /api/spawns/{id}/cancel`), which routes inside the worker process
to the in-process branch. The cancel command auto-detects whether a
spawn is app-managed by reading the spawn record (`launch_mode == "app"`
or equivalent flag). For non-app spawns, SIGTERM goes to the runner pid
directly.

See `cancel_pipeline.md` for the dispatcher logic.

## Test plan

- **Unit**: heartbeat helper touches the file at the configured interval.
- **Unit**: SpawnManager start/stop heartbeat is idempotent; no leaked task
  after `stop_spawn`.
- **Smoke**: scenario 12 — start an app-launched spawn, wait 60s, verify
  reaper does not stamp `missing_worker_pid`.
- **Smoke**: scenario 13 — start an app-launched spawn, kill the FastAPI
  worker; verify reaper takes over within `heartbeat_window` and stamps a
  reconciler outcome.
