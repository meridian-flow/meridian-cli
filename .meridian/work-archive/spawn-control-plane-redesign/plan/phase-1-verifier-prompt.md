# Phase 1 Verification — Foundation Primitives

Verify Phase 1 of the spawn control plane redesign. The coder implemented R-01 (heartbeat helper), R-02 (inject/interrupt serialization), and R-11 (launch_mode schema extension).

## What to Verify

1. **Static checks**: `uv run ruff check .` and `uv run pyright` must pass clean.
2. **Tests**: `uv run pytest-llm` must pass.
3. **R-01 correctness**: Check that `src/meridian/lib/streaming/heartbeat.py` exists and both runners (`runner.py`, `streaming_runner.py`) delegate to it instead of inline loops.
4. **R-02 correctness**: 
   - `src/meridian/lib/streaming/inject_lock.py` exists with `get_lock()` and `drop_lock()`.
   - `SpawnManager.inject()` and `.interrupt()` acquire the lock and return `InjectResult` with `inbound_seq`.
   - `_record_inbound` returns the line index.
   - `on_result` callback fires inside lock scope.
   - `drop_lock` called from `stop_spawn` and `_cleanup_completed_session`.
5. **R-11 correctness**: `LaunchMode = Literal["background", "foreground", "app"]` in spawn_store.py. `SpawnStartEvent.launch_mode` typed as `LaunchMode | None`.

## EARS Statements to Verify

- INJ-001: Inject text delivered to harness without finalization
- INJ-002: Concurrent injects linearizable per spawn (lock + inbound_seq)
- INJ-003: Inject acks include inbound_seq
- INJ-004: Inject rejects when spawn is terminal
- INT-007: Per-spawn interrupt-and-inject ordering linearizable

## What NOT to Verify (out of phase scope)

- Cancel behavior, HTTP endpoints, AF_UNIX transport, authorization, classifier changes — all later phases.
