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
