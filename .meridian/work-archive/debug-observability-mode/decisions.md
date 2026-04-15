# Decision Log: --debug Observability Mode

## D1: Separate structured tracer, not Python logging

**Decision:** Debug observability uses a dedicated `DebugTracer` class that writes structured JSONL, separate from Python's `logging` module.

**Reasoning:** The goal is structured wire-level traces with correlation context (spawn_id, layer, direction, timestamp) written to `{spawn_dir}/debug.jsonl`. Python logging is designed for human-readable diagnostic messages, not structured protocol traces. Mixing them conflates two concerns: operational logging ("connection failed") vs. protocol observability ("sent this JSON-RPC frame, got this response").

**Alternatives rejected:**
- **Python logging at DEBUG level**: Would require a custom `logging.Handler` that writes JSONL, a custom `logging.Formatter` that adds spawn_id/layer context, and careful configuration to route only debug-trace records to the file. This is more code, harder to test, and couples the trace format to Python's logging infrastructure. Additionally, `logger.debug()` calls have non-zero overhead even when disabled (function call + level check on every event), while a no-op tracer reference check is a single attribute test.
- **Structured logging library (structlog)**: Adds a dependency for a feature that needs exactly one write path (append JSONL line to file). Overkill.

**Constraint discovered:** The three adapters have fundamentally different I/O patterns (stdin/stdout, WebSocket, HTTP/SSE), so the tracer must be generic enough to capture wire traffic regardless of transport.

## D2: Tracer propagates via ConnectionConfig, not Protocol changes

**Decision:** Add `debug_tracer: DebugTracer | None = None` to `ConnectionConfig`. Each concrete connection reads it from config during `start()`. The `HarnessConnection` Protocol is unchanged.

**Reasoning:** `ConnectionConfig` is already the single input to `start()` and carries all per-spawn configuration. Adding the tracer here means:
- No Protocol signature changes (HarnessLifecycle, HarnessSender, HarnessReceiver all stay stable)
- No constructor signature changes on concrete classes
- The tracer is scoped per-spawn, which is correct since the debug file is per-spawn

**Alternatives rejected:**
- **Add tracer to `HarnessConnection` Protocol**: Protocol changes ripple to every consumer and implementation. A debug facility shouldn't change the core contract.
- **Global/module-level tracer**: No per-spawn isolation. Concurrent spawns would write interleaved events to a shared destination.
- **Wrapping proxy around connections**: Adds indirection and makes the connection type opaque to `SpawnManager`, complicating type checking and debugging (ironically).

## D3: Tracer wraps AG-UI mapping from the outside, not inside the Protocol

**Decision:** The `ws_endpoint._outbound_loop` traces around `mapper.translate()` calls rather than injecting the tracer into `AGUIMapper` implementations.

**Reasoning:** `AGUIMapper` is a Protocol with a clean `translate(event) -> list[BaseEvent]` signature. The ws_endpoint already has both the input event and the output events, so it can trace the translation without any mapper changes. This keeps mapper implementations pure and testable.

## D4: Default payload truncation at 4KB, not configurable in v1

**Decision:** Wire payloads in debug events are truncated to 4,096 bytes by default. No `--debug-full` flag in the first version.

**Reasoning:** Full wire payloads are already persisted in `output.jsonl`. The debug trace exists to correlate events across layers and spot protocol mismatches — you need to see the structure (type fields, method names, status codes), not the full assistant response text. 4KB is enough to capture any JSON envelope with meaningful fields while keeping the debug file small enough to `tail -f`.

**Deferral:** A `--debug-full` or `--debug-payload-limit` flag can be added later if truncation obscures real problems. Starting restrictive is safer than starting permissive — it's easy to expand later, hard to shrink if tools start depending on full payloads.

## D5: debug.jsonl file in spawn dir, optional stderr echo for CLI mode

**Decision:** Debug events write to `{spawn_dir}/debug.jsonl`. In `streaming_serve` CLI mode, events are also echoed to stderr. In `meridian app` server mode, file-only.

**Reasoning:** 
- File output is always available and doesn't pollute stdout (which is the CLI's JSON output channel).
- `streaming_serve` is interactive and users want live feedback — stderr echo is useful there.
- `meridian app` runs under uvicorn — stderr echo would interleave with uvicorn logs and be unreadable for concurrent spawns.

