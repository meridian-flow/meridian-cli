# Phase 4: Streaming Runner and `meridian spawn` Routing

## Goal

Build `streaming_runner.py` — the streaming equivalent of `runner.py`'s `execute_with_finalization()`. Then route streaming-capable child spawns through it in `execute.py`.

## Context from Prior Phases

- **Phase 1**: `SpawnManager` no longer calls `spawn_store.finalize_spawn()`. It exposes `DrainOutcome` + `wait_for_completion()` for callers to own finalization.
- **Phase 2**: `SpawnExtractor` protocol exists in `adapter.py`. `enrich_finalize()` takes `extractor: SpawnExtractor`. `unwrap_event_payload()` in `common.py` handles envelope format. Connection implementations have `session_id` property.
- **Phase 3**: `ConnectionConfig` is transport-only. `HarnessConnection.start()` takes `(config, params)`. `SpawnManager.start_spawn()` takes `(config, params)`.

## New File: `src/meridian/lib/launch/streaming_runner.py`

Create `execute_with_streaming()` that mirrors `execute_with_finalization()` signature. The streaming runner:

1. Builds `ConnectionConfig` (transport) + `SpawnParams` (command) from `PreparedSpawnPlan`
2. Creates a `SpawnManager` and starts a spawn
3. Writes `harness.pid` from `connection.subprocess_pid` (new property needed)
4. Marks spawn running with `mark_spawn_running`
5. Subscribes to drain events
6. Starts a report watchdog (watches for report.md)
7. Installs signal handlers (SIGINT/SIGTERM → stop)
8. Waits for: drain completion OR report watchdog timeout OR signal OR budget breach
9. Runs finalization: `reset_finalize_attempt_artifacts()`, `enrich_finalize()`, `extract_latest_session_id()`, guardrails, retry logic
10. On retry: `manager.stop_connection(spawn_id)` (needs new method — stops connection without finalizing), sleep backoff, restart
11. On done: `resolve_execution_terminal_state()` + `spawn_store.finalize_spawn()` in finally with SIGTERM masked
12. Returns exit code

### Key implementation details:

**Report watchdog**: Watch for `report.md` appearing in spawn log dir. After detection, start grace timer. If drain doesn't complete in grace period, call `manager.stop_spawn()` to close connection. This handles harnesses that write the report but keep the connection alive.

**Budget tracking**: Observe events from the subscriber queue. Extract cost from structured events using `unwrap_event_payload()` + `LiveBudgetTracker.observe_json_line()`.

**Terminal output (--stream)**: When `stream_stdout_to_terminal=True`, print events from subscriber to terminal using `parse_json_stream_event()`.

**Signal handling**: Use `asyncio.Event` and signal handlers, same pattern as `streaming_serve.py`.

**Heartbeat**: Wrap spawn lifetime in `heartbeat_scope`.

**subprocess_pid**: Need `HarnessConnection` to expose subprocess PID. Add `subprocess_pid: int | None` property:
- `CodexConnection`: return `self._process.pid`
- `ClaudeConnection`: return `self._process.pid`
- `OpenCodeConnection`: return `self._process.pid`

**stop_connection() method on SpawnManager**: New method that stops a connection and cleans up the session WITHOUT writing terminal state, for use between retry attempts. It should:
1. Stop the connection
2. Cancel and await drain task
3. Stop control server
4. Remove session from dict
5. NOT finalize via spawn_store
6. NOT resolve completion_future (or resolve with a sentinel that indicates "retry")

Actually, since the streaming runner manages the retry loop and owns finalization, it can just call `stop_spawn()` between retries — that already doesn't finalize (Phase 1 removed that). But `stop_spawn()` resolves the completion_future. For retries, we need to re-create the session. So the streaming runner should:
- Between retries: call `stop_spawn()` to clean up, which resolves the future. Then `start_spawn()` will create a new session with a new future.

### Signature:

```python
async def execute_with_streaming(
    run: Spawn,
    *,
    plan: PreparedSpawnPlan,
    repo_root: Path,
    state_root: Path,
    artifacts: ArtifactStore,
    registry: HarnessRegistry,
    cwd: Path | None = None,
    env_overrides: dict[str, str] | None = None,
    budget: Budget | None = None,
    space_spent_usd: float = 0.0,
    guardrails: tuple[Path, ...] = (),
    guardrail_timeout_seconds: float = DEFAULT_GUARDRAIL_TIMEOUT_SECONDS,
    secrets: tuple[SecretSpec, ...] = (),
    harness_session_id_observer: Callable[[str], None] | None = None,
    event_observer: Callable[[StreamEvent], None] | None = None,
    stream_stdout_to_terminal: bool = False,
    stream_stderr_to_terminal: bool = False,
) -> int:
```

