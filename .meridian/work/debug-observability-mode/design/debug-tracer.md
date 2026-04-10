# DebugTracer: Contract, Schema, and Hooks

## DebugTracer Class

A single class in a new module `src/meridian/lib/streaming/debug_tracer.py`:

```python
class DebugTracer:
    """Structured JSONL debug event writer for streaming pipeline observability."""

    def __init__(
        self,
        spawn_id: str,
        debug_path: Path,
        *,
        echo_stderr: bool = False,
        max_payload_bytes: int = 4096,
    ) -> None: ...

    def emit(
        self,
        layer: str,
        event: str,
        *,
        direction: str = "internal",
        data: dict[str, object] | None = None,
    ) -> None:
        """Append one structured debug event. Safe to call from any context."""
        ...

    def close(self) -> None:
        """Flush and close the debug file handle."""
        ...
```

**Key properties:**
- `emit()` is synchronous. It appends one line to an open file handle and optionally writes to stderr. No async machinery — debug tracing must not introduce event loop pressure or backpressure into the pipeline it's observing.
- Thread-safe via a `threading.Lock` on the file handle, since `emit()` can be called from `asyncio.to_thread` paths (e.g., the `_append_jsonl` helper).
- The file handle opens on first `emit()`, not in `__init__`, so creating a tracer has zero I/O cost.
- `close()` is idempotent. Called in cleanup paths.

## JSONL Event Schema

Each line in `debug.jsonl` is one JSON object:

```json
{
  "ts": 1712700000.123,
  "spawn_id": "p42",
  "layer": "wire",
  "direction": "outbound",
  "event": "stdin_write",
  "data": {
    "payload": "{\"type\":\"user\",\"message\":{\"role\":\"user\",\"content\":\"hello\"}}",
    "bytes": 67
  }
}
```

| Field | Type | Description |
|---|---|---|
| `ts` | float | Unix timestamp from `time.time()` |
| `spawn_id` | string | Spawn identifier for correlation |
| `layer` | string | Pipeline layer: `wire`, `connection`, `drain`, `mapper`, `websocket` |
| `direction` | string | `inbound`, `outbound`, or `internal` (state changes) |
| `event` | string | What happened — machine-greppable identifier |
| `data` | object \| null | Event-specific payload, truncated per `max_payload_bytes` |

### Payload Truncation

Wire payloads (the `payload` field within `data`) are truncated to `max_payload_bytes` (default 4096). Truncation appends `...[truncated, {original_bytes}B total]` so you know data was lost and how much. Non-payload fields (byte counts, status codes, state names) are never truncated.

```python
def _truncate(self, value: str) -> str:
    if len(value) <= self._max_payload_bytes:
        return value
    return value[:self._max_payload_bytes] + f"...[truncated, {len(value)}B total]"
```

## ConnectionConfig Change

Add one field to `ConnectionConfig` in `base.py`:

```python
@dataclass(frozen=True)
class ConnectionConfig:
    # ... existing fields ...
    debug_tracer: DebugTracer | None = None
```

No `TYPE_CHECKING` guard needed — `DebugTracer` is a concrete class, not a protocol, and lives in the same package (`lib/streaming`). The import is lightweight (no heavy dependencies).

## Instrumentation Hooks by Layer

### Layer 1: Wire — Harness Connection Adapters

Each concrete connection stores `self._tracer = config.debug_tracer` during `start()` and uses it throughout.

#### ClaudeConnection (stdin/stdout)

| Hook location | Event name | Direction | Data |
|---|---|---|---|
| `_send_json()` after serialization | `stdin_write` | outbound | `{payload, bytes}` |
| `events()` after `readline()` | `stdout_line` | inbound | `{raw_text, bytes}` |
| `events()` after `_parse_stdout_line()` | `parsed_event` | inbound | `{event_type, payload}` |
| `events()` on parse failure | `parse_error` | inbound | `{raw_text, error}` |
| `_signal_process()` | `signal_sent` | outbound | `{signal}` |

```python
# In _send_json, after building wire string:
if self._tracer is not None:
    self._tracer.emit("wire", "stdin_write", direction="outbound", data={
        "payload": wire,
        "bytes": len(wire.encode("utf-8")),
    })
```

