# Phase 1 — Bidirectional Streaming Foundation

Phase 1 delivers universal bidirectional streaming for all three harnesses. Every spawn gains input-channel writability. Fire-and-forget callers that never call `send_*()` get exactly the same behavior as before.

**Dependencies**: None (foundation phase).
**Gate**: All three harnesses pass manual smoke tests for mid-turn injection via `meridian spawn inject`.

## Sub-step 1A: Interfaces, Types, and Registration

**Scope**: Define the complete type system for bidirectional connections. This is the interface contract that all connection adapters, the SpawnManager, and Phase 2 depend on. Getting the types right here prevents cascading rework.

**Round**: 1 (first — everything else depends on this).

### Files to Create

- `src/meridian/lib/harness/connections/__init__.py` — Connection registry (`register_connection`, `get_connection_class`), import registrations
- `src/meridian/lib/harness/connections/base.py` — All types and protocols:
  - `ConnectionCapabilities` (frozen dataclass): `mid_turn_injection`, `supports_steer`, `supports_interrupt`, `supports_cancel`, `runtime_model_switch`, `structured_reasoning`
  - `ConnectionState` (Literal type): `created`, `starting`, `connected`, `stopping`, `stopped`, `failed`
  - `ConnectionNotReady` (exception)
  - `HarnessEvent` (frozen dataclass): `event_type`, `payload`, `harness_id`, `raw_text`
  - `ConnectionConfig` (frozen dataclass): all fields from `design/harness-abstraction.md` ConnectionConfig section
  - `HarnessLifecycle` (Protocol): `start()`, `stop()`, `health()`, `state` property
  - `HarnessSender` (Protocol): `send_user_message()`, `send_interrupt()`, `send_cancel()`
  - `HarnessReceiver` (Protocol): `events()` → `AsyncIterator[HarnessEvent]`
  - `HarnessConnection` (Protocol, composite): inherits all three + `harness_id`, `spawn_id`, `capabilities` properties
- `src/meridian/lib/streaming/__init__.py` — Package init
- `src/meridian/lib/streaming/types.py` — Control message types:
  - `ControlMessage` (union type for user_message / interrupt / cancel)
  - `InjectResult` (dataclass): `success: bool`, `error: str | None`

### Files to Modify

- `src/meridian/lib/harness/adapter.py` — Add `supports_bidirectional: bool = False` to `HarnessCapabilities`

### Interface Contract

```python
# The exact signatures that all downstream code depends on.
# Phase 1B-1D implement these. Phase 1E consumes them.

class HarnessConnection(HarnessLifecycle, HarnessSender, HarnessReceiver, Protocol):
    @property
    def harness_id(self) -> HarnessId: ...
    @property
    def spawn_id(self) -> SpawnId: ...
    @property
    def capabilities(self) -> ConnectionCapabilities: ...
```

### Patterns to Follow

- Existing `adapter.py` — `HarnessCapabilities` is a frozen `BaseModel`; follow same pattern for `ConnectionCapabilities` (but use `@dataclass(frozen=True)` per design doc)
- Existing `types.py` in `lib/core/types.py` — NewType pattern for SpawnId, HarnessId
- Existing protocols in `adapter.py` — `SubprocessHarness` as reference for Protocol style

### Verification Criteria

- [ ] `uv run pyright` passes with 0 errors
- [ ] `uv run ruff check .` passes
- [ ] All types are importable: `from meridian.lib.harness.connections.base import HarnessConnection, HarnessEvent, ConnectionConfig, ConnectionCapabilities, ConnectionState, ConnectionNotReady`
- [ ] `from meridian.lib.streaming.types import ControlMessage, InjectResult` works
- [ ] `from meridian.lib.harness.connections import get_connection_class, register_connection` works
- [ ] `HarnessCapabilities` has `supports_bidirectional` field defaulting to `False`
- [ ] Existing tests still pass: `uv run pytest-llm`

### Edge Cases

- None for types-only sub-step. Edge cases surface in implementation phases.

---

## Sub-step 1B: Claude Connection (`ClaudeConnection`)

**Scope**: Implement the Claude bidirectional adapter. We are the WebSocket server; Claude CLI connects to us via `--sdk-url`.

**Round**: 2 (parallel with 1C, 1D, 1E).