## D6: No-op tracer pattern for zero-overhead disabled path

**Decision:** When debug is disabled, `ConnectionConfig.debug_tracer` is `None`. Each instrumentation site does a single `if self._tracer is not None:` check before calling. No no-op class instantiated.

**Reasoning:** Considered a `NullTracer` that implements the interface with empty methods. This is cleaner OOP but means every instrumentation site still pays for a method call and argument construction. Since wire events happen at high frequency (every stdout line, every WebSocket frame), the `None` check is measurably cheaper and the code is still readable. The pattern is already used throughout the codebase (e.g., `if self._process is not None`).

---

## Review Round 1 Decisions (from p1269 gpt-5.4, p1270 opus, p1271 gpt-5.4 refactor-reviewer)

## D7: Move tracer to neutral package `lib/observability/`, not `lib/streaming/`

**Decision:** Place `DebugTracer` in `src/meridian/lib/observability/debug_tracer.py` instead of `lib/streaming/`.

**Reasoning (from refactor-reviewer p1271):** The tracer is consumed by `lib/harness/connections/` (wire hooks), `lib/streaming/` (drain hooks), and `lib/app/` (WebSocket hooks). Placing it in `lib/streaming/` makes harness connections depend upward on the streaming layer, reversing the natural dependency direction where streaming depends on harness. A neutral `lib/observability/` package has no directional coupling — any layer can import from it without creating circular dependencies.

**Alternative rejected:** Putting it in `lib/harness/connections/` was considered but that's equally wrong — the app/ws_endpoint layer would then depend on harness internals.

## D8: emit() must be non-raising and self-disabling

**Decision:** `emit()` wraps all internal operations in try/except, logs one warning on first failure, sets `_disabled = True`, and returns silently on all subsequent calls. The tracer must never crash the pipeline it observes.

**Reasoning (from correctness reviewer p1269):** The design stated this intent in the edge cases section but didn't specify it as a contract requirement. Since `emit()` is called inside hot async paths (WebSocket reads, request/response handlers, outbound translation), any unhandled exception would propagate into the streaming pipeline — turning a debug facility into an outage source.

## D9: Pass tracer directly to _drain_loop, not via SpawnSession lookup

**Decision:** `_drain_loop(spawn_id, receiver, tracer)` receives the tracer as a parameter. The tracer is also stored on `SpawnSession` for other uses (ws_endpoint access, cleanup).

**Reasoning (from both p1269 and p1270):** Current code creates the drain task (line 81) before registering SpawnSession (line 98). The earliest events — handshake, protocol validation — arrive before SpawnSession exists. These are exactly the events where protocol mismatches live. Passing directly eliminates the race.

## D10: Prerequisite — centralize Codex state transitions before adding hooks

**Decision:** Codex adapter gets a `_transition()` method as a prerequisite refactor before tracer hooks. This refactor is a separate phase from the debug feature itself.

**Reasoning (from p1270):** Codex mutates `self._state` directly at 7 sites. Adding a trace hook at each site duplicates the tracing call; centralizing first means one hook location. This follows the existing pattern in Claude (`_set_state`) and OpenCode (`_transition`).

## D11: Include truncated payload in mapper trace events

**Decision:** The mapper trace `translate_input` event includes the truncated `HarnessEvent.payload` and `raw_text` when available, not just `event_type`.

**Reasoning (from p1269):** The whole point of debug mode is diagnosing why events get dropped or mistranslated. Claude mapper drops `stream_event`s with missing nested fields by returning `[]`. With only `event_type` in the trace, you'd see "input was stream_event, output_count was 0" but not the malformed payload that caused the drop. The payload is where the diagnosis lives.

## D12: Add explicit parse_error/event_dropped traces for Codex and OpenCode

**Decision:** All three adapters emit a `parse_error` or `frame_dropped` event when raw input fails to parse or is discarded before reaching the drain loop.

**Reasoning (from p1269):** Claude already had this in the design. Codex silently returns `None` from `_parse_jsonrpc()` and continues; OpenCode does the same for malformed stream lines. Without a positive trace, you diagnose drops by absence — scanning for raw frames that have no corresponding parsed event. Explicit drop events make this immediate.

## D13: Separate event name for OpenCode path probing

**Decision:** OpenCode path probing (health checks, session creation endpoint discovery) uses event name `http_probe` instead of `http_post`. The `data` field includes `{is_probe: true, attempt: N, total_attempts: M}`.

