# Phase 3: Interrupt Classifier (R-04)

Make interrupt non-fatal at the runner layer by narrowing `_terminal_event_outcome`.

## What to Change

### `src/meridian/lib/launch/streaming_runner.py`

Find `_terminal_event_outcome` function. Currently it returns a non-None outcome for `turn/completed` events with non-`completed` status (including `interrupted`). This is the root cause of #28.

**New rule:** `turn/completed` events are NEVER spawn-terminal. The spawn ends only on:
- `session.error` / `session.terminated` — harness is done
- The harness exiting its event stream (drain ends naturally)
- SIGTERM / SIGINT (CAN-001)
- Report-watchdog escalation

For codex specifically:
```python
if event.harness_id == HarnessId.CODEX.value and event.event_type == "turn/completed":
    # Per-turn outcome; spawn lifetime continues. Fixes #28.
    return None
```

Claude `result` and opencode `session.idle`/`session.error` remain unchanged — those describe the SESSION, not a turn.

### Interrupt noop behavior (INT-004)

In `SpawnManager.interrupt()`, when no turn is in flight (`connection.current_turn_id is None`), return `InjectResult(success=True, noop=True)`. Check this is already present from Phase 1 — if not, add it.

## EARS Statements

- INT-001: Interrupt stops current turn without finalization
- INT-002: `turn/completed` with `status="interrupted"` is non-terminal
- INT-003: Interrupt followed by usable connection
- INT-004: Interrupt allowed when no turn in flight (noop ack)

## What NOT to Change

- Do NOT change cancel behavior
- Do NOT change HTTP endpoints
- Do NOT change authorization
- Do NOT change app server or liveness

## Verification

```bash
uv run ruff check .
uv run pyright
uv run pytest-llm
```