### Files to Create

- `src/meridian/lib/harness/connections/claude_ws.py` — `ClaudeConnection` class implementing `HarnessConnection`:
  - `start()`: start asyncio WS server on 127.0.0.1:0, build Claude command with `--sdk-url ws://127.0.0.1:<port>`, launch subprocess, wait for WS connection, send initial prompt as `{"type": "user", "content": "<prompt>"}` message
  - `events()`: yield `HarnessEvent` from WS messages (NDJSON parsing)
  - `send_user_message()`: send `{"type": "user", "content": text}` over WS
  - `send_interrupt()`: send interrupt signal over WS
  - `send_cancel()`: send cancel signal, transition to stopping
  - `stop()`: close WS, terminate subprocess (SIGTERM → timeout → SIGKILL)
  - `health()`: check subprocess alive + WS connected
  - State machine enforcement per `design/harness-abstraction.md` transition rules
  - Version gating: check `claude --version`, warn if untested (D52)
  - Protocol mismatch detection: validate first WS message format (D52)

### Files to Modify

- `src/meridian/lib/harness/claude.py` — Add `supports_bidirectional=True` to capabilities property
- `src/meridian/lib/harness/connections/__init__.py` — Register `ClaudeConnection`

### Dependencies

- Requires: Phase 1A (base types and protocols)
- Independent of: Phase 1C, 1D, 1E

### Interface Contract

```python
class ClaudeConnection:
    """Implements HarnessConnection for Claude Code via --sdk-url WS."""
    
    capabilities = ConnectionCapabilities(
        mid_turn_injection="queue",
        supports_steer=False,
        supports_interrupt=True,
        supports_cancel=True,
        runtime_model_switch=False,
        structured_reasoning=True,  # Claude emits thinking blocks
    )
```

### Wire Format Reference

**Inbound (us → Claude)**:
```json
{"type": "user", "content": "user message text"}
```

**Outbound (Claude → us)**:
```json
{"type": "assistant", "message": {"content": [...]}}
{"type": "stream_event", "event": {"type": "content_block_delta", ...}}
{"type": "tool_progress", "tool_use_id": "...", "progress": "..."}
{"type": "tool_use_summary", "tool_use_id": "...", "name": "...", "result": "..."}
{"type": "result", "result": "...", "duration_ms": 1234}
```

### Verification Criteria

- [ ] `uv run pyright` passes
- [ ] `uv run ruff check .` passes
- [ ] `ClaudeConnection` satisfies `HarnessConnection` protocol (pyright structural check)
- [ ] State machine transitions are enforced (test: `send_user_message()` in "created" state raises `ConnectionNotReady`)
- [ ] Existing tests pass: `uv run pytest-llm`

### Edge Cases (from design/edge-cases.md)

- **EC1: Harness subprocess dies mid-turn** — events() yields final error event, completes. State → "failed".
- **EC4: Adapter starts but harness won't connect** — start() times out after 30s, raises ConnectionTimeout. State → "failed".
- **EC8: Malformed harness events** — log and skip, don't crash events() iterator.
- **EC10: Port conflicts** — Port 0 auto-assign avoids this for our WS server.
- **D52 stability risk** — Version gating, protocol mismatch detection, hybrid fallback path documented but NOT implemented in MVP (complexity budget). The fallback is designed-in for post-MVP.

---

## Sub-step 1C: Codex Connection (`CodexConnection`)

**Scope**: Implement the Codex bidirectional adapter. Codex runs a WS server; we connect as a client via JSON-RPC 2.0.

**Round**: 2 (parallel with 1B, 1D, 1E).

### Files to Create

- `src/meridian/lib/harness/connections/codex_ws.py` — `CodexConnection` class implementing `HarnessConnection`:
  - `start()`: launch `codex app-server --listen ws://127.0.0.1:<port>`, connect as WS client, perform JSON-RPC handshake (`initialize` → capabilities → `initialized`), start thread (`thread/start`), start first turn (`turn/start` with prompt)
  - `events()`: yield `HarnessEvent` from JSON-RPC notifications (`item/agentMessage`, `item/commandExecution`, `item/fileChange`, `turn/completed`, etc.)
  - `send_user_message()`: send `turn/steer` if in-flight turn (with `expectedTurnId`), else `turn/start` for new turn
  - `send_interrupt()`: send `turn/interrupt` JSON-RPC request
  - `send_cancel()`: close connection, transition to stopping
  - `stop()`: close WS, terminate subprocess
  - JSON-RPC ID tracking for request/response correlation
  - Turn ID tracking for steer vs start decision