**Reasoning (from p1270):** A single startup can produce 30+ trace events from path probing alone (2×2 session create, 4×3 action, 4 event stream paths). Using the same `http_post` event name makes it impossible to grep for real traffic vs. discovery noise. `http_probe` separates them.

## D14: SpawnManager owns tracer lifecycle; close() wired into cleanup paths

**Decision:** `SpawnManager` is the single lifecycle owner of the tracer. `close()` is called in both `_cleanup_completed_session()` and `stop_spawn()`, alongside existing resource cleanup. The CLI path creates the tracer but transfers ownership to SpawnManager by passing it through ConnectionConfig.

**Reasoning (from p1271 and p1270):** The design had split ownership — CLI creates, SpawnManager copies to SpawnSession, cleanup is vaguely assigned. This consolidates: SpawnManager creates the tracer (or receives it via config), stores it on SpawnSession, and is responsible for closing it when the session ends. For `meridian app`, this means unclosed handles don't accumulate across spawn lifecycles.

## D16: DebugTracer creates parent directories on lazy open

**Decision:** `DebugTracer._ensure_open()` creates parent directories (`path.parent.mkdir(parents=True, exist_ok=True)`) when opening the file handle for the first time.

**Reasoning (from convergence reviewer p1277):** The first trace event is `state_change(created→starting)`, which fires before `_start_subprocess()` creates the spawn directory. Without parent dir creation, the lazy open would fail on the first `emit()`, permanently disabling the tracer before it captures anything useful.

## D17: start_spawn() closes tracer on startup failure

**Decision:** `SpawnManager.start_spawn()` wraps `connection.start(config)` in a try/except that calls `tracer.close()` if the connection fails before SpawnSession is created.

**Reasoning (from convergence reviewer p1277):** In `meridian app` mode, SpawnManager creates a tracer for each spawn. If `connection.start()` raises, the SpawnSession is never created, so the cleanup paths in `_cleanup_completed_session()` and `stop_spawn()` never run. Repeated failed starts would leak file descriptors.

## D18: emit() serializes dict data values, then truncates the serialized string

**Decision:** `emit()` processes `data` dict values: string values are truncated directly; dict/list values are serialized to JSON first, then truncated; non-serializable values fall back to `repr()` then truncate.

**Reasoning (from convergence reviewer p1277):** The mapper trace passes `HarnessEvent.payload` as a dict, but `_truncate()` only handles strings. Without a serialization rule, either payloads go through unbounded or fall back to lossy `repr()`. Serializing first, then truncating, preserves the JSON structure up to the truncation point.

## D15: Centralize repetitive trace helpers, keep transport-specific extraction at call sites

**Decision:** Provide shared helpers for common trace patterns (state transition, parsed/dropped event) as module-level functions in the observability package. Adapters call these helpers at their transport-specific extraction points. No mixin, no proxy.

**Reasoning (from p1271):** The three adapters have structurally different I/O (stdin/stdout, WebSocket, HTTP/SSE), so a full proxy or mixin would need to abstract over all three — that's the wrong abstraction. But the trace event format (state_change, parse_error, frame_dropped) is identical across adapters. Extracting these into helpers like `trace_state_change(tracer, harness, from_state, to_state)` prevents drift in event naming and schema without forcing structural uniformity.

---

## Post-Streaming-Convergence Updates

The following decisions were made or updated during the design refresh for the post-convergence codebase. They supplement the original D1–D18 decisions above.

## D19: debug_tracer stays on ConnectionConfig, not SpawnParams

**Decision:** `debug_tracer: DebugTracer | None = None` is added to `ConnectionConfig`, not `SpawnParams`.

**Reasoning:** The streaming convergence split `start()` into `start(config: ConnectionConfig, params: SpawnParams)`. `SpawnParams` carries command-building config (model, skills, agent, effort, extra_args) — things that shape the harness CLI invocation. `ConnectionConfig` carries per-connection startup config (spawn_id, harness_id, model, prompt, repo_root, env_overrides, transport settings). The tracer is per-connection and scoped to a per-spawn file — it belongs with the connection config. This is a refinement of D2, not a reversal: the mechanism is the same (tracer on config, not on Protocol), but the "which config" question didn't exist pre-convergence.

