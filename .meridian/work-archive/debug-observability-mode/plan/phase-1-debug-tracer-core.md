# Phase 1: DebugTracer Core

## Round: 1 (parallel with Phase 2)

## Scope

Create the `src/meridian/lib/observability/` package with the `DebugTracer` class and shared trace helper functions. The only non-package file in scope is focused test coverage for the tracer contract.

## Intent

The tracer is a structured JSONL writer for wire-level observability. Its core rule is strict: `emit()` is best-effort and never raises. If serialization, file I/O, or stderr echo fails, the tracer logs one warning, disables itself, and silently no-ops afterward.

## Files to Create

### `src/meridian/lib/observability/__init__.py`

Minimal package init that re-exports:

- `DebugTracer`
- `trace_state_change`
- `trace_wire_send`
- `trace_wire_recv`
- `trace_parse_error`

### `src/meridian/lib/observability/debug_tracer.py`

Implement `DebugTracer` with this contract:

```python
class DebugTracer:
    def __init__(
        self,
        spawn_id: str,
        debug_path: Path,
        *,
        echo_stderr: bool = False,
        max_payload_bytes: int = 4096,
    ) -> None: ...

    def emit(
        self,
        layer: str,
        event: str,
        *,
        direction: str = "internal",
        data: dict[str, object] | None = None,
    ) -> None: ...

    def close(self) -> None: ...
```

Implementation requirements:

- lazy file open on first `emit()`
- `threading.Lock` around file-handle writes
- compact one-line JSON objects with `ts`, `spawn_id`, `layer`, `direction`, `event`, and `data`
- string truncation with the `...[truncated, NB total]` suffix
- dict/list values serialized to JSON before truncation
- one warning on first internal failure, then permanent self-disable
- idempotent `close()`

### `src/meridian/lib/observability/trace_helpers.py`

Implement:

- `trace_state_change(...)`
- `trace_wire_send(...)`
- `trace_wire_recv(...)`
- `trace_parse_error(...)`

Each helper should do the `if tracer is not None` check internally so later phases get one-line call sites.

### `tests/test_debug_tracer.py`

Add focused regression coverage for:

- JSONL schema and per-line metadata
- truncation behavior
- data preparation for strings, dicts, lists, scalars, and non-serializable objects
- first-failure disable semantics
- idempotent `close()`
- lazy file creation
- `echo_stderr=True`
- helper no-op behavior when `tracer is None`

## Dependencies

- **Requires:** Nothing. This package must remain importable from harness, launch, streaming, and app layers without circular imports.
- **Produces:** `DebugTracer` and the shared helper functions consumed by Phases 3-6.

## Patterns to Follow

- Use `logging.getLogger(__name__)` for the warning path.
- Look at `src/meridian/lib/state/atomic.py` for local file helper style, but do not use tmp+rename here. `debug.jsonl` is append-only best-effort output.

## Constraints

- No async code.
- No imports from `lib/harness/`, `lib/launch/`, `lib/streaming/`, or `lib/app/`.
- The tracer must be safe to call from hot paths and from `asyncio.to_thread` write sites.

## Verification Criteria

- [ ] `uv run pyright` passes with 0 errors
- [ ] `uv run ruff check .` passes
- [ ] `uv run pytest-llm tests/test_debug_tracer.py` passes
- [ ] `emit()` never raises, including after a simulated write failure
- [ ] No file is created until the first successful `emit()`
