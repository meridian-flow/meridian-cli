# Phase 5: Collapse `streaming_serve.py` Onto the Canonical Path

## Goal

Replace the independent execution logic in `streaming_serve.py` with a thin wrapper around the shared streaming execution infrastructure. After this, there are only two execution paths: PTY primary and streaming-backed child/app.

## Context

`streaming_serve.py` currently has its own run loop: signal handling, subscriber polling, shutdown management, finalization. Phase 4 built `streaming_runner.py` which does all of this. The goal is to make `streaming_serve` delegate to shared helpers rather than reimplementing the same pattern.

The approach: `streaming_serve.py` becomes a thin adapter that:
1. Validates CLI inputs (harness, prompt, model)
2. Creates a spawn record in spawn_store
3. Builds `ConnectionConfig` + `SpawnParams`
4. Delegates execution to a shared helper from `streaming_runner.py`
5. Reports results

## Changes Required

### 1. `src/meridian/lib/launch/streaming_runner.py`

Extract or expose the minimum surface that `streaming_serve.py` needs. The streaming_serve use case is simpler than the full `execute_with_streaming` flow — it doesn't need retry, guardrails, budget, or the full finalization pipeline. But it needs the core loop: manager setup → start spawn → wait for completion → finalize.

Add a lighter-weight helper function:

```python
async def run_streaming_spawn(
    *,
    config: ConnectionConfig,
    params: SpawnParams,
    state_root: Path,
    repo_root: Path,
    spawn_id: SpawnId,
    stream_to_terminal: bool = False,
) -> DrainOutcome:
    """Run a streaming spawn to completion and return the drain outcome.
    
    Handles signal management, heartbeat, and resource cleanup.
    Does NOT handle spawn_store finalization (caller's responsibility).
    Does NOT handle retry, guardrails, or budget (those are runner-level policy).
    """
```

This helper:
- Creates `SpawnManager`
- Starts spawn
- Writes harness.pid if subprocess_pid available
- Installs signal handlers
- Subscribes and waits for completion/signal
- If stream_to_terminal, prints events
- Returns `DrainOutcome` from `manager.wait_for_completion()`
- Cleans up manager on exit

### 2. `src/meridian/cli/streaming_serve.py`

Rewrite to use the shared helper:

```python
async def streaming_serve(
    harness: str,
    prompt: str,
    model: str | None = None,
    agent: str | None = None,
) -> None:
    # 1. Validate inputs
    # 2. Create spawn record
    # 3. Build config + params
    # 4. Call run_streaming_spawn()
    # 5. Finalize with outcome
```

Remove all signal handling, subscriber management, and the custom run loop. The shared helper handles that.

### 3. `tests/test_streaming_serve.py`

Update tests. The tests currently mock `SpawnManager`, signal handlers, and the wait functions. After this change, `streaming_serve.py` delegates to `run_streaming_spawn`, so tests should mock that helper instead.

Alternatively, keep the existing test structure but update it to work with the new code flow.

### 4. `src/meridian/cli/main.py`

Keep the CLI entrypoint pointing at `streaming_serve`. Only change if the function signature changes (it shouldn't).

## Edge Cases

1. **Start failure**: If `run_streaming_spawn` raises during start, streaming_serve still needs to finalize as "failed".
2. **Signal during execution**: Handled by the shared helper — it installs signal handlers and stops the manager.
3. **streaming_serve still prints spawn info**: The print statements about spawn ID, socket path, output path should stay in streaming_serve (user-facing output) or move to the helper if appropriate.

## Files to Read First

- `src/meridian/cli/streaming_serve.py` (current implementation)
- `src/meridian/lib/launch/streaming_runner.py` (shared infrastructure)
- `src/meridian/lib/streaming/spawn_manager.py` (DrainOutcome, wait_for_completion)
- `tests/test_streaming_serve.py` (test updates)
- `src/meridian/cli/main.py` (CLI entrypoint)

## Verification

- `uv run pytest tests/test_streaming_serve.py -x` passes
- `uv run pytest tests/ -x` passes
- `uv run pyright` passes (0 errors)
- `uv run ruff check .` passes
