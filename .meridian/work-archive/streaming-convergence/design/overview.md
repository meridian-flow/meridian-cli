# Streaming Convergence — Design

## Problem

The Phase 1 design ([agent-shell-mvp/design/phase-1-streaming.md](../../agent-shell-mvp/design/phase-1-streaming.md)) specified that bidirectional streaming is **universal**: every spawn gets a `HarnessConnection`, a durable drain, and a control socket. The design explicitly states:

> Per D41, bidirectionality is universal — not a flag, not a mode, not a new invocation shape. Every spawn launched after Phase 1 gets a HarnessConnection and a control socket.

The implementation violated this. Three completely separate execution pipelines exist:

1. **Primary path** (`meridian` → `launch/__init__.py` → `process.py` → PTY fork/exec): Interactive terminal session. Launches harness via PTY, proxies stdin/stdout between user and process. No connection, no drain, no control socket.

2. **Child spawn path** (`meridian spawn` → `execute.py` → `runner.py` → `spawn_and_stream`): Launches harness as a raw subprocess, captures stdout/stderr via pipes, no websocket/HTTP connection, no drain task, no control socket, no inject capability.

3. **Streaming path** (`meridian streaming serve` / `meridian app` → `SpawnManager` → `HarnessConnection`): Uses bidirectional connections (websocket for Claude/Codex, HTTP for OpenCode), durable drain to `output.jsonl`, control socket, inject support.

Result: `meridian spawn inject` is dead code for all normal spawns AND the primary session. The streaming pipeline is only reachable through `streaming serve` (a test command) and `app` (the web UI). Neither `meridian spawn` nor `meridian` (primary) — the two commands everyone actually uses — have any bidirectional capabilities.

## Goal

Converge **child spawns** to the streaming pipeline. Primary sessions stay on PTY.

After this work:

- `meridian spawn -m codex -p "..."` creates a `HarnessConnection`, gets a control socket, drains structured events to `output.jsonl`
- `meridian spawn inject p1234 "change approach"` works against any running child spawn
- The old subprocess-only path through `runner.py` → `spawn_and_stream` is eliminated for harnesses that support bidirectional connections
- `meridian app` continues to work — it already uses `SpawnManager`
- The structured event stream from child spawns becomes the building block for future app UI integration (observe/steer any spawn from the web interface)

**Not in scope**: Primary session (`meridian`) convergence. Primary sessions keep the PTY path and the harness's native TUI. Building our own TUI renderer to reconstruct each harness's interactive experience from structured events is not worth the effort or maintenance burden — the app (`meridian app`) is where we control the UI.

## Architecture

### Current State (3 separate paths)

```
meridian (primary interactive)
  └─ launch/__init__.py → process.py
       └─ PTY fork/exec (raw terminal proxy)
            ├─ stdin/stdout via PTY master fd
            ├─ output.jsonl (raw byte capture)
            ├─ heartbeat
            └─ report + session ID extraction on exit

meridian spawn (child)
  └─ execute.py → runner.py
       └─ spawn_and_stream (raw subprocess, pipe capture)
            ├─ stdout → output.jsonl (line-by-line)
            ├─ stderr → stderr.log
            ├─ heartbeat
            └─ report extraction on exit

meridian streaming serve / meridian app
  └─ SpawnManager
       └─ HarnessConnection (codex_ws / claude_ws / opencode_http)
            ├─ drain task → output.jsonl (structured events)
            ├─ fan-out → subscriber queues
            ├─ ControlSocketServer → control.sock
            └─ finalize on drain exit
```

### Target State

```
meridian (primary)
  └─ process.py → PTY fork/exec (UNCHANGED)
       └─ Native harness TUI, raw byte capture

meridian spawn (child) / meridian app / streaming serve
  └─ streaming_runner.py: execute_with_streaming
       └─ SpawnManager.start_spawn(config)
            └─ HarnessConnection (codex_ws / claude_ws / opencode_http)
                 ├─ drain task → output.jsonl (structured events)
                 ├─ fan-out → subscriber queues
                 ├─ ControlSocketServer → control.sock
                 ├─ heartbeat
                 └─ finalization (report extraction, spawn_store update)
```

Three entry points share the `SpawnManager` → `HarnessConnection` pipeline. The difference is what consumes the fan-out:

- **Child spawn foreground**: Subscriber optionally prints events (`--stream`)
- **Child spawn background**: No subscriber (events drain to `output.jsonl` only)
- **App/streaming serve**: Subscriber feeds WebSocket to UI client

