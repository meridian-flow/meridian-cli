# Streaming Runner — Detailed Design

## Purpose

`streaming_runner.py` is the streaming equivalent of `runner.py`'s `execute_with_finalization()`. It wraps `SpawnManager` with the execution policy that `runner.py` currently owns: finalization, retry, budget, heartbeat, signal handling. After this, `execute.py` can route streaming-capable harnesses here instead of to `runner.py`.

## Function Signature

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

The signature intentionally mirrors `execute_with_finalization` so `execute.py` can call either based on the `supports_bidirectional` flag with minimal branching.

## Execution Flow

```
execute_with_streaming(run, plan, ...)
  │
  ├─ Build ConnectionConfig from plan + run (including report_output_path, mcp_tools, etc.)
  ├─ Resolve SubprocessHarness adapter from registry (for extraction)
  ├─ Create SpawnManager(state_root, repo_root)
  ├─ heartbeat_scope(heartbeat_path)
  │
  ├─ RETRY LOOP:
  │   ├─ manager.start_spawn(config)  ← launches harness + connection
  │   ├─ Write harness.pid from connection.subprocess_pid
  │   ├─ mark_spawn_running(worker_pid=connection.subprocess_pid)
  │   ├─ Subscribe to drain (always — needed for completion detection)
  │   ├─ Start report watchdog (watches for report.md appearing)
  │   ├─ Install signal handlers (SIGINT/SIGTERM → shutdown_event.set)
  │   │
  │   ├─ WAIT (concurrent tasks):
  │   │   ├─ Subscriber sentinel (drain complete) → break
  │   │   ├─ Report watchdog (report.md + grace period) → manager.stop_spawn → break
  │   │   ├─ Signal received → manager.stop_spawn → break
  │   │   └─ Budget callback on subscriber events → manager.stop_spawn → break
  │   │
  │   ├─ POST-DRAIN FINALIZATION:
  │   │   ├─ reset_finalize_attempt_artifacts() — clear per-attempt state
  │   │   ├─ enrich_finalize(harness=adapter) — report + token extraction
  │   │   ├─ extract_latest_session_id(adapter=adapter)
  │   │   ├─ run_guardrails() if exit_code == 0
  │   │   ├─ Check for retryable error
  │   │   └─ If retry: manager.stop_connection(spawn_id), sleep(backoff), continue
  │   │   └─ If done: break
  │   │
  │   └─ manager.stop_connection(spawn_id) after each attempt (no finalize)
  │
  └─ FINALLY:
      ├─ mask_sigterm()
      ├─ resolve_execution_terminal_state()
      ├─ spawn_store.finalize_spawn()  ← SINGLE authoritative write
      ├─ manager.shutdown() (idempotent, resource cleanup only)
      └─ return exit_code
```

Key differences from `runner.py`'s flow:
- **No subprocess management** — the connection owns the subprocess
- **Report watchdog** instead of report-watchdog-integrated-into-stream-capture
- **`stop_connection()` between retries** instead of just restarting the subprocess — cleans up the connection and drain without writing terminal state
- **Budget via subscriber callback** instead of stdout line observation
- **Single finalize in finally** — the manager never writes terminal state

## Config Construction

The streaming runner builds two objects from the `PreparedSpawnPlan` — transport config and command params. This keeps `ConnectionConfig` focused on transport concerns (ISP, D15).

```python
def _build_configs(
    run: Spawn,
    plan: PreparedSpawnPlan,
    env_overrides: dict[str, str],
    execution_cwd: Path,
    report_path: Path,
) -> tuple[ConnectionConfig, SpawnParams]:
    config = ConnectionConfig(
        spawn_id=run.spawn_id,
        harness_id=HarnessId(plan.harness_id),
        model=str(run.model) if str(run.model).strip() else None,
        prompt=run.prompt,
        repo_root=execution_cwd,
        env_overrides=env_overrides,
        timeout_seconds=plan.execution.timeout_secs,
    )
    params = SpawnParams(
        prompt=run.prompt,
        model=run.model if str(run.model).strip() else None,
        skills=plan.skills,
        agent=plan.agent_name,
        adhoc_agent_payload=plan.adhoc_agent_payload,
        extra_args=plan.passthrough_args,
        repo_root=execution_cwd.as_posix(),
        mcp_tools=plan.mcp_tools,
        report_output_path=report_path.as_posix(),
        appended_system_prompt=plan.appended_system_prompt,
        continue_harness_session_id=plan.session.harness_session_id,
        continue_fork=plan.session.continue_fork,
    )
    return config, params
```

`SpawnManager.start_spawn()` passes both through to `connection.start(config, params)`.

## Drain Completion Detection

The streaming runner needs to know when the spawn finishes. Two mechanisms:

1. **Subscriber sentinel**: Subscribe a queue, wait for `None` (end-of-stream sentinel from drain task). This is what `streaming_serve.py` does.

2. **Drain task completion**: Await the drain task directly. When `connection.events()` exhausts (harness process exits), the drain task finishes, which triggers `SpawnManager._cleanup_completed_session`.

Use approach 1 (subscriber queue) — it's the designed fan-out mechanism and also provides the event stream for `--stream` output.

```python
subscriber = manager.subscribe(spawn_id)
assert subscriber is not None  # We just started it

completion_task = asyncio.create_task(_wait_for_sentinel(subscriber))
signal_task = asyncio.create_task(_wait_for_signal(shutdown_event))

done, pending = await asyncio.wait(
    {completion_task, signal_task},
    return_when=asyncio.FIRST_COMPLETED,
)
for t in pending:
    t.cancel()
```

## Terminal Output (--stream)

When `stream_stdout_to_terminal` is True, the subscriber queue also feeds a terminal printer. The streaming runner reads events from the queue and prints them before passing `None` through:

```python
async def _drain_to_terminal_and_wait(
    subscriber: asyncio.Queue[HarnessEvent | None],
) -> None:
    while True:
        event = await subscriber.get()
        if event is None:
            return
        # Print event in a useful format — matches the old stdout streaming
        _print_stream_event(event)
```

The `_print_stream_event` function should match the output format that the old `event_observer` callback produced, so `--stream` output looks the same.

## Signal Handling

Same pattern as `streaming_serve.py` but integrated with the retry loop:

```python
loop = asyncio.get_running_loop()
shutdown_event = asyncio.Event()
for sig in (signal.SIGINT, signal.SIGTERM):
    loop.add_signal_handler(sig, shutdown_event.set)
```

When shutdown fires during an active spawn, the runner calls `manager.stop_spawn()` which sends cancel to the connection and cleans up. The retry loop does not continue after a signal.

## Finalization

The streaming runner calls the same extraction functions as `runner.py` — no new `finalize.py` module (per D10). The shared code already lives in `extract.py` (`enrich_finalize`, `reset_finalize_attempt_artifacts`).

The key difference: the streaming runner passes a `StreamingExtractor` (not `SubprocessHarness`) to `enrich_finalize()`. This is the DIP fix (D14) — extraction is decoupled from the subprocess adapter layer.

```python
# In streaming_runner.py, after drain completion:
connection = manager.get_connection(spawn_id)
extractor = StreamingExtractor(connection=connection, harness_id=harness_id)

reset_finalize_attempt_artifacts(artifacts=artifacts, spawn_id=run.spawn_id, log_dir=log_dir)
extracted = enrich_finalize(
    artifacts=artifacts,
    extractor=extractor,  # was: adapter=harness_adapter
    spawn_id=run.spawn_id,
    log_dir=log_dir,
    secrets=secrets,
)
```

`enrich_finalize()` takes `extractor: SpawnExtractor` instead of `adapter: SubprocessHarness`. The old runner passes the subprocess adapter (which implicitly satisfies `SpawnExtractor`). The streaming runner passes `StreamingExtractor`. Neither knows about the other's implementation.

The terminal-state write stays inline in each runner — it's ~10 lines of `resolve_execution_terminal_state()` + `spawn_store.finalize_spawn()` and doesn't benefit from extraction.

### StreamingExtractor

```python
class StreamingExtractor:
    def __init__(self, connection: HarnessConnection, harness_id: HarnessId):
        self._connection = connection
        self._harness_id = harness_id

    def extract_session_id(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None:
        # Direct from connection state — no artifact parsing
        return self._connection.session_id

    def extract_usage(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> TokenUsage:
        # Parse from structured events in output.jsonl using unwrap_event_payload()
        # Delegates to the common extraction helper but envelope-aware
        return extract_usage_from_artifacts(artifacts, spawn_id)

    def extract_report(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None:
        # Report still comes from report.md on disk — delegates to common helper
        return extract_report_from_artifacts(artifacts, spawn_id)
```

Session ID is the big win — the connection already has it from the protocol handshake (Codex `thread_id`, OpenCode `session_id`). No parsing needed. Usage and report extraction delegate to the common helpers which are made envelope-aware.

### Envelope-Aware Extraction

`extract.py` gains an `unwrap_event_payload()` helper that all extractors use. This handles both the streaming envelope format and legacy raw format:

```python
def unwrap_event_payload(line: dict) -> dict:
    if "event_type" in line and "payload" in line:
        return line["payload"]
    return line
```

Extractors that parse `output.jsonl` (report content, token usage, written files, assistant messages) call this instead of reading top-level keys directly.

## Execution Path Routing in execute.py

