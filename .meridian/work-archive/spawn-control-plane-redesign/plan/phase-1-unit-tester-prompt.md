# Phase 1 Unit Testing — Foundation Primitives

Write and run unit tests for Phase 1 of the spawn control plane redesign.

## What to Test

### InjectResult and inbound_seq (R-02)
- `InjectResult` dataclass has `success`, `inbound_seq`, `noop`, `error` fields.
- Two coroutines calling `inject("A")` and `inject("B")` against a fake connection: verify `inbound_seq` values are monotonic and distinct.
- Same test with `inject("A")` and `interrupt()`: verify linearization.
- Lock scope verification: `on_result` callback fires inside lock scope (attempt a second operation from within the callback — it should deadlock/timeout, proving lock is held).

### LaunchMode schema (R-11)
- `LaunchMode` accepts `"app"` as a valid value.
- Spawn projection accepts `launch_mode="app"` in start events.

### Heartbeat helper (R-01)
- `heartbeat_loop` touches the file at configured interval.
- The sentinel file is created if it doesn't exist.

## Where to Put Tests

Place tests alongside existing test patterns in the `tests/` directory. Check existing test files for conventions.

## Run All Tests

```bash
uv run pytest-llm
```

Must pass clean. Report any failures.
