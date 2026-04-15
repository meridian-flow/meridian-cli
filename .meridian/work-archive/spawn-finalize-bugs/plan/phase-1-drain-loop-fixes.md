# Phase 1: Drain-Loop Family (B-01, B-02, B-03)

## Scope
Fix the three drain-loop source-of-truth bugs where the spawn finalization path misclassifies terminal state.

## Files Touched
- `src/meridian/lib/launch/streaming_runner.py` — `_terminal_event_outcome()`
- `src/meridian/lib/streaming/spawn_manager.py` — `_drain_loop()` finally block

## Changes

### B-01: Codex turn/completed as terminal
In `_terminal_event_outcome()` (~line 246), replace the early return `None` for Codex `turn/completed` with a return of `_TerminalEventOutcome(status="succeeded", exit_code=0)`. One-shot spawns treat turn completion as session completion.

### B-02: Drain finally consults cancel_sent
In `_drain_loop()` finally block (~lines 326-354), add `elif session.cancel_sent:` check before the `else` succeeded branch:
```python
elif session.cancel_sent:
    outcome = DrainOutcome(
        status="cancelled",
        exit_code=143,
        error="cancelled",
        duration_secs=...,
    )
```

### B-03: error/connectionClosed → failed
In `_terminal_event_outcome()`, add a case for `error/connectionClosed` returning `_TerminalEventOutcome(status="failed", exit_code=1, error="connection_closed")`.

## Exit Criteria
- `uv run ruff check .` passes
- `uv run pyright` passes  
- `uv run pytest-llm` passes
- Code review of the three changes shows correct logic
