# Phase 1: Drain-Loop Terminal Event Tracking + SIGKILL Cleanup

## Scope
C-01: Make the drain loop observe terminal events as they stream through.
C-03: Clean up "Task exception was never retrieved" on OpenCode SIGKILL.

## What to Change

### 1. Make `_terminal_event_outcome` importable from streaming_runner.py

In `src/meridian/lib/launch/streaming_runner.py`:
- Rename `_TerminalEventOutcome` → `TerminalEventOutcome` (public)
- Rename `_terminal_event_outcome` → `terminal_event_outcome` (public)
- Update all internal references in the file
- Add both to `__all__` or ensure they're importable

### 2. Drain loop tracks terminal events in spawn_manager.py

In `src/meridian/lib/streaming/spawn_manager.py`:
- Import `terminal_event_outcome, TerminalEventOutcome` from `streaming_runner`
- In `_drain_loop()`, add a local variable `recorded_terminal_outcome: TerminalEventOutcome | None = None`
- Inside the `async for event` loop (after persisting), call `terminal_event_outcome(event)` and if non-None, record it
- In the `finally` block, after `cancel_sent` check and before `succeeded` default:
  ```
  elif recorded_terminal_outcome is not None:
      outcome = DrainOutcome(
          status=recorded_terminal_outcome.status,
          exit_code=recorded_terminal_outcome.exit_code,
          error=recorded_terminal_outcome.error,
          duration_secs=...,
      )
  else:
      outcome = DrainOutcome(status="succeeded", exit_code=0, ...)
  ```

### 3. SIGKILL cleanup (C-03)

The "Task exception was never retrieved" noise happens when `_drain_loop` raises an exception (like `ClientPayloadError`) but the drain_task is never awaited.

In `spawn_manager.py`, check `_cleanup_completed_session()` — the drain task should be awaited or its exception suppressed. In the `finally` of `_drain_loop`, the exception is already caught at line 323-324, but if the task is cancelled externally and the exception isn't consumed, Python logs the warning.

Fix: In `stop_spawn()` or `_cleanup_completed_session()`, ensure the drain task's exception is consumed:
```python
if session.drain_task is not None and not session.drain_task.cancelled():
    with suppress(Exception):
        session.drain_task.result()  # consume the exception
```

Or better: in `_cleanup_completed_session`, await the drain task with exception suppression.

## Files Touched
- `src/meridian/lib/launch/streaming_runner.py` — rename private → public
- `src/meridian/lib/streaming/spawn_manager.py` — drain loop + cleanup

## Exit Criteria
- `uv run ruff check .` clean
- `uv run pyright` clean (0 errors)
- `uv run pytest-llm` passes