#### CodexConnection (WebSocket)

| Hook location | Event name | Direction | Data |
|---|---|---|---|
| `_request()` before `ws.send()` | `ws_send_request` | outbound | `{method, request_id, payload}` |
| `_notify()` before `ws.send()` | `ws_send_notify` | outbound | `{method, payload}` |
| `_read_messages_loop()` on raw message | `ws_recv` | inbound | `{raw_text, bytes}` |
| `_read_messages_loop()` on parsed response | `ws_recv_response` | inbound | `{request_id, has_error}` |
| `_read_messages_loop()` on parsed notification | `ws_recv_notification` | inbound | `{method, payload}` |

```python
# In _request, before ws.send:
if self._tracer is not None:
    self._tracer.emit("wire", "ws_send_request", direction="outbound", data={
        "method": method,
        "request_id": request_id,
        "payload": json.dumps(payload),
    })
```

#### OpenCodeConnection (HTTP)

| Hook location | Event name | Direction | Data |
|---|---|---|---|
| `_post_json()` before request | `http_post` | outbound | `{path, payload}` |
| `_post_json()` after response | `http_response` | inbound | `{path, status, body}` |
| `_open_event_stream()` on connect | `sse_connect` | inbound | `{path, status}` |
| `events()` on parsed stream line | `sse_event` | inbound | `{event_type, payload}` |
| `_health_endpoint_ready()` | `health_check` | internal | `{path, status}` |

```python
# In _post_json, before request:
if self._tracer is not None:
    self._tracer.emit("wire", "http_post", direction="outbound", data={
        "path": path,
        "payload": json.dumps(dict(payload)),
    })
```

### Layer 1b: Connection State Transitions

All three adapters trace state transitions. Same event name, different adapter:

| Hook location | Event name | Direction | Data |
|---|---|---|---|
| `_set_state()` / `_transition()` | `state_change` | internal | `{from_state, to_state}` |

```python
# In ClaudeConnection._set_state:
if self._tracer is not None:
    self._tracer.emit("connection", "state_change", data={
        "from": self._state,
        "to": next_state,
        "harness": "claude",
    })
```

### Layer 2: SpawnManager._drain_loop

The drain loop receives the tracer from the config stored on the connection. It traces at the boundaries of event persistence and fan-out.

| Hook location | Event name | Direction | Data |
|---|---|---|---|
| Top of drain loop iteration | `event_received` | inbound | `{event_type, harness_id}` |
| After `_append_jsonl` success | `event_persisted` | outbound | `{event_type}` |
| On `_append_jsonl` failure | `persist_error` | internal | `{event_type, error, consecutive_failures}` |
| In `_fan_out_event` on delivery | `event_fanout` | outbound | `{event_type, queue_size}` |
| In `_fan_out_event` on drop (queue full) | `event_dropped` | internal | `{event_type, reason: "backpressure"}` |

**How the tracer reaches _drain_loop:** The `SpawnManager.start_spawn()` method already has the `ConnectionConfig`. It passes the tracer to the `SpawnSession` dataclass, and `_drain_loop` reads it from there.

```python
@dataclass
class SpawnSession:
    connection: HarnessConnection
    drain_task: asyncio.Task[None]
    subscriber: asyncio.Queue[HarnessEvent | None] | None
    control_server: ControlSocketServer
    started_monotonic: float
    debug_tracer: DebugTracer | None  # NEW
```

### Layer 3: AG-UI Mapper (traced from outside)

The `AGUIMapper` Protocol is NOT modified. Instead, `ws_endpoint._outbound_loop` wraps the `mapper.translate()` call:

```python
# In _outbound_loop:
if tracer is not None:
    tracer.emit("mapper", "translate_input", direction="inbound", data={
        "event_type": event.event_type,
        "harness_id": event.harness_id,
    })

translated = mapper.translate(event)

if tracer is not None:
    tracer.emit("mapper", "translate_output", direction="outbound", data={
        "input_event_type": event.event_type,
        "output_count": len(translated),
        "output_types": [getattr(e, "type", "unknown") for e in translated],
    })
```

### Layer 4: WebSocket Bridge

