# Phase 2 — FastAPI WebSocket Server with AG-UI Translation

Phase 2 wraps Phase 1's bidirectional streaming layer in a FastAPI server that speaks AG-UI over WebSocket. The mapper layer is the bulk of the real work — translating three different harness wire formats into the standard AG-UI event protocol.

**Dependencies**: Phase 1 complete (SpawnManager, HarnessConnection, control socket all working).
**Gate**: Unit tests for all three mappers + per-harness end-to-end smoke tests through the WebSocket.

## Sub-step 2A: FastAPI Server Skeleton and WebSocket Endpoint

**Scope**: Set up the FastAPI application, WebSocket endpoint shell, and dependency wiring to SpawnManager. The endpoint handles connection lifecycle (accept, subscribe, concurrent inbound/outbound tasks, unsubscribe on disconnect) but delegates event translation to Phase 2B mappers.

**Round**: 4 (after Phase 1 complete).

### Files to Create

- `src/meridian/lib/app/__init__.py` — Package init
- `src/meridian/lib/app/server.py` — FastAPI app factory:
  - `create_app(spawn_manager: SpawnManager) -> FastAPI`: creates app with lifespan, registers WS endpoint and REST routes
  - Lifespan: startup → SpawnManager already initialized by caller; shutdown → SpawnManager.shutdown()
  - Static file mounting placeholder (Phase 3 fills in `frontend/dist/`)
  - CORS middleware for local dev (allow localhost origins)
  
- `src/meridian/lib/app/ws_endpoint.py` — WebSocket handler:
  - `spawn_websocket(websocket, spawn_id, manager)`: accept WS, subscribe to drain fan-out, run concurrent outbound + inbound tasks
  - Outbound task: read from subscriber queue → (placeholder: pass-through as JSON until mappers exist) → send as WS text frames
  - Inbound task: read WS frames → parse JSON → route to `manager.inject()` / `manager.interrupt()` / `manager.cancel()` with `source="websocket"`
  - Error handling: RUN_ERROR on spawn not found, rejection on duplicate subscriber
  - Clean unsubscribe in finally block

- `src/meridian/lib/app/agui_mapping/__init__.py` — Mapper registry: `get_agui_mapper(harness_id) -> AGUIMapper`
- `src/meridian/lib/app/agui_mapping/base.py` — `AGUIMapper` protocol:
  - `translate(event: HarnessEvent) -> list[BaseEvent]`
  - `make_run_started(spawn_id: str) -> RunStartedEvent`
  - `make_run_finished(spawn_id: str) -> RunFinishedEvent`
  - `make_capabilities_event(caps: ConnectionCapabilities) -> CustomEvent`

### Files to Modify

- `pyproject.toml` — Add dependencies:
  ```toml
  [project.optional-dependencies]
  app = ["fastapi>=0.115", "uvicorn[standard]>=0.34", "websockets>=14.0", "ag-ui-protocol>=0.1"]
  ```
  Also add `aiofiles` if not already present (for async file writes in drain loop).

### Dependencies

- Requires: Phase 1 complete (SpawnManager interface stable)
- Independent of: Phase 2B (mappers — endpoint uses mapper protocol, concrete mappers come next)

### Interface Contract

```python
# WebSocket endpoint contract
# ws://localhost:<port>/ws/spawn/{spawn_id}

# Outbound frames (server → client): AG-UI JSON events
# Each frame is: event.model_dump_json(by_alias=True, exclude_none=True)

# Inbound frames (client → server):
# {"type": "user_message", "text": "..."}
# {"type": "interrupt"}
# {"type": "cancel"}
```

### Patterns to Follow

- Existing FastAPI pattern in `src/meridian/server/main.py` (FastMCP server) — follow lifespan and app factory style
- `design/phase-2-fastapi-agui.md` ws_endpoint.py pseudocode — the design doc has detailed endpoint implementation to follow

### Verification Criteria

- [ ] `uv run pyright` passes
- [ ] `uv run ruff check .` passes
- [ ] FastAPI app starts without errors: `uvicorn meridian.lib.app.server:create_app --factory`
- [ ] WebSocket connection to `/ws/spawn/{spawn_id}` succeeds when spawn exists
- [ ] Inbound frames route to SpawnManager correctly
- [ ] Client disconnect does not stop the drain task
- [ ] Second client to same spawn is rejected with RUN_ERROR
- [ ] `AGUIMapper` protocol is defined and importable
- [ ] Existing tests pass: `uv run pytest-llm`

### Edge Cases

- **EC2: Client disconnects mid-stream** — drain task continues; subscriber queue removed in finally block
- **EC6: Process restart** — fresh SpawnManager, no reattachment (MVP)
- **EC10: Concurrent WS clients** — second rejected with clear error message

---

## Sub-step 2B: AG-UI Mappers (All Three Harnesses)

**Scope**: Implement the per-harness wire-format → AG-UI event translation. This is the heaviest logic in Phase 2. Each mapper transforms `HarnessEvent` objects into `ag_ui.core` Pydantic models.

