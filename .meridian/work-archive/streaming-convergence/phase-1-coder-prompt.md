# Phase 1: Finalization Ownership and App Handoff

## Goal

Remove all `spawn_store.finalize_spawn()` calls from `SpawnManager` so that terminal-state writes are exclusively owned by callers. Add a `wait_for_completion()` surface that callers can await to learn drain outcome. Update both existing callers (`streaming_serve.py` and `server.py`) to finalize spawns themselves.

## Key Design Decisions

- **D3**: Finalization logic lives in the runner, not the manager. Single writer.
- The manager signals drain completion to the caller but does NOT write terminal state.
- `SpawnManager` keeps control socket cleanup and session dict cleanup (resource freeing), but NOT `spawn_store.finalize_spawn()`.

## Changes Required

### 1. `src/meridian/lib/streaming/spawn_manager.py`

**Add a `DrainOutcome` dataclass:**
```python
@dataclass(frozen=True)
class DrainOutcome:
    status: SpawnStatus  # "succeeded" | "failed" | "cancelled"
    exit_code: int
    error: str | None = None
    duration_secs: float = 0.0
```

**Add `wait_for_completion(self, spawn_id: SpawnId) -> DrainOutcome | None`:**
- Returns a future/awaitable that resolves when the drain for this spawn completes.
- Uses an `asyncio.Future[DrainOutcome]` stored on `SpawnSession`.
- If spawn_id not found, returns None immediately.
- Does NOT consume the subscriber queue — callers can use both `subscribe()` for events AND `wait_for_completion()` for the terminal signal.

**Modify `SpawnSession`:**
- Add `completion_future: asyncio.Future[DrainOutcome]` field, created in `start_spawn()`.

**Modify `_drain_loop` finally block:**
- Instead of scheduling `_cleanup_completed_session` (which calls `_finalize_spawn`), resolve the `completion_future` with the `DrainOutcome` and then clean up resources (control socket, session dict removal) WITHOUT calling `spawn_store.finalize_spawn()`.
- On `CancelledError`, resolve the future with status="cancelled".

**Modify `_cleanup_completed_session`:**
- Remove the call to `_finalize_spawn`. Keep the control socket stop and session dict pop.

**Modify `stop_spawn`:**
- Remove the call to `_finalize_spawn`. Keep connection stop, drain cancel, control socket stop, session pop, and sentinel fan-out.
- If the drain already completed naturally (future already resolved), use its outcome. Otherwise, resolve the future with the stop-requested status.
- Return the `DrainOutcome` so callers know what happened.

**Modify `shutdown`:**
- Remove `_finalize_spawn` calls (they're removed from `stop_spawn` already).
- Keep calling `stop_spawn` for each session.

**Delete `_finalize_spawn` method entirely.**

### 2. `src/meridian/cli/streaming_serve.py`

After this change, `streaming_serve.py` must own all finalization:

- **Natural completion**: After `manager.shutdown()` returns (which no longer finalizes), call `spawn_store.finalize_spawn()` with the terminal status.
- **Shutdown/cancel**: Same — finalize after manager shutdown.
- **Start failure**: Already handled (the `if not manager_started:` block). Keep this.
- **Error**: Finalize as "failed".

The key change: currently `streaming_serve.py` relies on `manager.shutdown()` to finalize when the manager started. After this change, finalization always happens in the finally block, for ALL paths:
```python
finally:
    # ... cleanup ...
    await manager.shutdown()  # resource cleanup only, no finalize
    # Always finalize, whether manager started or not:
    spawn_store.finalize_spawn(
        state_root, spawn_id,
        status=shutdown_status,
        exit_code=shutdown_exit_code,
        duration_secs=...,
        error=... if shutdown_status == "failed" else None,
    )
```

### 3. `src/meridian/lib/app/server.py`

The app server currently relies on manager auto-finalization for spawns that complete naturally. After this change:

- **Start failure**: Already handled (lines 179-185 finalize on start_spawn exception). Keep this.
- **Natural completion**: Add a background task per spawn that awaits `manager.wait_for_completion(spawn_id)` and finalizes when it resolves.
- **Cancellation via REST**: `cancel_spawn` currently calls `manager.cancel()` which just sends cancel to the connection. The drain still needs to complete, and the background finalizer will pick it up.

Add a background finalizer coroutine:
```python
async def _background_finalize(spawn_id: SpawnId) -> None:
    outcome = await spawn_manager.wait_for_completion(spawn_id)
    if outcome is None:
        return  # already cleaned up
    spawn_store.finalize_spawn(
        state_root, spawn_id,
        status=outcome.status,
        exit_code=outcome.exit_code,
        duration_secs=outcome.duration_secs,
        error=outcome.error,
    )
```

Launch this as a background task after each successful `start_spawn()` call.

### 4. `tests/test_spawn_manager.py`

Update all three tests:

- **`test_spawn_manager_natural_completion_writes_envelope_and_finalizes`**: The manager should still write the envelope to output.jsonl. But instead of checking that `spawns.jsonl` has a "finalize" event, verify that the completion future resolves with `DrainOutcome(status="succeeded", exit_code=0)`. The spawn_store should NOT have a finalize event after manager drain completes — that's the caller's job now.

- **`test_spawn_manager_stop_spawn_finalizes_cancelled`**: After `stop_spawn`, verify the completion future resolved, but spawn_store should NOT have a finalize event.

- **`test_spawn_manager_stop_spawn_race_with_natural_cleanup_finalizes_once`**: The race test should verify that the completion future resolves exactly once with the correct status (succeeded, since drain completed naturally before stop_spawn).

### 5. `tests/test_streaming_serve.py`

- **`test_streaming_serve_shutdown_finalizes_once_as_cancelled`**: Update to verify that `streaming_serve.py` (not the manager) writes the finalize event. The FakeManager.shutdown should NOT finalize. The finalize should come from the streaming_serve finally block.

- **`test_streaming_serve_start_failure_finalizes_failed_once`**: Should work mostly as-is since start failure already finalizes in streaming_serve.

### 6. Tests for app server finalization

Add a test that verifies the background finalizer runs when a spawn completes through the REST API. If `tests/test_app_server.py` doesn't exist, create tests in `tests/server/` if that directory exists, or `tests/` otherwise.

## Edge Cases to Handle

1. **Race: drain completes just as stop_spawn is called**: The completion future should be resolved exactly once. Use `future.done()` guard before setting result.
2. **Race: stop_spawn called when drain_loop hasn't started yet**: The future exists (created in start_spawn) but drain_loop hasn't run. stop_spawn should resolve the future.
3. **start_spawn fails after connection.start() but before future is created**: This shouldn't happen if future is created before connection.start().
4. **Multiple await on wait_for_completion**: Asyncio futures support multiple awaiters. This should work.
5. **CancelledError in drain_loop**: Must still resolve the future (with cancelled status) before re-raising.
6. **App server: spawn cancelled via REST then drain completes**: Background finalizer should get the outcome regardless.

## Files to Read First

- `src/meridian/lib/streaming/spawn_manager.py` (primary target)
- `src/meridian/cli/streaming_serve.py` (caller)
- `src/meridian/lib/app/server.py` (caller)
- `tests/test_spawn_manager.py` (test updates)
- `tests/test_streaming_serve.py` (test updates)
- `src/meridian/lib/core/domain.py` (SpawnStatus type)
- `src/meridian/lib/state/spawn_store.py` (finalize_spawn signature)

## Verification

After changes:
- `uv run pytest tests/test_spawn_manager.py tests/test_streaming_serve.py -x` passes
- `uv run pyright` passes (0 errors)
- `uv run ruff check .` passes