Primary sessions keep the PTY path — the harness owns the terminal UX. The `direct` harness (and any future non-bidirectional harness) also keeps the old `runner.py` → `spawn_and_stream` path.

**Future**: The structured event stream from child spawns is what enables the app to observe and steer any spawn from the web UI. When `meridian app` gains a spawn dashboard, it reads the same event stream that `inject` writes to.

### Why Primary Sessions Stay on PTY

Primary sessions (`meridian` with no subcommand) use a PTY to give the harness full control of the terminal. Claude Code, Codex, and OpenCode all have their own TUIs — input boxes, tool approval prompts, thinking indicators, markdown rendering. The PTY proxy in `process.py` is completely transparent: it ferries bytes between the user's terminal and the harness's rendering.

Switching to the streaming pipeline would mean launching the harness in programmatic API mode (e.g., `codex app-server`, `claude --ide`). The harness never gets the terminal. We'd have to reconstruct every harness's TUI from their structured event protocol — a massive effort that would always lag behind the native experience.

The right place for a meridian-controlled UI is `meridian app` (web), not a terminal renderer. Primary sessions keep the PTY; spawns converge to streaming; the app is where we own the rendering.

### Key Integration Points

#### 1. SpawnManager Lifecycle in execute.py

Currently, `SpawnManager` instances are created ad-hoc by `streaming_serve.py` and `server.py`. For convergence, `execute_spawn_blocking` and `execute_spawn_background` need access to a `SpawnManager`.

**For foreground spawns**: Create a short-lived `SpawnManager` scoped to the execution. It starts, runs the spawn to completion, and shuts down. This is what `streaming_serve.py` already does — the pattern just moves into `execute.py`.

**For background spawns**: The background worker process (`_background_worker_main`) creates its own `SpawnManager`. Same pattern — one manager per spawn, scoped to the worker process lifetime. No long-lived daemon needed.

#### 2. Finalization Ownership — Single Writer

The old path (`runner.py`) handles substantial finalization logic:
- Report extraction (`enrich_finalize`)
- Session ID extraction (`extract_latest_session_id`)
- Retry logic (guardrail failures, transient errors)
- Budget tracking
- Written files extraction
- Token usage extraction

The current `SpawnManager._drain_loop` **also** finalizes: it calls `spawn_store.finalize_spawn()` when the drain exits and cleans up the control socket. This creates a double-finalization problem — the manager writes "succeeded" before the runner can check for missing reports, guardrail failures, or budget breaches.

**Fix**: Remove `spawn_store.finalize_spawn()` from `SpawnManager` entirely. The manager signals drain completion to the caller (via the subscriber sentinel or a returned future) but does **not** write terminal state. The runner is the single owner of finalization — it runs the full pipeline (extraction, guardrails, budget, retry decisions) and writes the one authoritative `finalize_spawn()` call.

`SpawnManager` keeps control socket cleanup and session dict cleanup (it needs to remove the `SpawnSession` entry so resources are freed), but terminal-state writes in `spawn_store` are the runner's job.

**Convergence approach**: `streaming_runner.py` wraps `SpawnManager` with the finalization logic from `runner.py`. The streaming runner:

1. Creates `SpawnManager` + starts spawn (gets `HarnessConnection`)
2. Waits for drain completion (subscriber sentinel)
3. Resolves `SubprocessHarness` adapter from `registry.get_subprocess_harness(harness_id)` for extraction
4. Runs the same finalization pipeline as `runner.py`: report extraction, session ID extraction, token extraction, written files
5. Handles retry logic (restart connection on retryable failures)
6. Writes the single authoritative `spawn_store.finalize_spawn()` with SIGTERM masked

This keeps `SpawnManager` thin (connections + drain + fan-out) and puts execution policy (retries, budgets, guardrails, finalization) in the runner layer.

#### 3. Extraction Protocol (DIP fix)

`enrich_finalize()` currently takes `adapter: SubprocessHarness` and calls `adapter.extract_usage()`, `adapter.extract_session_id()`, `adapter.extract_report()`. These methods parse raw subprocess artifacts — a dependency the streaming path shouldn't have.

**Fix**: Extract a `SpawnExtractor` protocol from the three extraction methods. Both `SubprocessHarness` and a new `StreamingExtractor` satisfy it. `enrich_finalize()` takes the protocol instead of the concrete adapter.