**Round**: 5 (after 2A provides the mapper protocol and testing infrastructure).

**D56 OVERRIDE**: Use standard `REASONING_*` events from `ag_ui.core`, NOT custom `THINKING_*` events. The design docs reference `THINKING_*` (D48) — this was overridden. Mappers emit `ReasoningMessageStartEvent`, `ReasoningMessageContentEvent`, `ReasoningMessageEndEvent`.

### Files to Create

- `src/meridian/lib/app/agui_mapping/claude.py` — `ClaudeAGUIMapper`:

  | Claude wire event | AG-UI event(s) |
  |---|---|
  | `stream_event` + `content_block_start` (text) | `TextMessageStartEvent(messageId=<uuid>)` |
  | `stream_event` + `content_block_delta` (text) | `TextMessageContentEvent(messageId=..., delta=...)` |
  | `stream_event` + `content_block_stop` (text) | `TextMessageEndEvent(messageId=...)` |
  | `stream_event` + `content_block_start` (thinking) | `ReasoningMessageStartEvent` (D56) |
  | `stream_event` + `content_block_delta` (thinking) | `ReasoningMessageContentEvent` (D56) |
  | `stream_event` + `content_block_stop` (thinking) | `ReasoningMessageEndEvent` (D56) |
  | `stream_event` + `content_block_start` (tool_use) | `ToolCallStartEvent(toolCallId=..., toolCallName=...)` |
  | `stream_event` + `content_block_delta` (tool_use) | `ToolCallArgsEvent(toolCallId=..., delta=...)` |
  | `stream_event` + `content_block_stop` (tool_use) | `ToolCallEndEvent(toolCallId=...)` |
  | `tool_use_summary` / `tool_progress` | `ToolCallResultEvent(toolCallId=..., content=...)` |
  | `result` (error) | `RunErrorEvent(message=...)` |
  | `result` (success) | consumed internally (RUN_FINISHED emitted by endpoint) |
  | `system/init` | consumed internally |

  ID generation: `messageId` and reasoning IDs from UUID. `toolCallId` from Claude's `tool_use_id`. `threadId` = spawn_id. `runId` = `{spawn_id}-run-{n}`.

- `src/meridian/lib/app/agui_mapping/codex.py` — `CodexAGUIMapper`:

  | Codex JSON-RPC notification | AG-UI event(s) |
  |---|---|
  | `item/agentMessage` (delta) | `TextMessageContentEvent` |
  | `item/agentMessage` (complete) | `TextMessageStartEvent` + `TextMessageContentEvent` + `TextMessageEndEvent` |
  | `item/commandExecution` | `ToolCallStartEvent` + `ToolCallArgsEvent` + `ToolCallEndEvent` |
  | `item/fileChange` | `ToolCallStartEvent(name="FileWrite")` + args + end |
  | `item/reasoning` | `ReasoningMessageStartEvent` + `ReasoningMessageContentEvent` + `ReasoningMessageEndEvent` (D56) |
  | `item/webSearch` | `ToolCallStartEvent(name="WebSearch")` + args + end |
  | `item/mcpToolCall` | `ToolCallStartEvent` + args + end + result |
  | `turn/completed` | `StepFinishedEvent` |

- `src/meridian/lib/app/agui_mapping/opencode.py` — `OpenCodeAGUIMapper`:

  | OpenCode update type | AG-UI event(s) |
  |---|---|
  | `agent_message_chunk` | `TextMessageContentEvent` |
  | `agent_thought_chunk` | `ReasoningMessageContentEvent` (D56) |
  | `tool_call` | `ToolCallStartEvent` + `ToolCallArgsEvent` + `ToolCallEndEvent` |
  | `tool_call_update` | `ToolCallResultEvent` |
  | `user_message_chunk` | consumed (own echo) |
  | `session_info_update` | consumed internally |

- `src/meridian/lib/app/agui_mapping/extensions.py` — Meridian AG-UI extensions:
  - `make_capabilities_event(caps: ConnectionCapabilities) -> CustomEvent`: creates `CUSTOM` event with name="capabilities"
  - `make_run_error_event(message: str, is_cancelled: bool = False) -> RunErrorEvent`: with `isCancelled` extension field

### Files to Modify

- `src/meridian/lib/app/agui_mapping/__init__.py` — Register all three mappers in `get_agui_mapper()`
- `src/meridian/lib/app/ws_endpoint.py` — Wire mapper into outbound task (replace placeholder pass-through with actual mapping)

### Dependencies

- Requires: Phase 2A (mapper protocol, endpoint structure)
- Requires: Phase 1A (HarnessEvent type for mapper input)

### Interface Contract

```python
class AGUIMapper(Protocol):
    def translate(self, event: HarnessEvent) -> list[BaseEvent]: ...
    def make_run_started(self, spawn_id: str) -> RunStartedEvent: ...
    def make_run_finished(self, spawn_id: str) -> RunFinishedEvent: ...
```

All output events are Pydantic models from `ag_ui.core`. Serialization: `event.model_dump_json(by_alias=True, exclude_none=True)`.

### Verification Criteria

