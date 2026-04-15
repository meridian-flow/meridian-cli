# Phase 1: Finalization Ownership and App Handoff

**Risk:** High  
**Design docs:** [overview.md](../design/overview.md), [streaming-runner.md](../design/streaming-runner.md)

## Scope

Remove terminal-state writes from `SpawnManager` and replace them in the existing streaming consumers immediately. After this phase, the manager owns only connection lifecycle, drain persistence, fan-out, and control socket cleanup. Callers own `spawn_store.finalize_spawn()`.

This phase must leave both current consumers working:

- `meridian app`
- `meridian streaming serve`

## Files to Modify

- `src/meridian/lib/streaming/spawn_manager.py`
  Remove `_finalize_spawn()` ownership and add one explicit completion surface that callers can await without consuming the event subscriber used by UI/WebSocket streaming.
- `src/meridian/lib/app/server.py`
  Start a background finalizer per app-created spawn that waits for manager completion and performs the one authoritative finalize write.
- `src/meridian/cli/streaming_serve.py`
  Stop relying on `SpawnManager.shutdown()` for terminal-state writes. Finalize explicitly on natural completion, shutdown, and start failure.
- `tests/test_spawn_manager.py`
  Rewrite expectations so the manager persists envelopes and cleans resources, but does not append `finalize` events on its own.
- `tests/test_streaming_serve.py`
  Move finalize expectations from manager shutdown to the explicit caller-owned finalizer path.
- `tests/test_app_server.py`
  Add focused tests for natural completion and start failure on the REST path if no equivalent coverage already exists.

## Dependencies

- Requires: none
- Produces: the stable lifecycle contract that every later streaming caller uses
- Independent of: extraction protocol refactor, config split refactor

## Interface Contract

The implementation should expose one manager-owned completion surface that is reusable by both the app and the future streaming runner. A concrete shape is preferred over more ad-hoc sentinel polling. For example:

```python
@dataclass(frozen=True)
class DrainOutcome:
    status: SpawnStatus
    exit_code: int
    error: str | None = None

async def wait_for_completion(self, spawn_id: SpawnId) -> DrainOutcome | None: ...
```

Required behavior regardless of exact API:

- Natural drain completion never calls `spawn_store.finalize_spawn()` inside `SpawnManager`.
- Explicit stop/shutdown never calls `spawn_store.finalize_spawn()` inside `SpawnManager`.
- Callers can await one definitive completion outcome without taking over the event subscriber queue.
- Resource cleanup remains idempotent and race-safe.

## Patterns to Follow

- Follow the existing cleanup race coverage in `tests/test_spawn_manager.py`; keep one authoritative terminal-state writer.
- Reuse the shutdown and signal structure in `src/meridian/cli/streaming_serve.py`, but move finalization out of the manager contract.

## Constraints and Boundaries

- Do not route `meridian spawn` to streaming in this phase.
- Do not introduce streaming-runner policy here.
- Do not leave `server.py` or `streaming_serve.py` depending on implicit manager finalization after this phase.

## Verification Criteria

- `uv run pytest tests/test_spawn_manager.py tests/test_streaming_serve.py` passes.
- Any new app-server tests for spawn completion/failure pass.
- `uv run pyright` passes.
- Smoke test: create a spawn through `meridian app`, let it complete or cancel it, and verify exactly one terminal `finalize` event is written.

## Staffing

- Builder: `@coder`
- Testers: `@verifier`, `@smoke-tester`

## Completion Signal

This phase is done when the manager can no longer finalize spawns by itself and the current app/streaming entry points still produce correct terminal state.