**Alternatives considered:**
- **SpawnParams**: Wrong semantic bucket. SpawnParams is about building the harness command line. The tracer is consumed by the connection during its lifecycle, not during command construction.
- **Separate `DebugConfig` dataclass**: Adds a third config object to `start()`. The tracer is one optional field — a whole dataclass is overkill.

## D20: SpawnExtractor does not need tracer awareness

**Decision:** `SpawnExtractor` (protocol) and `StreamingExtractor` (implementation) are not instrumented with debug tracing.

**Reasoning:** The extractor runs after the connection finishes — it reads `session_id` from a live connection or falls back to artifact-based extraction (`extract_usage_from_artifacts`). It has no wire traffic, no I/O boundary mismatches, and no hot event path. The original design didn't address extractors because `SpawnExtractor` didn't exist pre-convergence. Post-convergence, adding tracer hooks here would be noise with no diagnostic value.

## D21: streaming_runner.py is transparent to the tracer

**Decision:** `streaming_runner.py` (including `run_streaming_spawn()` and `_run_streaming_attempt()`) requires zero debug-specific code changes. The tracer rides on `ConnectionConfig` from the CLI layer through to `SpawnManager.start_spawn(config, params)`.

**Reasoning:** The streaming runner's responsibilities — signal handling, heartbeat files, subscriber event consumption, timeout enforcement, budget tracking, watchdog — are orthogonal to debug tracing. The runner creates a `SpawnManager` and passes `config` to `start_spawn()`. SpawnManager extracts the tracer from config. On shutdown, `manager.shutdown()` → `stop_spawn()` closes any active tracers. No runner code touches the tracer directly.

This is the correct layering: the runner is an orchestration layer that composes SpawnManager, signals, and timeouts. The tracer is a per-connection concern owned by SpawnManager. Mixing them would couple debug instrumentation to orchestration logic.

## D22: Tracer close aligns with completion_future/DrainOutcome lifecycle

**Decision:** Tracer `close()` is called in three paths, all aligned with the post-convergence DrainOutcome pattern:

1. **`_cleanup_completed_session()`** — natural drain exit. Called after `_resolve_completion_future()` sets the DrainOutcome on the session's `completion_future`.
2. **`stop_spawn()`** — forced stop. Called after `_resolve_completion_future()` but before `connection.stop()` and `drain_task.cancel()`.
3. **`start_spawn()` except block** — startup failure. Called if `connection.start(config, params)` or `control_server.start()` raises before SpawnSession is created.

**Reasoning:** The original D14/D17 decisions specified tracer close in cleanup paths, but the cleanup paths themselves changed. Pre-convergence, there was no `completion_future` or `DrainOutcome` — the manager called `spawn_store.finalize_spawn()` directly. Post-convergence, SpawnManager never calls `finalize_spawn()` (single-writer finalization: the runner owns that). Instead, the drain loop resolves a `completion_future: asyncio.Future[DrainOutcome]` and schedules `_cleanup_completed_session()`. The `stop_spawn()` path resolves the future then cleans up resources.

Tracer close must happen AFTER the completion future is resolved (so the last drain events are captured) but BEFORE connection.stop() (so the tracer file handle is released before the process exits). This ordering is guaranteed by the existing cleanup sequence in both paths.

## D23: Three CLI entry points for --debug

**Decision:** `--debug` is supported on three commands: `meridian spawn --debug`, `meridian streaming serve --debug`, and `meridian app --debug`. On `meridian spawn`, the flag is hidden from agent mode (like `--stream`).

**Reasoning:** Pre-convergence, the design only covered `streaming serve` and `app` because `meridian spawn` didn't route through the streaming pipeline. Post-convergence, `meridian spawn` is the primary spawn path and routes through the streaming pipeline via `execute_with_streaming()` (see D24 for the corrected execution path). Omitting `--debug` from the most-used command would defeat the purpose.

The `--debug` flag on `meridian spawn` is hidden (`show=False`) because agents should never enable debug mode — it's a developer diagnostic tool. This matches the existing `--stream` flag pattern.

`echo_stderr` behavior per path:
- `meridian spawn` (foreground): `echo_stderr=True` — user wants live feedback
- `meridian spawn --background`: `echo_stderr=False` — no terminal to echo to
- `meridian streaming serve`: `echo_stderr=True` — interactive headless mode
- `meridian app`: `echo_stderr=False` — would interleave with uvicorn logs