```python
# In execute_spawn_blocking and _execute_existing_spawn:

resolved_harness_id = HarnessId(plan.harness_id)
harness = registry.get_subprocess_harness(resolved_harness_id)

if harness.capabilities.supports_bidirectional:
    exit_code = await execute_with_streaming(
        spawn,
        plan=resolved_plan,
        repo_root=runtime.repo_root,
        state_root=state_root,
        artifacts=runtime.artifacts,
        registry=runtime.harness_registry,
        cwd=runtime.repo_root,
        env_overrides=child_env,
        harness_session_id_observer=session_context.harness_session_id_observer,
        event_observer=event_observer,
        stream_stdout_to_terminal=stream_stdout_to_terminal,
        stream_stderr_to_terminal=payload.stream,
    )
else:
    exit_code = await execute_with_finalization(
        spawn,
        plan=resolved_plan,
        ...  # existing call unchanged
    )
```

Same routing in `execute_spawn_background` → `_execute_existing_spawn`.

## What Changes for Each Harness

### Codex (`supports_bidirectional=True`)

Currently: `meridian spawn -m codex` → `runner.py` → `codex --quiet -p "..."` subprocess → pipe capture.
After: `meridian spawn -m codex` → `streaming_runner.py` → `SpawnManager` → `CodexConnection` (WebSocket to `codex app-server`).

The subprocess is still launched — `CodexConnection.start()` launches `codex app-server` and connects via WebSocket. The difference is: events come via WebSocket (structured), not stdout pipe (text lines). Control socket exists. Inject works.

### Claude (`supports_bidirectional=True`)

Currently: `meridian spawn -m claude` → `runner.py` → `claude -p "..."` subprocess → pipe capture.
After: `meridian spawn -m claude` → `streaming_runner.py` → `SpawnManager` → `ClaudeConnection` (WebSocket server that Claude connects to).

### OpenCode (`supports_bidirectional=True`)

Currently: `meridian spawn -m opencode` → `runner.py` → `opencode` subprocess → pipe capture.
After: `meridian spawn -m opencode` → `streaming_runner.py` → `SpawnManager` → `OpenCodeConnection` (HTTP API to OpenCode server).

### Direct (`supports_bidirectional=False`)

No change. Direct harness has no connection implementation and continues through `runner.py`.

## Edge Cases

### Background worker process crash

If the background worker process dies mid-spawn, the `SpawnManager` dies with it. The control socket disappears. Orphan detection (PID-alive check) marks the spawn as failed. Same as today — crash-only design handles this.

### Connection fails but subprocess is alive

If the WebSocket/HTTP connection drops but the harness subprocess is still running, the `HarnessConnection` should detect this and emit an error event. The drain task catches the error and signals completion via the subscriber sentinel. The streaming runner's retry logic can then call `manager.stop_connection(spawn_id)` (which kills the orphaned subprocess) and attempt a new connection if the error is retryable.

### Multiple spawns in one process

`SpawnManager` already supports multiple concurrent spawns (it's a dict of sessions). A foreground spawn only runs one at a time, but the background worker could theoretically be extended. Not in scope — one spawn per manager instance for now.

### Port conflicts

`CodexConnection` and `ClaudeConnection` use port 0 (OS-assigned). No conflict possible.

### Existing output.jsonl format compatibility

The streaming drain writes structured event envelopes (`{event_type, harness_id, payload}`). The old path writes raw line-by-line stdout. After convergence, all streaming-capable harness output will be structured event envelopes. All extractors (`spawn log`, `enrich_finalize`, token extraction) use `unwrap_event_payload()` to handle both formats transparently.

### Harness writes report but keeps connection alive

The report watchdog detects `report.md` appearing, waits a grace period, then calls `manager.stop_spawn()`. This matches `runner.py`'s report-watchdog behavior. The spawn is treated as successfully completed (report exists).

### SIGTERM during finalization

The finally block masks SIGTERM before writing terminal state, preventing an interrupted atomic write from leaving the spawn non-terminal. Same as `runner.py`'s `signal_coordinator().mask_sigterm()`.

### Retry resets output.jsonl

Between retry attempts, `reset_finalize_attempt_artifacts()` clears `output.jsonl` and other per-attempt files. The drain task from the failed attempt is already stopped via `manager.stop_connection()` before the reset, so there's no race between old drain writes and the reset.

### Written files extraction from structured events

`enrich_finalize()` extracts written files from `output.jsonl`. With the envelope format, it must unwrap to get the raw payload before parsing. The `unwrap_event_payload()` helper handles this. Verify that each harness's connection implementation emits tool-use events that contain file paths in the same shape as the raw stdout stream — if not, the extraction logic needs harness-specific awareness of the structured event format.
