# Phase 2 — FastAPI WebSocket Server with AG-UI Translation

Phase 2 wraps Phase 1's bidirectional streaming layer in a FastAPI server that speaks AG-UI over WebSocket. It is the bridge between the harness wire formats and the React UI.

## Architecture

```
Phase 3 (React)
    │
    │  WebSocket: /ws/spawn/{spawn_id}
    │  JSON text frames (AG-UI events outbound, control messages inbound)
    │
    ▼
FastAPI Server
    ├── ws_endpoint.py   → reads HarnessEvents, maps to AG-UI, sends to client
    ├── agui_mapping/    → per-harness wire-format → AG-UI event translators
    └── server.py        → app factory, static files, spawn management API
    │
    │  In-process asyncio calls
    │
    ▼
Phase 1 SpawnManager
    └── HarnessConnection per spawn
```

## WebSocket Endpoint

One endpoint, one lifecycle, one frame format (per D42):

```
ws://localhost:<port>/ws/spawn/{spawn_id}
```

### Outbound frames (server → client)

Each frame is a JSON string — one AG-UI event serialized with `event.model_dump_json(by_alias=True, exclude_none=True)`. The `type` field discriminates the event kind.

```json
{"type": "RUN_STARTED", "threadId": "spawn-p100", "runId": "run-1"}
{"type": "TEXT_MESSAGE_START", "messageId": "msg-1"}
{"type": "TEXT_MESSAGE_CONTENT", "messageId": "msg-1", "delta": "Hello "}
{"type": "TEXT_MESSAGE_CONTENT", "messageId": "msg-1", "delta": "world"}
{"type": "TEXT_MESSAGE_END", "messageId": "msg-1"}
{"type": "TOOL_CALL_START", "toolCallId": "tc-1", "toolCallName": "Bash"}
{"type": "TOOL_CALL_ARGS", "toolCallId": "tc-1", "delta": "{\"command\":\"ls\"}"}
{"type": "TOOL_CALL_END", "toolCallId": "tc-1"}
{"type": "TOOL_CALL_RESULT", "messageId": "msg-1", "toolCallId": "tc-1", "content": "file1.py\nfile2.py"}
{"type": "RUN_FINISHED", "threadId": "spawn-p100", "runId": "run-1"}
```

### Inbound frames (client → server)

```json
{"type": "user_message", "text": "reconsider the auth approach"}
{"type": "interrupt"}
{"type": "cancel"}
```

The endpoint parses each frame, routes to the appropriate `SpawnManager` method:
- `user_message` → `manager.inject(spawn_id, text)`
- `interrupt` → `manager.interrupt(spawn_id)`
- `cancel` → `manager.cancel(spawn_id)`

### Endpoint implementation

The WebSocket endpoint is a **consumer of the SpawnManager's fan-out mechanism**, not a direct reader of `connection.events()`. The durable drain task in `SpawnManager` owns the event iterator; this endpoint subscribes to a queue that the drain feeds.