### Files to Modify

- `src/meridian/lib/harness/codex.py` — Add `supports_bidirectional=True` to capabilities
- `src/meridian/lib/harness/connections/__init__.py` — Register `CodexConnection`

### Dependencies

- Requires: Phase 1A
- Independent of: Phase 1B, 1D, 1E

### Interface Contract

```python
class CodexConnection:
    capabilities = ConnectionCapabilities(
        mid_turn_injection="interrupt_restart",
        supports_steer=True,
        supports_interrupt=True,
        supports_cancel=True,
        runtime_model_switch=False,
        structured_reasoning=True,  # Codex emits item/reasoning
    )
```

### Wire Format Reference

**Outbound (Codex → us)** — JSON-RPC 2.0 notifications:
```json
{"jsonrpc": "2.0", "method": "item/agentMessage", "params": {"turnId": "...", "delta": "..."}}
{"jsonrpc": "2.0", "method": "turn/completed", "params": {"turnId": "..."}}
```

**Inbound (us → Codex)** — JSON-RPC 2.0 requests:
```json
{"jsonrpc": "2.0", "id": 1, "method": "turn/start", "params": {"prompt": "..."}}
{"jsonrpc": "2.0", "id": 2, "method": "turn/steer", "params": {"expectedTurnId": "...", "message": "..."}}
```

### Verification Criteria

- [ ] `uv run pyright` passes
- [ ] `uv run ruff check .` passes
- [ ] `CodexConnection` satisfies `HarnessConnection` protocol
- [ ] State machine transitions enforced
- [ ] JSON-RPC request IDs increment correctly
- [ ] Turn tracking: steer vs start decision based on active turn state
- [ ] Existing tests pass: `uv run pytest-llm`

### Edge Cases

- **EC1: Harness dies mid-turn** — WS close detected, error event emitted, state → "failed"
- **EC3: Inbound during mid-tool** — `turn/steer` is always accepted; Codex handles timing
- **EC4: Harness won't handshake** — timeout on `initialize` response
- **EC12: Large initial prompt** — truncate `turn/start` prompt at 50KB with warning

---

## Sub-step 1D: OpenCode Connection (`OpenCodeConnection`)