The `_outbound_loop` and `_inbound_loop` in `ws_endpoint.py` trace WebSocket I/O:

| Hook location | Event name | Direction | Data |
|---|---|---|---|
| `_send_event()` | `ws_send` | outbound | `{event_type, serialized_bytes}` |
| `_inbound_loop` on receive | `ws_recv` | inbound | `{message_type, raw_text}` |
| `_inbound_loop` on control dispatch | `control_dispatch` | inbound | `{action, spawn_id}` |

**How the tracer reaches ws_endpoint:** `spawn_websocket()` receives the `SpawnManager` which has the `SpawnSession`. The tracer is extracted from the session and passed to the loop functions as a parameter.

## CLI Integration

### `meridian streaming serve`

Add `--debug` flag to `streaming_serve_cmd` in `main.py`. This creates a `DebugTracer` with `echo_stderr=True` and passes it through `ConnectionConfig`.

```python
# In streaming_serve():
tracer: DebugTracer | None = None
if debug:
    spawn_dir = state_root / "spawns" / str(spawn_id)
    tracer = DebugTracer(
        spawn_id=str(spawn_id),
        debug_path=spawn_dir / "debug.jsonl",
        echo_stderr=True,
    )
```

### `meridian app`

Add `--debug` flag to `run_app()` in `app_cmd.py`. The `SpawnManager` stores the debug flag and creates tracers for each spawn it starts. `echo_stderr=False` in server mode.

## File Lifecycle

1. `DebugTracer.__init__` — stores path, no I/O.
2. First `emit()` call — opens file handle in append mode, creates parent dirs.
3. Subsequent `emit()` calls — append JSONL line, optional stderr echo.
4. `close()` — flush and close file handle. Called from `SpawnManager` cleanup paths alongside existing resource cleanup.
5. If the spawn crashes before any debug events, no `debug.jsonl` is created.

## Edge Cases and Failure Modes

- **Tracer write fails (disk full, permissions):** Log once via `logger.warning`, set an internal `_write_failed` flag, and stop attempting writes. The tracer must never crash the pipeline it's observing.
- **Concurrent emit() calls:** Protected by `threading.Lock`. The lock is uncontested in practice (one spawn = one event stream), but safe if drain_loop and fan_out race.
- **Large payloads:** Truncated at 4KB by default. The `bytes` field in the data always reports the original size so you know truncation happened.
- **Tracer not closed (crash):** Python's GC and OS process exit will flush the file. No data loss beyond the current unflushed line, which is at most one JSONL event.
- **debug.jsonl grows unbounded:** For long-running spawns, the file can grow large. This is acceptable for a debug mode — you only enable it when diagnosing problems, not in production. A future enhancement could add rotation.

## Files Changed

| File | Change |
|---|---|
| `src/meridian/lib/streaming/debug_tracer.py` | **NEW** — DebugTracer class |
| `src/meridian/lib/harness/connections/base.py` | Add `debug_tracer` field to `ConnectionConfig` |
| `src/meridian/lib/harness/connections/claude_ws.py` | Add wire + state trace hooks |
| `src/meridian/lib/harness/connections/codex_ws.py` | Add wire + state trace hooks |
| `src/meridian/lib/harness/connections/opencode_http.py` | Add wire + state trace hooks |
| `src/meridian/lib/streaming/spawn_manager.py` | Add drain/fan-out trace hooks, pass tracer to SpawnSession |
| `src/meridian/lib/app/ws_endpoint.py` | Add mapper + WebSocket trace hooks |
| `src/meridian/cli/streaming_serve.py` | Create tracer when `--debug`, pass via config |
| `src/meridian/cli/app_cmd.py` | Accept `--debug` flag, propagate to SpawnManager |
| `src/meridian/cli/main.py` | Wire `--debug` CLI parameter |

## What This Does NOT Cover

- **Replay tooling.** A `meridian debug replay` command that reads `debug.jsonl` and pretty-prints the trace would be valuable but is a separate concern.
- **Performance profiling.** Debug mode captures protocol events, not timing/latency metrics. Profiling is a different tool.
- **Automatic protocol validation.** The tracer captures what happened; it doesn't assert correctness. A future layer could validate events against a schema, but that's additive.
