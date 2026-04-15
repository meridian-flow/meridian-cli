# Design: --debug Observability Mode

> **Updated for post-streaming-convergence codebase (v2).** The core design (DebugTracer contract, JSONL schema, shared trace helpers, per-adapter hooks) is unchanged. This update corrects execution path routing: `meridian spawn` routes through `execute_with_streaming()` (not `run_streaming_spawn()`), which constructs `ConnectionConfig` internally. The `--debug` flag must therefore propagate through the ops layer, not just the CLI surface.

## Problem

The meridian streaming pipeline has four layers between the harness process and the UI client. When a harness adapter speaks the wrong protocol — wrong JSON-RPC method, wrong field names, wrong message framing — the failure manifests as a crash or hang with no indication of what the harness actually sent or what we actually sent to it.

All three harness adapters shipped with wrong protocols because nobody could see the wire traffic. This design adds structured wire-level observability to every layer.

## Pipeline Layers

```
HarnessConnection          SpawnManager._drain_loop       ws_endpoint._outbound_loop
(per-harness adapter)      (event persistence + fan-out)  (AG-UI mapper + WebSocket)
                                                          
  claude stdin/stdout  ──>  append output.jsonl  ──>  mapper.translate()  ──>  WS send
  codex  WebSocket     ──>  fan-out to subscriber  ──>  (harness event → AG-UI events)
  opencode HTTP/SSE    ──>                                                    
```

Each boundary is an integration point where protocol mismatches hide. The debug tracer instruments all four.

### Spawn Execution Paths

After streaming convergence, there are four execution paths across three CLI commands. All bidirectional spawns ultimately flow through `SpawnManager.start_spawn(config, params)`:

| Path | Entry point | Config construction | SpawnManager | Finalization |
|---|---|---|---|---|
| **`meridian spawn` (fg)** | `spawn.py` → `execute_spawn_blocking()` → `execute_with_streaming()` | `execute_with_streaming()` builds `ConnectionConfig` at line 760 | Created per-spawn inside `execute_with_streaming()` at line 821 | `execute_with_streaming()` calls `spawn_store.finalize_spawn()` |
| **`meridian spawn --background`** | `execute_spawn_background()` → bg worker → `_execute_existing_spawn()` → `execute_with_streaming()` | Same as above | Same as above | Same as above |
| **`meridian streaming serve`** | `streaming_serve()` → `run_streaming_spawn()` | `streaming_serve()` builds `ConnectionConfig` at line 59 | Created per-spawn inside `run_streaming_spawn()` at line 439 | `streaming_serve()` calls `spawn_store.finalize_spawn()` in finally |
| **`meridian app`** | `app_cmd.run_app()` → `SpawnManager` (long-lived) | API request handler builds config | Shared instance; persists for server lifetime | SpawnManager cleanup; no `spawn_store.finalize_spawn()` |

**Key architectural point:** `execute_with_streaming()` is the primary spawn execution function — it handles retries, guardrails, budget tracking, and finalization. It constructs `ConnectionConfig` internally from `Spawn` + `PreparedSpawnPlan`. This means `--debug` cannot simply ride on a CLI-constructed `ConnectionConfig` for the `meridian spawn` path; it must be threaded through the ops layer into `execute_with_streaming()`.

`run_streaming_spawn()` is a simpler function used only by `streaming_serve`, where the CLI does construct `ConnectionConfig` directly.

## What Debug Mode Captures

| Layer | Direction | What's captured |
|---|---|---|
| **wire** | outbound | JSON sent to harness process (stdin writes, WS sends, HTTP posts) |
| **wire** | inbound | Raw data received from harness (stdout lines, WS frames, HTTP/SSE chunks) |
| **connection** | internal | State transitions (created → starting → connected → ...) with timestamps |
| **drain** | inbound | Events entering the drain loop from the connection |
| **drain** | outbound | Events fanned out to subscriber queue |
| **mapper** | inbound | HarnessEvent entering translation |
| **mapper** | outbound | AG-UI BaseEvent(s) produced, or empty (event dropped) |
| **websocket** | outbound | AG-UI events serialized and sent to client |
| **websocket** | inbound | Control messages received from client |

## How It Flows

1. **CLI flag** `--debug` on `meridian spawn`, `meridian streaming serve`, or `meridian app`.
2. **Flag propagation** differs by path:
   - **`meridian spawn`**: `--debug` flag on `SpawnCreateInput` → `execute_with_streaming(debug=True)` → tracer created inside `execute_with_streaming()` alongside `ConnectionConfig` construction (line 760). The tracer is set on `ConnectionConfig.debug_tracer` before passing to `manager.start_spawn(config, params)`.
   - **`meridian streaming serve`**: `--debug` flag → tracer created in `streaming_serve()` → set on `ConnectionConfig` directly → passed to `run_streaming_spawn()`.
   - **`meridian app`**: `--debug` flag → `SpawnManager(debug=True)` → manager creates tracer per-spawn in `start_spawn()`.
3. **ConnectionConfig** carries `debug_tracer: DebugTracer | None`. Despite the ConnectionConfig/SpawnParams split, ConnectionConfig is the correct home: it carries per-connection startup config (spawn_id, harness_id, env, timeouts), and the tracer is per-connection with per-spawn file scope.
4. **Concrete connections** (Claude, Codex, OpenCode) store `self._tracer = config.debug_tracer` during `start(config, params)` and emit structured events via shared trace helpers. The `params: SpawnParams` argument is irrelevant to the tracer.
5. **SpawnManager._drain_loop** receives the tracer as a direct parameter (not via SpawnSession lookup) and traces event persistence and fan-out. The drain loop resolves a `completion_future: asyncio.Future[DrainOutcome]` on exit — tracer close is wired into both the natural cleanup path (`_cleanup_completed_session`) and the forced path (`stop_spawn`).
6. **ws_endpoint._outbound_loop** traces around `mapper.translate()` and WebSocket sends without modifying the `AGUIMapper` Protocol. Mapper traces include truncated payload for diagnosing why events are dropped.

When debug is disabled (the default), `debug_tracer` is `None` and no instrumentation code runs beyond the `None` check.

## SpawnExtractor

The `SpawnExtractor` protocol (and its `StreamingExtractor` implementation in `lib/harness/extractor.py`) does NOT need tracer awareness. It's an artifact extractor that runs after the connection finishes — reading session_id from a live connection or falling back to artifact-based extraction. It's not on the hot event path and has no wire traffic to trace.

## Prerequisite

Codex adapter needs a centralized `_transition()` method (matching Claude's `_set_state` and OpenCode's `_transition`) before tracer hooks go in. Currently mutates `self._state` directly without a centralized method. This is a separate refactor phase.

## Design Docs

- [overview.md](./overview.md) — this doc. Problem, pipeline map, event taxonomy, execution paths.
- [debug-tracer.md](./debug-tracer.md) — DebugTracer contract, JSONL event schema, file lifecycle, and instrumentation hooks for each layer.