```python
# src/meridian/lib/app/ws_endpoint.py

from fastapi import WebSocket, WebSocketDisconnect
from meridian.lib.streaming.spawn_manager import SpawnManager

async def spawn_websocket(
    websocket: WebSocket,
    spawn_id: str,
    manager: SpawnManager,
):
    """WebSocket handler for one spawn's event stream.

    Subscribes to the SpawnManager's fan-out queue for this spawn.
    Runs two concurrent tasks:
    1. Outbound: read from subscriber queue → map to AG-UI → send as JSON frames
    2. Inbound: read client frames → parse → route to SpawnManager
    """
    await websocket.accept()

    connection = await manager.get_connection(SpawnId(spawn_id))
    if connection is None:
        await websocket.send_json({"type": "RUN_ERROR", "message": "spawn not found"})
        await websocket.close()
        return

    # Subscribe to the drain's fan-out. Returns None if another client
    # is already subscribed (MVP: one client per spawn).
    event_queue = manager.subscribe(SpawnId(spawn_id))
    if event_queue is None:
        await websocket.send_json({"type": "RUN_ERROR", "message": "another client is already connected to this spawn"})
        await websocket.close()
        return

    mapper = get_agui_mapper(connection.harness_id)

    async def outbound():
        """Read from subscriber queue and send AG-UI events to the client."""
        try:
            # Emit RUN_STARTED
            run_started = mapper.make_run_started(spawn_id)
            await websocket.send_text(
                run_started.model_dump_json(by_alias=True, exclude_none=True)
            )

            # Emit capabilities custom event
            caps_event = mapper.make_capabilities_event(connection.capabilities)
            await websocket.send_text(
                caps_event.model_dump_json(by_alias=True, exclude_none=True)
            )

            while True:
                harness_event = await event_queue.get()
                if harness_event is None:
                    break  # Sentinel: stream ended

                agui_events = mapper.translate(harness_event)
                for agui_event in agui_events:
                    await websocket.send_text(
                        agui_event.model_dump_json(by_alias=True, exclude_none=True)
                    )

            # Emit RUN_FINISHED
            run_finished = mapper.make_run_finished(spawn_id)
            await websocket.send_text(
                run_finished.model_dump_json(by_alias=True, exclude_none=True)
            )
        except WebSocketDisconnect:
            pass  # Client disconnected — drain task continues independently
        except Exception as e:
            try:
                run_error = RunErrorEvent(message=str(e))
                await websocket.send_text(
                    run_error.model_dump_json(by_alias=True, exclude_none=True)
                )
            except WebSocketDisconnect:
                pass
        finally:
            manager.unsubscribe(SpawnId(spawn_id))

    async def inbound():
        """Read client frames and route to SpawnManager."""
        try:
            while True:
                data = await websocket.receive_json()
                msg_type = data.get("type")
                if msg_type == "user_message":
                    await manager.inject(SpawnId(spawn_id), data["text"], source="websocket")
                elif msg_type == "interrupt":
                    await manager.interrupt(SpawnId(spawn_id), source="websocket")
                elif msg_type == "cancel":
                    await manager.cancel(SpawnId(spawn_id), source="websocket")
        except WebSocketDisconnect:
            pass  # Client disconnected — drain task continues independently

    # Run both tasks concurrently
    outbound_task = asyncio.create_task(outbound())
    inbound_task = asyncio.create_task(inbound())

    done, pending = await asyncio.wait(
        {outbound_task, inbound_task},
        return_when=asyncio.FIRST_COMPLETED,
    )

    for task in pending:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
```

**Key property**: when the client disconnects, the `outbound` and `inbound` tasks end, but the SpawnManager's drain task continues draining events to `output.jsonl`. The spawn is not affected by client lifecycle. Lost events are available in `meridian spawn log <spawn_id>`.

## AG-UI Event Mapping

The mapping layer is the bulk of Phase 2's real work. Each harness speaks a different wire format; the mapper translates to AG-UI.

### Mapper Protocol

```python
# src/meridian/lib/app/agui_mapping/base.py

from typing import Protocol
from ag_ui.core import BaseEvent
from meridian.lib.harness.connections.base import HarnessEvent

class AGUIMapper(Protocol):
    """Translates harness wire events to AG-UI protocol events."""

    def translate(self, event: HarnessEvent) -> list[BaseEvent]:
        """Map one harness event to zero or more AG-UI events.

        One harness event may produce multiple AG-UI events (e.g., a Claude
        assistant message with multiple content blocks produces START + CONTENT
        + END events per block).

        Returns empty list for events that have no AG-UI equivalent (e.g.,
        harness-internal heartbeats).
        """
        ...

    def make_run_started(self, spawn_id: str) -> "RunStartedEvent":
        """Create a RUN_STARTED event for this spawn."""
        ...

    def make_run_finished(self, spawn_id: str) -> "RunFinishedEvent":
        """Create a RUN_FINISHED event for this spawn."""
        ...
```

### Claude Mapper

Claude's wire format is NDJSON with `type` discriminators. The mapper handles:

