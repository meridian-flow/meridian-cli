# Phase 5: SpawnManager Drain Loop Hooks

## Round: 3 (parallel with Phase 4)

## Scope

Instrument `SpawnManager._drain_loop()` and `_fan_out_event()` with drain-layer trace hooks. The tracer is passed directly into `_drain_loop()` to avoid the race where the drain task starts before `SpawnSession` has been registered.

## Intent

The drain layer explains what happened after the adapter parsed an event: whether Meridian persisted it, whether a subscriber received it, and whether backpressure or repeated disk failures caused the pipeline to degrade.

## Files to Modify

### `src/meridian/lib/streaming/spawn_manager.py`

Update `_drain_loop()` to accept `tracer: DebugTracer | None` and emit:

- `drain/event_received`
- `drain/event_persisted`
- `drain/persist_error`

Update `_fan_out_event()` to emit:

- `drain/event_fanout`
- `drain/event_dropped`

Replace the current `with suppress(asyncio.QueueFull)` path with explicit `try/except asyncio.QueueFull` for regular events so drop traces can be recorded while preserving the existing behavior. Keep the terminal `None` sentinel logic intact.

Update `start_spawn()` to pass the resolved tracer directly into `_drain_loop()`.

### `tests/test_spawn_manager.py`

Add or extend coverage for:

- direct tracer parameter flow into `_drain_loop()`
- persisted-event and drop-event traces
- queue-full behavior staying unchanged
- cleanup ordering relative to `completion_future`

## Dependencies

- **Requires:** Phase 3.
- **Produces:** `drain` layer events for receive, persist, fan-out, and drop paths.
- **Independent of:** Phase 4.

## Patterns to Follow

- Match the existing drain outcome and cleanup ordering; trace emission should fit around it, not reorder it.
- Capture exceptions with `except Exception as exc:` so `persist_error` can record the message.

## Constraints

- The tracer is a direct `_drain_loop()` parameter, not a lookup from `SpawnSession`.
- `_fan_out_event()` behavior must remain identical when tracing is disabled.
- Do not disturb `completion_future` resolution semantics.

## Verification Criteria

- [ ] `uv run pyright` passes with 0 errors
- [ ] `uv run ruff check .` passes
- [ ] `uv run pytest-llm tests/test_spawn_manager.py` passes
- [ ] `_drain_loop()` accepts `tracer: DebugTracer | None`
- [ ] Queue-full fan-out still drops non-terminal events silently from the caller’s perspective
- [ ] When exercised, `debug.jsonl` contains `event_received`, `event_persisted`, `event_fanout`, and `event_dropped` or `persist_error`