## Execution Path Correction (v2)

The following decisions correct the execution path analysis from the v1 post-convergence update. The v1 update assumed `meridian spawn` routes through `run_streaming_spawn()` and that the CLI layer constructs `ConnectionConfig`. Codebase tracing reveals `meridian spawn` routes through `execute_with_streaming()` which constructs `ConnectionConfig` internally, requiring `--debug` to propagate through the ops layer.

## D24: --debug propagates through ops layer, not just CLI surface

**Decision:** For `meridian spawn`, the `--debug` flag is added to `SpawnCreateInput` and threaded through `execute_spawn_blocking()` / `execute_spawn_background()` → `BackgroundWorkerParams` → `_execute_existing_spawn()` → `execute_with_streaming(debug=True)`. The tracer is created inside `execute_with_streaming()` alongside `ConnectionConfig` construction. For `streaming_serve` and `app`, the original propagation (CLI-level tracer creation or SpawnManager `debug` flag) remains correct.

**Reasoning:** Codebase tracing reveals the actual spawn execution flow:
```
spawn.py → spawn_create_sync() → execute_spawn_blocking()
  → execute_with_streaming()    # constructs ConnectionConfig at line 760
    → SpawnManager.start_spawn(config, params)
```

`execute_with_streaming()` constructs `ConnectionConfig` internally from `Spawn` + `PreparedSpawnPlan` at line 760 of `streaming_runner.py`. The CLI layer (`spawn.py`) never touches `ConnectionConfig` — it builds a `SpawnCreateInput` and passes it to the ops layer. The original D23 design assumed the CLI constructs `ConnectionConfig` directly (as `streaming_serve` does), but that's only true for `streaming_serve` and `app` paths.

This means `SpawnCreateInput` needs a `debug: bool = False` field, and every layer between `spawn_create_sync()` and `execute_with_streaming()` must forward it. For background spawns, `BackgroundWorkerParams` must also persist the flag so the background worker process can restore it.

**Impact on D23:** D23 is refined, not reversed. The three CLI entry points remain the same. What changes is HOW `--debug` reaches the tracer creation point for `meridian spawn` specifically — through ops layer forwarding rather than direct `ConnectionConfig` construction.

## D25: Tracer survives retries — reuse across execute_with_streaming retry loop

**Decision:** `execute_with_streaming()` creates one `DebugTracer` before the retry loop and reuses it across retries via the same `ConnectionConfig` object. The tracer is NOT recreated per retry.

**Reasoning:** `execute_with_streaming()` has a retry loop (line 837). Each retry calls `_run_streaming_attempt()` → `manager.start_spawn(config, params)`. Between retries, `stop_spawn()` closes the tracer (via `SpawnSession` cleanup). On the next retry, `start_spawn()` extracts the same tracer from `config`.

Since `DebugTracer` uses lazy file open (`_ensure_open()` on first `emit()`), a closed-and-reopened tracer transparently reopens the file in append mode. The gap in events between retries is diagnostic — it shows where the retry boundary is. Creating a new tracer per retry would either overwrite the file or require unique filenames, both worse than the append-reopen pattern.

**Alternative rejected:** Creating a new `DebugTracer` per retry with unique filenames (`debug-attempt-1.jsonl`, `debug-attempt-2.jsonl`). This fragments the trace, making cross-attempt correlation harder. A single file with an implicit gap is simpler to analyze.

## D26: echo_stderr follows stream_stdout_to_terminal for meridian spawn

**Decision:** In `execute_with_streaming()`, the tracer's `echo_stderr` flag is set to the value of `stream_stdout_to_terminal` — True only when the user passed `--stream` on a foreground spawn.

**Reasoning:** `stream_stdout_to_terminal` (set by `--stream` flag on `meridian spawn`) indicates the user wants live output. Aligning `echo_stderr` with this flag means debug trace echo only appears when the user has opted into verbose output. Without `--stream`, spawn output is silent (just the spawn ID JSON), and debug trace to stderr would be surprising noise.

For `streaming_serve`, `echo_stderr=True` always (interactive mode). For `app`, `echo_stderr=False` always (server mode, would interleave with uvicorn). This is consistent with D23's original per-path policy, just refined for the `meridian spawn` path where the decision is context-dependent.