| Claude wire event | AG-UI event(s) |
|---|---|
| `stream_event` with `content_block_start` (text) | `TextMessageStartEvent(message_id=<generated>)` |
| `stream_event` with `content_block_delta` (text) | `TextMessageContentEvent(message_id=..., delta=...)` |
| `stream_event` with `content_block_stop` (text) | `TextMessageEndEvent(message_id=...)` |
| `stream_event` with `content_block_start` (thinking) | `ReasoningMessageStartEvent(message_id=<generated>)` (D56) |
| `stream_event` with `content_block_delta` (thinking) | `ReasoningMessageContentEvent(message_id=..., delta=...)` (D56) |
| `stream_event` with `content_block_stop` (thinking) | `ReasoningMessageEndEvent(message_id=...)` (D56) |
| `stream_event` with `content_block_start` (tool_use) | `ToolCallStartEvent(tool_call_id=..., tool_call_name=...)` |
| `stream_event` with `content_block_delta` (tool_use) | `ToolCallArgsEvent(tool_call_id=..., delta=...)` |
| `stream_event` with `content_block_stop` (tool_use) | `ToolCallEndEvent(tool_call_id=...)` |
| `tool_use_summary` / `tool_progress` | `ToolCallResultEvent(tool_call_id=..., content=...)` |
| `result` (success) | (consumed internally — `RUN_FINISHED` emitted by endpoint) |
| `result` (error) | `RunErrorEvent(message=...)` |
| `system/init` | (consumed internally for capability setup) |

**Reasoning events (D56 override)**: The mapper emits standard `ReasoningMessageStartEvent`, `ReasoningMessageContentEvent`, `ReasoningMessageEndEvent` from `ag_ui.core` — NOT custom `THINKING_*` events. D48 originally specified custom thinking events; D56 overrides this to use the AG-UI standard. Reasoning and thinking are the same concept.

**ID generation**: The mapper generates `messageId` and `toolCallId` values. Claude's wire format includes `tool_use_id` for tools; for text and reasoning blocks, the mapper generates UUIDs. The `threadId` is the spawn ID; `runId` is `{spawn_id}-run-{n}`.

### Codex Mapper

Codex speaks JSON-RPC 2.0 notifications. The mapper handles:

| Codex JSON-RPC notification | AG-UI event(s) |
|---|---|
| `item/agentMessage` (delta) | `TextMessageContentEvent` (accumulates into messages) |
| `item/agentMessage` (complete) | `TextMessageStartEvent` + `TextMessageContentEvent` + `TextMessageEndEvent` |
| `item/commandExecution` | `ToolCallStartEvent` + `ToolCallArgsEvent` + `ToolCallEndEvent` |
| `item/fileChange` | `ToolCallStartEvent` (name="FileWrite") + `ToolCallArgsEvent` + `ToolCallEndEvent` |
| `item/reasoning` | `ReasoningMessageStartEvent` + `ReasoningMessageContentEvent` + `ReasoningMessageEndEvent` (D56) |
| `item/webSearch` | `ToolCallStartEvent` (name="WebSearch") + args + end |
| `item/mcpToolCall` | `ToolCallStartEvent` + args + end + result |
| `item/*/requestApproval` | (held — approval UI is post-MVP; auto-approve for now) |
| `turn/completed` | (consumed — triggers step boundary in AG-UI) |

**Note**: Codex's streaming model is different from Claude's — it sends complete or large-chunk events rather than token-by-token deltas. The mapper may need to synthesize a `TextMessageStartEvent` from the first `item/agentMessage` delta, then accumulate subsequent deltas as `TextMessageContentEvent`.

**Reference**: The companion repo's `web/CODEX_MAPPING.md` documents the full JSON-RPC → internal event translation. The Python mapper should pattern-match this for completeness, adapted to AG-UI output.

### OpenCode Mapper

OpenCode uses ACP-style `session/update` notifications over SSE. The mapper handles:

| OpenCode update type | AG-UI event(s) |
|---|---|
| `agent_message_chunk` | `TextMessageContentEvent` |
| `agent_thought_chunk` | `ReasoningMessageContentEvent` (D56) |
| `tool_call` | `ToolCallStartEvent` + `ToolCallArgsEvent` + `ToolCallEndEvent` |
| `tool_call_update` | `ToolCallResultEvent` |
| `user_message_chunk` | (consumed — this is our own message echoed back) |
| `session_info_update` | (consumed internally) |