```python
@runtime_checkable
class SpawnExtractor(Protocol):
    """Artifact extraction interface for spawn finalization."""
    def extract_usage(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> TokenUsage: ...
    def extract_session_id(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None: ...
    def extract_report(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None: ...
```

`SubprocessHarness` already satisfies this protocol — no changes needed to the old adapters.

`StreamingExtractor` wraps a `HarnessConnection` and implements extraction from structured events and connection state:

```python
class StreamingExtractor:
    """SpawnExtractor implementation for streaming connections."""
    
    def __init__(self, connection: HarnessConnection, harness_id: HarnessId):
        self._connection = connection
        self._harness_id = harness_id

    def extract_session_id(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None:
        # Connections already know the session ID from the protocol handshake:
        # - Codex: thread_id from thread/start response
        # - OpenCode: session_id from POST /session
        # - Claude: extractable from event stream
        return self._connection.session_id  # new property on HarnessConnection

    def extract_usage(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> TokenUsage:
        # Parse from structured events in output.jsonl (envelope-aware)
        # Falls back to common extraction if events don't carry usage
        ...

    def extract_report(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None:
        # Report still comes from report.md on disk — same as subprocess path
        # Alternatively, extract from assistant message events if no file exists
        ...
```

The old runner passes `registry.get_subprocess_harness(harness_id)` as the extractor. The streaming runner passes `StreamingExtractor(connection, harness_id)`. `enrich_finalize` doesn't know or care which path produced the artifacts.

#### 4. Report Extraction

Report extraction works identically on both paths — the harness writes `report.md` to the spawn log directory, and `extract_or_fallback_report()` reads it. The `SpawnExtractor.extract_report()` method handles fallback (extracting from assistant messages in `output.jsonl` if no file exists), and the envelope-aware `unwrap_event_payload()` helper makes this work for structured event output.

#### 5. Session ID Extraction

The streaming connections already track the session ID from the protocol handshake:
- **Codex**: `thread_id` from `thread/start` response (already stored as `self._thread_id`)
- **OpenCode**: `session_id` from `POST /session` (already stored as `self._session_id`)
- **Claude**: extractable from the WebSocket event stream

`HarnessConnection` gains a `session_id: str | None` property that exposes this. `StreamingExtractor.extract_session_id()` returns it directly — no artifact parsing needed. The old path continues extracting from artifacts via `SubprocessHarness.extract_session_id()`.

#### 5. ConnectionConfig + SpawnParams (ISP fix)

The current `ConnectionConfig` has 12 fields for transport concerns: spawn identity, harness type, prompt, connection parameters. Adding 6 more harness-specific command-building fields (report path, MCP tools, agent payload, etc.) would turn it into a god-config mixing transport setup with subprocess command construction.

**Fix**: `HarnessConnection.start()` takes **both** `ConnectionConfig` (transport) and `SpawnParams` (command building). `ConnectionConfig` stays focused on transport. `SpawnParams` already exists and is the right shape for building harness commands — it's what `SubprocessHarness.build_command()` uses today.

```python
# ConnectionConfig stays clean (transport essentials only):
@dataclass(frozen=True)
class ConnectionConfig:
    spawn_id: SpawnId
    harness_id: HarnessId
    model: str | None
    prompt: str
    repo_root: Path
    env_overrides: dict[str, str]
    timeout_seconds: float | None = None
    ws_bind_host: str = "127.0.0.1"
    ws_port: int = 0

# HarnessConnection.start() takes both:
async def start(self, config: ConnectionConfig, params: SpawnParams) -> None: ...
```

The connection uses `config` for transport setup (bind host, port, timeout, env) and `params` for building the harness subprocess command (model, skills, agent, report path, MCP tools, etc.). Each connection implementation picks the `params` fields it needs — same as `SubprocessHarness.build_command()` does today. No field duplication, each interface focused on its concern.

The streaming runner builds both from the `PreparedSpawnPlan`:

```python
config = ConnectionConfig(
    spawn_id=run.spawn_id, harness_id=HarnessId(plan.harness_id),
    model=str(run.model) or None, prompt=run.prompt,
    repo_root=execution_cwd, env_overrides=merged_env_overrides,
    timeout_seconds=plan.execution.timeout_secs,
)
params = SpawnParams(
    prompt=run.prompt, model=run.model, skills=plan.skills,
    agent=plan.agent_name, adhoc_agent_payload=plan.adhoc_agent_payload,
    extra_args=plan.passthrough_args, repo_root=execution_cwd.as_posix(),
    mcp_tools=plan.mcp_tools, report_output_path=report_path.as_posix(),
    appended_system_prompt=plan.appended_system_prompt,
    continue_harness_session_id=plan.session.harness_session_id,
    continue_fork=plan.session.continue_fork,
)
```

