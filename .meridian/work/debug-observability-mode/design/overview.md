# Design: --debug Observability Mode

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

1. **CLI flag** `--debug` on `meridian streaming serve` or `meridian app`.
2. **ConnectionConfig** carries `debug_tracer: DebugTracer | None`. When `--debug`, a `FileDebugTracer` is created targeting `{spawn_dir}/debug.jsonl`.
3. **Concrete connections** (Claude, Codex, OpenCode) check `self._tracer is not None` at each I/O site and emit structured events.
4. **SpawnManager._drain_loop** receives the tracer from the connection config and traces event persistence and fan-out.
5. **ws_endpoint._outbound_loop** traces around `mapper.translate()` and WebSocket sends without modifying the `AGUIMapper` Protocol.

When debug is disabled (the default), `debug_tracer` is `None` and no instrumentation code runs beyond the `None` check.

## Design Docs

- [overview.md](./overview.md) — this doc. Problem, pipeline map, event taxonomy.
- [debug-tracer.md](./debug-tracer.md) — DebugTracer contract, JSONL event schema, file lifecycle, and instrumentation hooks for each layer.