**SSE parsing**: OpenCode's `GET /event` endpoint returns Server-Sent Events. The mapper wraps this in an async iterator that yields `HarnessEvent` objects, abstracting the SSE framing.

## Meridian AG-UI Extensions

The MVP extends standard AG-UI in three places, all backward-compatible:

1. **~~`thinkingId` on THINKING_* events~~** — **Superseded by D56.** The mapper now emits standard `ReasoningMessage*Event` from `ag_ui.core`, which use `message_id` natively. No custom `thinkingId` field needed.

2. **`isCancelled` on RUN_ERROR** — Distinguishes user-initiated cancellation from actual errors. The frontend suppresses the error toast for cancellations. Matches the Go server's `MeridianRunErrorEvent`.

3. **`capabilities` custom event** — Sent immediately after `RUN_STARTED`:
```json
{
  "type": "CUSTOM",
  "name": "capabilities",
  "value": {
    "midTurnInjection": "queue",
    "supportsSteer": false,
    "supportsInterrupt": true,
    "harnessId": "claude"
  }
}
```
The frontend uses this to render the right send-button affordance per harness.

## REST API (minimal)

Phase 2 exposes a minimal REST API alongside the WebSocket for spawn management:

```
POST /api/spawn          → Start a new bidirectional spawn
GET  /api/spawn          → List active bidirectional spawns
GET  /api/spawn/{id}     → Get spawn status and metadata
POST /api/spawn/{id}/inject → Alternative inject path (for non-WS clients)
DELETE /api/spawn/{id}   → Cancel a spawn
```

These are convenience endpoints. The primary interaction path is the WebSocket.

## Dependencies

```toml
# All from ag-ui-protocol PyPI package
ag_ui.core.RunStartedEvent
ag_ui.core.RunFinishedEvent
ag_ui.core.RunErrorEvent
ag_ui.core.TextMessageStartEvent
ag_ui.core.TextMessageContentEvent
ag_ui.core.TextMessageEndEvent
ag_ui.core.ToolCallStartEvent
ag_ui.core.ToolCallArgsEvent
ag_ui.core.ToolCallEndEvent
ag_ui.core.ToolCallResultEvent
ag_ui.core.StepStartedEvent
ag_ui.core.StepFinishedEvent
ag_ui.core.CustomEvent
```

Serialization: `event.model_dump_json(by_alias=True, exclude_none=True)` — this is the standard AG-UI Python serialization that produces camelCase JSON matching the wire protocol.

## Phase 2 Gate: Tests

### Smoke tests (end-to-end through WebSocket)

One per harness, verifying the full event lifecycle:

1. Start the FastAPI server
2. Connect a WebSocket client to `/ws/spawn/{spawn_id}`
3. Receive `RUN_STARTED` event
4. Receive `CUSTOM` capabilities event
5. Receive text/tool/thinking events as the harness works
6. Send a `user_message` frame mid-stream
7. Verify the harness receives and responds to the injected message
8. Receive `RUN_FINISHED` event
9. Verify all events have valid AG-UI shape (deserializable by `ag_ui.core`)

### Unit tests (mapper in isolation)

One test suite per harness mapper, using recorded fixtures:

1. Capture real harness wire output from a representative spawn
2. Feed each wire event through the mapper
3. Assert the output AG-UI events have correct types, IDs, and content
4. Test edge cases: empty deltas, malformed wire events, missing fields

The unit tests are explicitly justified per requirements.md — the mapping function is a stable pure transformation, exactly where unit tests are cheap and valuable.

## Static File Serving

Phase 2's FastAPI app also serves the Phase 3 React build as static files:

```python
# After the React app is built (npm run build), mount the dist directory
app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="static")
```

The WebSocket endpoint is registered first (at `/ws/spawn/{spawn_id}`), so it takes priority over the static file catch-all.