- [ ] `uv run pyright` passes
- [ ] `uv run ruff check .` passes
- [ ] Each mapper satisfies `AGUIMapper` protocol
- [ ] Unit tests for each mapper: feed recorded wire fixtures, assert AG-UI output shapes
  - Claude: text blocks, thinking blocks (→ REASONING_*), tool calls, tool results, errors
  - Codex: agent messages, command executions, file changes, reasoning, turn completion
  - OpenCode: message chunks, thought chunks, tool calls, tool updates
- [ ] Edge case unit tests: empty deltas, malformed events (return empty list), missing fields
- [ ] All AG-UI events deserializable by `ag_ui.core` (round-trip test)
- [ ] Serialization produces camelCase JSON: `event.model_dump_json(by_alias=True, exclude_none=True)`
- [ ] D56 compliance: no `THINKING_*` events anywhere, only `REASONING_*`
- [ ] Existing tests pass: `uv run pytest-llm`

### Edge Cases

- **EC8: Malformed harness events** — `translate()` returns empty list, logs warning
- **EC7: Large output** — each event mapped independently, no accumulation
- **ID continuity** — mapper maintains internal state for open message/tool IDs across events

---

## Sub-step 2C: REST API, `meridian app` CLI, and End-to-End Integration

**Scope**: Add the minimal REST API for spawn management, the `meridian app` CLI command, and wire everything together for the Phase 2 gate.

**Round**: 6 (after 2A + 2B complete).

### Files to Create

- `src/meridian/cli/app.py` — `meridian app` CLI command:
  - `meridian app` — start server, open browser
  - `meridian app --port 8420` — custom port
  - `meridian app --no-browser` — server only
  - Creates SpawnManager, creates FastAPI app, starts uvicorn
  - Checks for `app` optional dependency group, gives clear error if missing
  - Opens default browser to `http://localhost:<port>`

### Files to Modify

- `src/meridian/lib/app/server.py` — Add REST routes:
  - `POST /api/spawn` — start a new bidirectional spawn (body: `{harness, agent, prompt, model?}`)
  - `GET /api/spawn` — list active spawns
  - `GET /api/spawn/{id}` — get spawn status and metadata
  - `POST /api/spawn/{id}/inject` — alternative inject for non-WS clients
  - `DELETE /api/spawn/{id}` — cancel a spawn
  - Static file mount: `app.mount("/", StaticFiles(directory="frontend/dist", html=True))` (conditional on directory existing)

- `src/meridian/cli/main.py` — Register `meridian app` command

### Dependencies

- Requires: Phase 2A (server skeleton), Phase 2B (mappers wired into endpoint)
- This step produces the complete Phase 2 deliverable

### Interface Contract

```bash
# CLI
meridian app                    # Start server, open browser
meridian app --port 8420        # Custom port  
meridian app --no-browser       # Start server only

# REST API
POST /api/spawn          → {"spawn_id": "p200", "harness": "claude", ...}
GET  /api/spawn          → [{"spawn_id": "p200", "status": "running", ...}, ...]
GET  /api/spawn/{id}     → {"spawn_id": "p200", "status": "running", "capabilities": {...}}
POST /api/spawn/{id}/inject → {"ok": true}
DELETE /api/spawn/{id}   → {"ok": true}
```

### Patterns to Follow

- Existing CLI registration in `main.py` — follow cyclopts subcommand pattern
- `design/overview.md` "What meridian app Does" section — launch sequence

### Verification Criteria

- [ ] `uv run pyright` passes
- [ ] `uv run ruff check .` passes
- [ ] `meridian app --no-browser` starts uvicorn and serves the WS endpoint
- [ ] `POST /api/spawn` starts a spawn and returns spawn_id
- [ ] `GET /api/spawn` lists active spawns
- [ ] REST inject endpoint routes to SpawnManager
- [ ] `DELETE /api/spawn/{id}` cancels a running spawn
- [ ] Missing `app` dependency group gives clear error message
- [ ] Existing CLI commands not broken
- [ ] Existing tests pass: `uv run pytest-llm`

### Smoke Tests (Phase 2 Gate)

Create smoke test guides in `tests/smoke/` — one per harness:

1. Start `meridian app --no-browser --port 8420`
2. `POST /api/spawn` with `{"harness": "claude", "prompt": "List files"}`
3. Connect WebSocket client to `ws://localhost:8420/ws/spawn/{spawn_id}`
4. Receive `RUN_STARTED` event
5. Receive `CUSTOM` capabilities event
6. Receive text/tool/reasoning events as harness works
7. Send `{"type": "user_message", "text": "What did you find?"}` frame
8. Verify harness receives and responds to injected message
9. Receive `RUN_FINISHED` event
10. All events have valid AG-UI shape (deserializable)

### Edge Cases

- **EC4: Harness won't connect** — `POST /api/spawn` returns 500 with error message
- **EC11: Agent profile not found** — `POST /api/spawn` returns 400 with clear error
- **Missing app deps** — `meridian app` prints "Install app dependencies: uv sync --extra app" and exits