## Modify: `src/meridian/lib/harness/connections/base.py`

Add `subprocess_pid` to `HarnessConnection`:

```python
class HarnessConnection(HarnessLifecycle, HarnessSender, HarnessReceiver, Protocol):
    @property
    def harness_id(self) -> HarnessId: ...
    @property
    def spawn_id(self) -> SpawnId: ...
    @property
    def capabilities(self) -> ConnectionCapabilities: ...
    @property
    def session_id(self) -> str | None: ...
    @property
    def subprocess_pid(self) -> int | None: ...
```

## Modify: Connection implementations

**`codex_ws.py`**: Add `subprocess_pid` property returning `self._process.pid if self._process else None`.
**`claude_ws.py`**: Same.
**`opencode_http.py`**: Same.

## Modify: `src/meridian/lib/ops/spawn/execute.py`

Route to `execute_with_streaming` when `harness.capabilities.supports_bidirectional` is True.

In `execute_spawn_blocking`, after resolving the plan and session context, check the flag:

```python
resolved_harness_id = HarnessId(prepared.harness_id)
harness = runtime.harness_registry.get_subprocess_harness(resolved_harness_id)

if harness.capabilities.supports_bidirectional:
    exit_code = asyncio.run(
        execute_with_streaming(...)
    )
else:
    exit_code = asyncio.run(
        execute_with_finalization(...)
    )
```

Same in `_execute_existing_spawn`.

## Modify: `src/meridian/lib/harness/extractor.py` (new file)

Create `StreamingExtractor` that implements `SpawnExtractor` using connection state + common extractors:

```python
class StreamingExtractor:
    def __init__(self, connection: HarnessConnection | None, harness_id: HarnessId):
        self._connection = connection
        self._harness_id = harness_id

    def extract_session_id(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None:
        if self._connection is not None:
            session_id = self._connection.session_id
            if session_id:
                return session_id
        return extract_session_id_from_artifacts(artifacts, spawn_id)

    def extract_usage(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> TokenUsage:
        return extract_usage_from_artifacts(artifacts, spawn_id)

    def extract_report(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None:
        # Delegate to harness-specific extractors
        if self._harness_id == HarnessId.CODEX:
            return extract_codex_report(artifacts, spawn_id)
        if self._harness_id == HarnessId.CLAUDE:
            return extract_claude_report(artifacts, spawn_id)
        if self._harness_id == HarnessId.OPENCODE:
            return extract_opencode_report(artifacts, spawn_id)
        return None
```

## Files to Read First

- `src/meridian/lib/launch/runner.py` (execute_with_finalization — the pattern to mirror)
- `src/meridian/lib/streaming/spawn_manager.py` (DrainOutcome, wait_for_completion, start_spawn)
- `src/meridian/lib/ops/spawn/execute.py` (routing changes)
- `src/meridian/lib/harness/connections/base.py` (subprocess_pid addition)
- `src/meridian/lib/harness/adapter.py` (SpawnExtractor, SpawnParams)
- `src/meridian/lib/launch/extract.py` (enrich_finalize)
- `src/meridian/lib/launch/session_ids.py` (extract_latest_session_id)
- `src/meridian/lib/harness/common.py` (extract helpers, unwrap_event_payload)
- `src/meridian/lib/launch/heartbeat.py` (heartbeat_scope)
- `src/meridian/lib/launch/signals.py` (signal_coordinator)
- `src/meridian/lib/core/spawn_lifecycle.py` (resolve_execution_terminal_state)
- `src/meridian/lib/safety/budget.py` (Budget, LiveBudgetTracker)
- `src/meridian/lib/safety/guardrails.py` (run_guardrails)
- `src/meridian/cli/streaming_serve.py` (signal handling pattern)
- `src/meridian/lib/ops/spawn/plan.py` (PreparedSpawnPlan)
- `src/meridian/lib/harness/connections/codex_ws.py`
- `src/meridian/lib/harness/connections/claude_ws.py`
- `src/meridian/lib/harness/connections/opencode_http.py`

## Edge Cases

1. **Report watchdog fires but drain already completing**: Use `asyncio.wait` with FIRST_COMPLETED so whichever happens first wins.
2. **Signal during finalization**: Mask SIGTERM in finally block.
3. **Budget breach**: Stop the spawn, break retry loop, finalize as failed with budget error.
4. **Connection start failure**: The first start_spawn may fail. Treat as retryable if appropriate.
5. **Guardrail failure**: Same as runner.py — if guardrails fail, retry or fail.
6. **No subprocess_pid**: Some connections might not have a subprocess. Return None and skip PID bookkeeping.

## Verification

- `uv run pyright` passes (0 errors)
- `uv run ruff check .` passes
- `uv run pytest tests/ -x` passes
- Focus on type correctness — the real smoke test needs a running harness