Existing fields that are currently on `ConnectionConfig` but belong to command-building (`agent`, `skills`, `extra_args`, `continue_session_id`) move to `SpawnParams` only. `ConnectionConfig` shrinks to ~9 fields.

#### 6. Report Watchdog

`runner.py` has a report watchdog: if the harness writes `report.md` but the process keeps running, the watchdog sends SIGTERM after a grace period. Finalization then treats the post-report SIGTERM as success (not a failure).

The streaming path replaces subprocess management with "wait for drain completion." If a harness writes the report but keeps the connection alive (e.g., Codex keeps the WebSocket open after the turn completes), the spawn hangs indefinitely.

**Fix**: The streaming runner watches for `report.md` appearing in the spawn log directory. When detected:
1. Start a grace timer (same duration as `runner.py`'s report watchdog)
2. If the drain completes within the grace period, normal exit
3. If the grace period expires, call `manager.stop_spawn()` — this sends cancel and closes the connection
4. Treat this as a successful completion (report exists, harness was just slow to disconnect)

This preserves `runner.py`'s "durable report completion" semantics exactly.

#### 7. PID Bookkeeping

The orphan reaper (`reaper.py`) detects stale foreground spawns by checking `worker_pid` and `harness.pid`. If neither exists after the startup grace period, the spawn is marked failed. The current `HarnessConnection` protocol has no PID exposure — a running streaming spawn gets incorrectly reaped.

**Fix**: Add a `subprocess_pid` property to `HarnessConnection` (returns `int | None`). Each connection implementation exposes the PID of the harness process it launched (e.g., `CodexConnection._process.pid`). The streaming runner writes `harness.pid` after `start()` returns, same as the old path. The reaper's PID-alive check then works identically.

```python
# In streaming_runner.py, after start_spawn:
connection = manager.get_connection(spawn_id)
if connection is not None and connection.subprocess_pid is not None:
    atomic_write_text(log_dir / "harness.pid", f"{connection.subprocess_pid}\n")
    spawn_store.mark_spawn_running(state_root, spawn_id, worker_pid=connection.subprocess_pid)
```

#### 8. output.jsonl Envelope Format

The streaming drain writes `{event_type, harness_id, payload}` envelopes. The old path writes raw harness stdout (line-by-line, no envelope). Extractors like `spawn log`, report extraction, and token extraction currently parse raw top-level payloads. After convergence, they'll see envelopes instead.

**Fix**: Codify the envelope as the canonical `output.jsonl` format. Add a shared unwrap helper:

```python
def unwrap_event_payload(line: dict) -> dict:
    """Extract the effective payload from an output.jsonl line.
    
    Handles both envelope format (streaming drain) and raw format (legacy).
    """
    if "event_type" in line and "payload" in line:
        return line["payload"]  # envelope
    return line  # raw legacy
```

All extractors (`spawn log`, `enrich_finalize`, token extraction, written files extraction) call this helper instead of reading top-level keys directly. Both formats work — new streaming output and legacy raw output.

#### 9. Heartbeat

The old path uses `heartbeat_scope` (async context manager that touches a file periodically). The streaming path doesn't have this. The streaming runner should wrap the spawn lifetime in `heartbeat_scope` — same mechanism, just around `SpawnManager` instead of `spawn_and_stream`.

#### 10. Signal Handling

The old path uses `signal_coordinator` for SIGINT/SIGTERM forwarding to the subprocess. The streaming path needs equivalent handling: on signal, call `SpawnManager.stop_spawn()` which sends cancel to the connection and cleans up. `streaming_serve.py` already does this pattern.

Additionally, the finally block must mask SIGTERM during the finalization write (same as `runner.py`'s `signal_coordinator().mask_sigterm()`). Without this, a SIGTERM arriving during `spawn_store.finalize_spawn()` can interrupt the atomic write and leave the spawn in a non-terminal state.

## New Files

| File | Purpose |
|---|---|
| `lib/launch/streaming_runner.py` | `execute_with_streaming()` — streaming equivalent of `execute_with_finalization()`. Wraps `SpawnManager` with finalization, retry, budget, heartbeat, report watchdog, and signal handling. |
| `lib/harness/extractor.py` | `SpawnExtractor` protocol + `StreamingExtractor` implementation. Decouples extraction from `SubprocessHarness`. |

## Modified Files

| File | Change |
|---|---|
| `lib/ops/spawn/execute.py` | Route to `execute_with_streaming` when harness `supports_bidirectional=True`. Fall back to `execute_with_finalization` otherwise. |
| `lib/harness/adapter.py` | Ensure `supports_bidirectional` flag exists on `HarnessCapabilities` (may already be there). |
| `lib/harness/claude.py` | Set `supports_bidirectional=True` on Claude adapter capabilities. |
| `lib/harness/codex.py` | Set `supports_bidirectional=True` on Codex adapter capabilities. |
| `lib/harness/opencode.py` | Set `supports_bidirectional=True` on OpenCode adapter capabilities. |
| `lib/harness/connections/base.py` | Add `subprocess_pid` and `session_id` properties to `HarnessConnection` protocol. Shrink `ConnectionConfig` to transport-only fields. Update `start()` signature to take `(config, params)`. |
| `lib/harness/connections/codex_ws.py` | Implement `subprocess_pid`, `session_id`. Accept `SpawnParams` in `start()`. Use `params` for command building instead of `ConnectionConfig` fields. |
| `lib/harness/connections/claude_ws.py` | Same — `subprocess_pid`, `session_id`, `start(config, params)`. |
| `lib/harness/connections/opencode_http.py` | Same — `subprocess_pid`, `session_id` (already tracked as `_session_id`), `start(config, params)`. |
| `lib/harness/adapter.py` | Extract `SpawnExtractor` protocol from `SubprocessHarness`'s 3 extraction methods. `SubprocessHarness` implicitly satisfies it. |
| `lib/streaming/spawn_manager.py` | Remove `spawn_store.finalize_spawn()` from drain loop cleanup. Expose drain completion to caller without writing terminal state. Add `stop_connection()` variant that cleans up without finalizing (for retry). Update `start_spawn()` to pass `SpawnParams` through to connection. |
| `lib/launch/runner.py` | Use `SpawnExtractor` protocol in finalization. Functionally identical — `SubprocessHarness` already satisfies the protocol. |
| `lib/launch/extract.py` | Take `SpawnExtractor` instead of `SubprocessHarness` in `enrich_finalize()`. Add `unwrap_event_payload()` helper for envelope-aware extraction. |
| `lib/ops/spawn/log.py` | Use `unwrap_event_payload()` for envelope-aware `spawn log` output. |
| `cli/streaming_serve.py` | Rewrite as thin wrapper around `execute_with_streaming`, or deprecate. Eliminates drift from a third execution path. |

## Files NOT Modified

| File | Why |
|---|---|
| `lib/streaming/control_socket.py` | Already correct. |
| `cli/spawn_inject.py` | Already correct — it connects to the control socket, which will now exist for all streaming spawns. |

## Decisions

**D1: One SpawnManager per spawn process, not a long-lived daemon.**
Each foreground or background spawn creates and owns its `SpawnManager`. No shared daemon, no IPC to a central coordinator. This matches the crash-only design — if the process dies, the manager dies with it, and orphan detection picks up the rest. The `app` server's manager is separate and manages spawns it creates.

**D2: Route selection via `supports_bidirectional` capability flag.**
The harness adapter's `HarnessCapabilities.supports_bidirectional` flag determines which execution path to use. This is the design's original approach — not a mode, not a flag on the spawn, but a harness capability.

**D3: Finalization logic lives in the runner, not the manager. Single writer.**
`SpawnManager` stays a thin connection registry + drain coordinator. It **does not** call `spawn_store.finalize_spawn()` — that's the runner's job. The manager signals drain completion and cleans up its own resources (session dict, control socket), but terminal-state writes in spawn_store are exclusively the runner's responsibility. This eliminates the double-finalization race where the manager's "succeeded" lands before the runner checks for missing reports or guardrail failures. The `app` server's usage of `SpawnManager` must also be updated — it currently relies on the manager's auto-finalization.

**D4: Old path retained for non-bidirectional harnesses.**
`runner.py` → `spawn_and_stream` is not deleted. The `direct` harness (and any future non-bidirectional harness) still needs it. The routing in `execute.py` picks the right path based on the capability flag.

**D5: Retry via connection restart, not subprocess restart.**
When a streaming spawn fails with a retryable error, the streaming runner creates a new `HarnessConnection` (which launches a new subprocess internally) rather than restarting the old subprocess. This matches how connections work — they own their subprocess lifecycle.

Between retry attempts, the runner calls `manager.stop_connection(spawn_id)` (new method) which stops the connection and drain task **without** finalizing the spawn in spawn_store. This avoids the problem where `shutdown()` writes terminal state between retries, making it impossible to restart with the same spawn ID. The manager removes the `SpawnSession` entry so `start_spawn()` can create a fresh one on the next attempt.

**D6: `--stream` flag maps to drain subscriber.**
When `--stream` is passed to a foreground spawn, the streaming runner subscribes to the drain's fan-out queue and prints events to the terminal. This replaces the old `stream_stdout_to_terminal` piping.

**D7: `streaming serve` is collapsed onto the canonical path.**
After convergence, `streaming_serve.py` is rewritten as a thin wrapper around `execute_with_streaming` — same args, same behavior, but going through the canonical execution path instead of being a parallel implementation. This prevents a third execution path from drifting. If the wrapper adds no value over `meridian spawn --foreground`, deprecate it.

**D8: Primary sessions stay on PTY — not in scope.**
The primary interactive session (`meridian`) keeps the PTY path. Harnesses own their TUI (Claude Code, Codex, OpenCode all render their own interactive terminal UI). Reconstructing these TUIs from structured events is not worth the effort — `meridian app` is where we control the rendering. The 90% win (all child spawns becoming injectable via structured event streams) doesn't require solving the primary TUI problem.

**D9: The event stream is the bridge to the app UI.**
Child spawn events drain to `output.jsonl` as structured `HarnessEvent` envelopes. This is the same format the app already consumes. When the app gains a spawn dashboard, it reads these events to observe and steer any spawn — no new protocol needed.

**D10: No new `finalize.py` — extend `extract.py` instead.**
Reviewers flagged that a new `finalize.py` wrapping `extract.py` adds an indirection without a real boundary. Instead, extend `extract.py` with the `unwrap_event_payload()` helper and keep extraction logic consolidated there. The terminal-state write (`resolve_execution_terminal_state` + `spawn_store.finalize_spawn`) stays inline in each runner — it's 10 lines and doesn't benefit from extraction.

**D11: Envelope format is the canonical `output.jsonl` schema.**
After convergence, all streaming-capable harness output uses `{event_type, harness_id, payload}` envelopes. A shared `unwrap_event_payload()` helper in `extract.py` handles both envelope and legacy raw formats, so extractors work on old and new spawns. The legacy raw format is only produced by the `direct` harness path going forward.

**D12: Budget tracking via subscriber callback.**
Real-time budget enforcement uses a callback on the subscriber loop in `streaming_runner.py` that extracts cost from structured events. This replaces `runner.py`'s `LiveBudgetTracker.observe_json_line()` which operates on raw stdout bytes. Post-hoc budget checking (from extracted usage after completion) works identically to `runner.py`.

**D13: Connections expose subprocess PID and session ID.**
`HarnessConnection` gains `subprocess_pid: int | None` and `session_id: str | None` properties. The streaming runner writes `harness.pid` after connection start (preserving reaper's PID-alive detection). The session ID is used by `StreamingExtractor` — no artifact parsing needed.

**D14: `SpawnExtractor` protocol decouples extraction from `SubprocessHarness` (DIP).**
The three extraction methods (`extract_usage`, `extract_session_id`, `extract_report`) become a standalone protocol. `SubprocessHarness` implicitly satisfies it (no changes). `StreamingExtractor` implements it using connection state + structured events. `enrich_finalize()` takes the protocol. This eliminates the streaming path's dependency on the subprocess adapter layer.

**D15: `ConnectionConfig` stays transport-only, `SpawnParams` handles command building (ISP).**
Instead of bloating `ConnectionConfig` with harness-specific command fields, `HarnessConnection.start()` takes both `ConnectionConfig` (transport: bind host, port, timeout, env) and `SpawnParams` (command: model, skills, agent, report path, MCP tools). Each connection picks the `SpawnParams` fields it needs. `ConnectionConfig` shrinks from 12 fields (with planned additions to 18) to ~9. No god-config.
