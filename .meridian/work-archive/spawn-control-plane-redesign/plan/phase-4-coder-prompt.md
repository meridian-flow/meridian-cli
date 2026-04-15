# Phase 4: Liveness Contract (R-07)

Move app-managed spawns onto the same liveness contract as CLI spawns.

## What to Change

### `src/meridian/lib/streaming/spawn_manager.py`

Add `_start_heartbeat()` / `_stop_heartbeat()` methods to SpawnManager:
- `_start_heartbeat(spawn_id)` — starts the heartbeat loop task from `heartbeat.py` (added in Phase 1). Idempotent.
- `_stop_heartbeat(spawn_id)` — cancels the heartbeat task. Called from `stop_spawn()` and `_cleanup_completed_session()`.

The heartbeat helper was extracted in Phase 1 (R-01). Now SpawnManager takes ownership of starting/stopping it.

### `src/meridian/lib/app/server.py`

1. **runner_pid population**: Set `runner_pid=os.getpid()` at spawn creation. Change `start_spawn(...)` call to include `runner_pid=os.getpid()`.
2. **launch_mode**: Set `launch_mode="app"` (schema extended in Phase 1, R-11).
3. **Heartbeat wiring**: Call `manager._start_heartbeat(spawn_id)` in the managed spawn path.
4. **Finalize as runner**: Change background-finalize to write `origin="runner"` instead of `origin="launcher"`.

### `src/meridian/lib/launch/streaming_runner.py` and `runner.py`

Replace the runners' own heartbeat task creation with calls to SpawnManager's heartbeat methods. The runners currently create their own heartbeat tasks (modified in Phase 1 to use the shared helper). Now they should delegate to SpawnManager.

## EARS Statements

- LIV-001: Every active spawn has non-null runner_pid
- LIV-002: Owning process keeps heartbeat fresh
- LIV-003: Heartbeat ownership in SpawnManager
- LIV-004: Reaper never finalizes while heartbeat fresh (existing, preserved)
- LIV-005: App-managed spawn finalize is single-writer
- LIV-006: spawn_id env propagation (existing, preserved)

## What NOT to Change

- Do NOT change reaper logic
- Do NOT change cancel behavior
- Do NOT change HTTP endpoints or authorization
- Do NOT change _terminal_event_outcome

## Verification

```bash
uv run ruff check .
uv run pyright
uv run pytest-llm
```