**Scope**: Implement the OpenCode bidirectional adapter using HTTP session API (D45: issue #13388 not merged, use HTTP).

**Round**: 2 (parallel with 1B, 1C, 1E).

### Files to Create

- `src/meridian/lib/harness/connections/opencode_http.py` — `OpenCodeConnection` class implementing `HarnessConnection`:
  - `start()`: launch `opencode serve --port <auto-port>`, poll health endpoint until ready, create session via POST, send initial prompt as first message
  - `events()`: stream responses from NDJSON event endpoint, parse SSE frames, yield `HarnessEvent` objects
  - `send_user_message()`: POST to session message endpoint
  - `send_interrupt()`: POST cancel to session endpoint
  - `send_cancel()`: POST cancel, transition to stopping
  - `stop()`: terminate subprocess, clean up HTTP client
  - Health check: GET health endpoint

### Files to Modify

- `src/meridian/lib/harness/opencode.py` — Add `supports_bidirectional=True` to capabilities
- `src/meridian/lib/harness/connections/__init__.py` — Register `OpenCodeConnection`

### Dependencies

- Requires: Phase 1A
- Independent of: Phase 1B, 1C, 1E

### Interface Contract

```python
class OpenCodeConnection:
    capabilities = ConnectionCapabilities(
        mid_turn_injection="http_post",
        supports_steer=False,
        supports_interrupt=True,
        supports_cancel=True,
        runtime_model_switch=False,
        structured_reasoning=True,
    )
```

### Verification Criteria

- [ ] `uv run pyright` passes
- [ ] `uv run ruff check .` passes
- [ ] `OpenCodeConnection` satisfies `HarnessConnection` protocol
- [ ] State machine transitions enforced
- [ ] HTTP client properly closed on stop()
- [ ] SSE/NDJSON parsing handles incomplete lines gracefully
- [ ] Existing tests pass: `uv run pytest-llm`

### Edge Cases

- **EC1: Harness dies** — HTTP connection error, state → "failed"
- **EC3: Inbound during mid-tool** — HTTP POST always accepted; OpenCode queues internally
- **EC4: Harness won't start** — health endpoint poll timeout
- **EC8: Malformed events** — SSE parse errors logged and skipped

---

## Sub-step 1E: SpawnManager and Control Socket

**Scope**: Build the central coordination layer — SpawnManager (connection registry, durable drain, fan-out) and ControlSocketServer (per-spawn Unix domain socket for cross-process inject).

**Round**: 2 (parallel with 1B, 1C, 1D).

### Files to Create

- `src/meridian/lib/streaming/spawn_manager.py` — `SpawnManager` class:
  - `SpawnSession` dataclass: groups connection, drain_task, subscriber queue, control_server per spawn
  - `start_spawn(config)`: resolve connection class, create connection, call start(), start drain task, start control socket, register in sessions dict
  - `_drain_loop(spawn_id, receiver)`: durable drain — read events(), persist to output.jsonl, fan-out to subscriber queue. Takes `HarnessReceiver` (ISP)
  - `subscribe(spawn_id)` / `unsubscribe(spawn_id)`: one subscriber per spawn (MVP)
  - `inject(spawn_id, message, source)`: write-ahead to inbound.jsonl, then route to connection
  - `interrupt(spawn_id, source)` / `cancel(spawn_id, source)`: same pattern
  - `_record_inbound(spawn_id, action, data, source)`: append to inbound.jsonl
  - `get_connection(spawn_id)`: lookup
  - `stop_spawn(spawn_id)`: stop connection, cancel drain task, stop control socket
  - `shutdown()`: stop all spawns, finalize states
  - `list_spawns()`: return active spawn IDs with metadata

- `src/meridian/lib/streaming/control_socket.py` — `ControlSocketServer` class:
  - `start()`: create Unix domain socket at `.meridian/spawns/<spawn_id>/control.sock`
  - `_handle_client()`: read one JSON message, route to SpawnManager (user_message/interrupt/cancel), respond with `{"ok": true/false}`
  - `stop()`: close server, unlink socket file
  - Protocol: one JSON line per connection, one response, then close

### Files to Modify

None — this is entirely new code. Depends only on Phase 1A types.

### Dependencies

- Requires: Phase 1A (HarnessConnection protocol, HarnessEvent, ConnectionConfig, InjectResult)
- Independent of: Phase 1B, 1C, 1D (SpawnManager depends on the protocol, not concrete implementations)

### Interface Contract

```python
class SpawnManager:
    async def start_spawn(self, config: ConnectionConfig) -> HarnessConnection: ...
    async def inject(self, spawn_id: SpawnId, message: str, source: str = "control_socket") -> InjectResult: ...
    async def interrupt(self, spawn_id: SpawnId, source: str = "control_socket") -> InjectResult: ...
    async def cancel(self, spawn_id: SpawnId, source: str = "control_socket") -> InjectResult: ...
    def subscribe(self, spawn_id: SpawnId) -> asyncio.Queue[HarnessEvent | None] | None: ...
    def unsubscribe(self, spawn_id: SpawnId) -> None: ...
    async def get_connection(self, spawn_id: SpawnId) -> HarnessConnection | None: ...
    async def stop_spawn(self, spawn_id: SpawnId) -> None: ...
    async def shutdown(self) -> None: ...
```

### Verification Criteria

- [ ] `uv run pyright` passes
- [ ] `uv run ruff check .` passes
- [ ] SpawnManager can be instantiated with mock connections
- [ ] Drain loop persists events to output.jsonl (testable with mock receiver)
- [ ] Inbound recording writes to inbound.jsonl before routing (write-ahead semantics)
- [ ] Control socket accepts JSON messages and returns responses
- [ ] Stale socket files are cleaned up on start (unlink before bind)
- [ ] Existing tests pass: `uv run pytest-llm`

### Edge Cases

- **EC2: Client disconnects** — drain task continues regardless of subscriber state (drain owns events(), not the UI)
- **EC5: Two processes control same spawn** — last-writer-wins at transport level, both messages delivered (MVP acceptable)
- **EC7: Output exceeds memory** — events are streamed one at a time, not accumulated
- **EC9: Socket left behind after crash** — `unlink(missing_ok=True)` before `start_unix_server()`
- **EC10: Concurrent WS clients** — MVP rejects second subscriber with error

---

## Sub-step 1F: CLI Commands and Runner Integration

**Scope**: Wire Phase 1 into the existing CLI — `meridian spawn inject`, `meridian streaming serve` headless runner, and the integration point in runner.py that makes every spawn bidirectional.

**Round**: 3 (needs 1B-1E complete).

### Files to Create

- `src/meridian/cli/spawn_inject.py` — `meridian spawn inject <spawn_id> "message"` command:
  - Connect to Unix domain socket at `.meridian/spawns/<spawn_id>/control.sock`
  - Send JSON control message, receive response
  - Support `--interrupt` and `--cancel` flags
  - Clear error messages: "spawn not found", "spawn not running", "connection refused"

- `src/meridian/cli/streaming_serve.py` — `meridian streaming serve` headless runner:
  - Creates SpawnManager, starts a spawn with specified harness/agent/prompt
  - Runs drain task (events → output.jsonl), serves control socket
  - Blocks until spawn completes or Ctrl-C
  - Graceful shutdown: cancel → wait → stop
  - Prints spawn_id on start, summary on exit

### Files to Modify

- `src/meridian/cli/main.py` — Register new CLI commands:
  - `meridian spawn inject` as subcommand under `spawn`
  - `meridian streaming serve` as new command group

- `src/meridian/lib/launch/runner.py` — Integration point: after launching subprocess, if harness `supports_bidirectional`:
  1. Create HarnessConnection from registry
  2. Call connection.start() to establish bidirectional transport
  3. Start durable drain task
  4. Start control socket server
  5. Register with global SpawnManager
  - This runs alongside existing stream_capture — same subprocess, additional transport

### Dependencies

- Requires: Phase 1A (types), 1B-1D (at least one connection for testing), 1E (SpawnManager, ControlSocket)
- This is the integration step that proves the Phase 1 layer works end-to-end

### Interface Contract

```bash
# CLI commands
meridian spawn inject <spawn_id> "message text"
meridian spawn inject <spawn_id> --interrupt
meridian spawn inject <spawn_id> --cancel

# Headless runner
meridian streaming serve --harness claude --agent my-agent -p "initial prompt"
meridian streaming serve --harness codex -p "do the task"
```

### Verification Criteria

- [ ] `uv run pyright` passes
- [ ] `uv run ruff check .` passes
- [ ] `meridian spawn inject` connects to control socket and delivers message
- [ ] `meridian streaming serve` starts a spawn, drains events to output.jsonl
- [ ] Control socket at `.meridian/spawns/<spawn_id>/control.sock` exists during spawn
- [ ] `inbound.jsonl` records inject actions with timestamps and source
- [ ] Graceful shutdown on Ctrl-C (SIGINT handling)
- [ ] `meridian spawn list` shows spawns started by `streaming serve`
- [ ] Existing CLI commands are not broken
- [ ] Existing tests pass: `uv run pytest-llm`

### Smoke Test (Phase 1 Gate)

Per-harness smoke test guides should be created as markdown files in `tests/smoke/`. Format per `smoke-test` skill:

**Claude Code smoke test**:
1. `meridian streaming serve --harness claude -p "List files in current directory"` → prints spawn_id
2. `meridian spawn list` → shows spawn running
3. `tail -f .meridian/spawns/<id>/output.jsonl` → events flowing
4. `meridian spawn inject <id> "What files have you read?"` → message delivered
5. Verify inbound.jsonl recorded the inject
6. Verify output.jsonl shows Claude's response to the inject
7. `meridian spawn inject <id> --interrupt` → interrupt delivered

**Codex and OpenCode**: same pattern, verifying per-harness wire format differences.

### Edge Cases

- **Stale control socket** — inject reports "spawn not found or not running" on ConnectionRefusedError
- **Spawn already finished** — inject reports "spawn not running or already finished" if no control.sock
- **Runner integration** — if connection.start() fails, spawn continues in fire-and-forget mode (bidirectional is additive, not blocking)
