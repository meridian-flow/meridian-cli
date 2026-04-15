# Harness Abstraction — SOLID Interface Design

This document defines the bidirectional harness interface that Phase 1 builds and all subsequent phases depend on. It is the most load-bearing surface in the design — getting it wrong means adding a new harness requires rewriting everything above it.

## Design Principles

The abstraction must satisfy five constraints simultaneously:

1. **Topology hiding** — Claude Code makes our process the WS server; Codex makes our process the WS client; OpenCode uses HTTP. Callers never see this difference.
2. **Semantic honesty** — the three harnesses have genuinely different mid-turn injection semantics (queue vs. interrupt-restart vs. HTTP POST). The abstraction unifies the delivery mechanism but surfaces the semantic difference via capability introspection.
3. **Coexistence with fire-and-forget** — the existing `SubprocessHarness` protocol stays. Bidirectional adapters extend, not replace.
4. **Testability** — each adapter is independently testable with a mock harness process or recorded fixture.
5. **One interface, two consumers** — the Phase 2 FastAPI server and the `meridian spawn inject` CLI both consume the same interface.

## Interface Hierarchy (ISP)

```python
from typing import AsyncIterator, Literal, Protocol
from dataclasses import dataclass

# ─── Capability introspection ────────────────────────────────────

@dataclass(frozen=True)
class ConnectionCapabilities:
    """Semantic capabilities of this harness connection.

    Consumers use this to render the right affordances. The UI shows
    "message queued for next turn" for Claude, "this will interrupt
    the current turn" for Codex, and a normal send button for OpenCode.

    Lives on HarnessConnection (the composite), NOT on HarnessReceiver.
    Consumers that only receive events (log writers, metrics collectors)
    shouldn't need to know about send-side capability metadata.
    """
    mid_turn_injection: Literal["queue", "interrupt_restart", "http_post"]
    supports_steer: bool          # Can append to in-flight turn without restart
    supports_interrupt: bool      # Can cancel current turn
    supports_cancel: bool         # Can terminate the entire spawn
    runtime_model_switch: bool    # Can change model after launch
    structured_reasoning: bool    # Emits thinking/reasoning events

# ─── Connection state machine ───────────────────────────────────

ConnectionState = Literal[
    "created",     # Constructed, not yet started
    "starting",    # start() called, transport establishing
    "connected",   # Transport up, events flowing, send_*() valid
    "stopping",    # stop() or send_cancel() called, tearing down
    "stopped",     # Clean shutdown complete
    "failed",      # Unrecoverable error (process crash, transport death)
]

# Transition rules:
#   created   → starting  (start() called)
#   starting  → connected (transport established, harness ready)
#   starting  → failed    (timeout, process crash during startup)
#   connected → stopping  (stop() or send_cancel() called)
#   connected → failed    (harness process dies unexpectedly)
#   stopping  → stopped   (clean shutdown complete)
#   stopping  → failed    (shutdown timeout, SIGKILL needed)
#   failed    → stopped   (stop() called for cleanup — teardown resources)
#
# stop() behavior by state:
#   "connected" → normal shutdown: connected → stopping → stopped
#   "stopping"  → idempotent: already tearing down, wait for completion
#   "stopped"   → no-op (already stopped)
#   "failed"    → cleanup: close transport, kill process if alive → stopped
#   "created"   → no-op (nothing to stop)
#   "starting"  → abort: cancel startup → failed → stopped
#
# Normal cancel-then-stop sequence:
#   send_cancel() transitions connected → stopping (signals harness)
#   Caller waits for events() to drain (harness may finish current tool)
#   stop() transitions stopping → stopped (tears down transport, kills process)
#
# Forced shutdown (skip graceful cancel):
#   stop() transitions connected → stopping → stopped directly
#
# Behavioral contracts per state:
#   send_*() methods raise ConnectionNotReady if state != "connected"
#   events() yields remaining buffered events in "stopping", then completes
#   events() yields nothing in "stopped" or "failed" (immediate StopAsyncIteration)
#   health() returns True only in "connected" state

class ConnectionNotReady(Exception):
    """Raised when send_*() is called on a connection not in 'connected' state."""
    pass

# ─── Event types from harness ────────────────────────────────────

@dataclass(frozen=True)
class HarnessEvent:
    """Raw event from the harness, before AG-UI mapping.

    Each adapter emits HarnessEvents with harness-specific event_type
    strings and raw payloads. The Phase 2 AG-UI mapper consumes these
    and transforms them into ag_ui.core event objects.

    The harness_id field makes events self-describing — if events are
    logged, replayed, or routed through a queue, the mapper can dispatch
    on harness_id without holding external state.
    """
    event_type: str                    # Harness-specific: "assistant", "tool_use", "item/agentMessage", etc.
    payload: dict[str, object]         # Raw JSON payload from the harness wire format
    harness_id: str                    # Which harness produced this event ("claude", "codex", "opencode")
    raw_text: str | None = None        # Original wire text (for debugging / logging)

# ─── Segregated interfaces (ISP) ────────────────────────────────

class HarnessLifecycle(Protocol):
    """Start, stop, and health-check a harness connection."""

    async def start(self, config: "ConnectionConfig") -> None:
        """Launch the harness subprocess and establish the bidirectional channel.

        Transitions: created → starting → connected (or → failed on timeout).

        For Claude: start a WS server, launch `claude --sdk-url`, wait for connection.
        For Codex: launch `codex app-server`, connect as WS client, complete handshake.
        For OpenCode: launch `opencode serve`, wait for HTTP readiness.
        """
        ...

    async def stop(self) -> None:
        """Gracefully shut down the harness subprocess.

        Transitions: connected → stopping → stopped (or → failed on timeout).

        Sends appropriate shutdown signal, waits for process exit with timeout,
        then SIGKILL if necessary. Cleans up transport resources (close WS, etc.).
        """
        ...

    async def health(self) -> bool:
        """Return True if the harness subprocess is alive and the transport is connected.

        Returns True only when state == "connected".
        """
        ...

    @property
    def state(self) -> ConnectionState:
        """Current connection state. See ConnectionState for transition rules."""
        ...


class HarnessSender(Protocol):
    """Send messages and control signals to the harness."""

    async def send_user_message(self, text: str) -> None:
        """Deliver a user message to the running harness.

        Raises ConnectionNotReady if state != "connected".

        Semantics vary by harness (see ConnectionCapabilities.mid_turn_injection):
        - Claude (queue): sends {"type": "user", "content": text} over WS;
          Claude queues it for the next turn boundary.
        - Codex (interrupt_restart): sends turn/steer JSON-RPC if a turn is
          in-flight (appends to current turn), or turn/start for a new turn.
        - OpenCode (http_post): POSTs to the session's message endpoint.
        """
        ...

    async def send_interrupt(self) -> None:
        """Interrupt the current turn without terminating the spawn.

        Raises ConnectionNotReady if state != "connected".

        - Claude: sends interrupt signal; Claude stops current generation.
        - Codex: sends turn/interrupt JSON-RPC.
        - OpenCode: POSTs cancel to the session endpoint.
        """
        ...

    async def send_cancel(self) -> None:
        """Cancel the entire spawn. Transitions connection to "stopping".

        After this call completes, the connection is in "stopping" or "stopped"
        state. The caller should then call stop() to finalize teardown.

        Lifecycle: send_cancel() signals intent to the harness (it may finish
        current tool execution then exit). stop() tears down the transport and
        kills the process if it hasn't exited.

        Normal shutdown: send_cancel() → wait for events() to complete → stop()
        Forced shutdown: stop() directly (skips graceful cancel signal)
        """
        ...


class HarnessReceiver(Protocol):
    """Receive events from the harness.

    Standalone use: SpawnManager._drain_loop() accepts HarnessReceiver,
    not the full HarnessConnection. This makes the drain task testable
    with a mock receiver and keeps the ISP boundary honest — the drain
    only needs to iterate events, not send messages or check capabilities.
    """

    def events(self) -> AsyncIterator[HarnessEvent]:
        """Async iterator of events from the harness.

        Yields HarnessEvent objects until the harness finishes, errors, or
        the connection is closed. The iterator completes (StopAsyncIteration)
        when the harness process exits.

        In "stopping" state: yields remaining buffered events, then completes.
        In "stopped" or "failed" state: immediate StopAsyncIteration.
        """
        ...
```

## Composite Interface

```python
class HarnessConnection(HarnessLifecycle, HarnessSender, HarnessReceiver, Protocol):
    """Complete bidirectional harness connection.

    A HarnessConnection is the unit of work for Phase 1. The SpawnManager
    holds one per active spawn. Phase 2's WebSocket endpoint reads from
    its events() iterator and writes through its send_*() methods.

    Capabilities and harness_id live here (on the composite), not on
    HarnessReceiver. Consumers that only need to receive events
    (e.g., log writers) use HarnessReceiver without capability metadata.
    """

    @property
    def harness_id(self) -> "HarnessId":
        """Which harness this connection wraps."""
        ...

    @property
    def spawn_id(self) -> "SpawnId":
        """Which spawn this connection belongs to."""
        ...

    @property
    def capabilities(self) -> ConnectionCapabilities:
        """Capabilities of this connection. Available after state reaches 'connected'."""
        ...
```

## Connection Configuration

```python
@dataclass(frozen=True)
class ConnectionConfig:
    """Everything a connection needs to launch and connect to a harness."""

    spawn_id: SpawnId
    harness_id: HarnessId
    model: str | None
    agent: str | None                     # Agent profile name
    prompt: str                           # Initial prompt text
    repo_root: Path                       # Working directory for the harness
    env_overrides: dict[str, str]         # Environment variables to pass
    extra_args: tuple[str, ...] = ()      # Additional CLI args
    skills: tuple[str, ...] = ()          # Skills to load
    continue_session_id: str | None = None  # For session resume
    timeout_seconds: float | None = None  # Spawn timeout

    # Transport config — these fields are Claude-specific (WS server).
    # Known SRP violation: transport knobs belong in adapter-private config.
    # Acceptable for 3 harnesses with 2 transport fields; if a 4th harness
    # needs transport config (e.g., gRPC port), refactor to a
    # transport_config: dict[str, Any] or per-adapter dataclass.
    ws_bind_host: str = "127.0.0.1"      # For Claude: WS server bind address
    ws_port: int = 0                       # 0 = auto-assign
```

## Per-Harness Implementations

### Claude Code — `ClaudeConnection`

**Topology**: We are the WebSocket server. Claude CLI connects to us.

```
┌──────────┐    WS connect    ┌──────────────┐
│ Claude   │ ──────────────►  │ Our WS Server│
│ CLI      │ ◄──────────────  │ (asyncio)    │
│ process  │   bidirectional  │              │
└──────────┘    NDJSON        └──────────────┘
```

**Launch sequence**:
1. Start an asyncio WebSocket server on `127.0.0.1:<auto-port>` using `websockets.serve()`
2. Build the Claude command: `claude --sdk-url ws://127.0.0.1:<port> --output-format stream-json --verbose`
3. Launch the subprocess via `asyncio.create_subprocess_exec()`
4. Wait for Claude to connect to our WS server (with timeout)
5. Send the initial prompt as a `{"type": "user", "content": "<prompt>"}` message
6. Begin yielding events from the WS connection

**Wire format (Claude → us)**:
```json
{"type": "assistant", "message": {"content": [...]}}
{"type": "stream_event", "event": {"type": "content_block_delta", ...}}
{"type": "tool_progress", "tool_use_id": "...", "progress": "..."}
{"type": "tool_use_summary", "tool_use_id": "...", "name": "...", "result": "..."}
{"type": "result", "result": "...", "duration_ms": 1234}
```

**Wire format (us → Claude)**:
```json
{"type": "user", "content": "user message text"}
```

**Mid-turn semantics**: `queue` — message queues until current turn completes, then Claude processes it as the next turn.

**Stability risk and mitigation**: `--sdk-url` is reverse-engineered from the companion project, not officially documented by Anthropic. The adapter must implement an explicit compatibility contract:

1. **Version gating**: document exact Claude CLI versions tested (minimum version, known-working versions). On startup, check `claude --version` and warn if untested.
2. **Protocol mismatch detection**: if the WS connection is established but the first message doesn't match expected NDJSON format, log the raw bytes and fail with a specific `ProtocolMismatchError` (not a generic timeout).
3. **Feature flag**: `--sdk-url` is behind a `claude_bidirectional_transport` config flag, defaulting to "on" for known-good versions and "off" for unknown versions.
4. **Hybrid fallback (concrete)**: if `--sdk-url` fails or is disabled, fall back to:
   - **Receive**: launch with `--output-format stream-json --verbose`, capture NDJSON from stdout (same as existing fire-and-forget capture in `stream_capture.py`).
   - **Send**: HTTP POST to `CLAUDE_CODE_POST_FOR_SESSION_INGRESS_V2` (requires session ID discovery from the harness's environment or startup output).
   - **Limitation**: hybrid mode may have higher latency for injection and cannot guarantee message ordering relative to the output stream.
5. **Detection of breakage**: if three consecutive WS sends get no response within 5s, log a warning and surface it in `meridian spawn show` output.

### Codex — `CodexConnection`

**Topology**: Codex runs a WebSocket server. We connect as a client.

```
┌──────────┐                  ┌──────────────┐
│ Codex    │ ◄──────────────  │ Our WS Client│
│ app-svr  │ ──────────────►  │ (asyncio)    │
│ process  │   bidirectional  │              │
└──────────┘   JSON-RPC 2.0  └──────────────┘
```

**Launch sequence**:
1. Launch Codex: `codex app-server --listen ws://127.0.0.1:<port>` with auto-assigned port
2. Connect to the Codex WS server as a client using `websockets.connect()`
3. Perform JSON-RPC handshake: send `initialize` request, receive capabilities, send `initialized` notification
4. Start a thread: send `thread/start` with `{model, cwd, approvalPolicy, sandbox}`
5. Start first turn: send `turn/start` with the initial prompt
6. Begin yielding events from `item/*` notifications

**Wire format (Codex → us)** — JSON-RPC 2.0 notifications:
```json
{"jsonrpc": "2.0", "method": "item/agentMessage", "params": {"turnId": "...", "delta": "..."}}
{"jsonrpc": "2.0", "method": "item/commandExecution", "params": {"turnId": "...", "command": "..."}}
{"jsonrpc": "2.0", "method": "item/fileChange", "params": {"turnId": "...", "path": "..."}}
{"jsonrpc": "2.0", "method": "turn/completed", "params": {"turnId": "..."}}
```

**Wire format (us → Codex)** — JSON-RPC 2.0 requests:
```json
{"jsonrpc": "2.0", "id": 1, "method": "turn/start", "params": {"prompt": "..."}}
{"jsonrpc": "2.0", "id": 2, "method": "turn/steer", "params": {"expectedTurnId": "...", "message": "..."}}
{"jsonrpc": "2.0", "id": 3, "method": "turn/interrupt", "params": {"turnId": "..."}}
```

**Mid-turn semantics**: `interrupt_restart` — `turn/steer` appends a user message to the in-flight turn (requires `expectedTurnId`). If the turn has already completed, falls back to `turn/start` for a new turn.

### OpenCode — `OpenCodeConnection`

**Topology**: We are an HTTP client to OpenCode's session API.

```
┌──────────┐    HTTP/NDJSON   ┌──────────────┐
│ OpenCode │ ◄──────────────  │ Our HTTP     │
│ serve    │ ──────────────►  │ Client       │
│ process  │   (SSE/NDJSON)  │ (aiohttp)    │
└──────────┘                  └──────────────┘
```

**Launch sequence**:
1. Launch OpenCode: `opencode serve --port <auto-port>`
2. Wait for HTTP readiness (poll health endpoint with timeout)
3. Create a session via POST
4. Send the initial prompt as a user message
5. Stream responses via the NDJSON event stream endpoint

**Mid-turn semantics**: `http_post` — POST a new message to the session endpoint. OpenCode handles it as the next input, which is the cleanest injection model of the three.

**Note on WebSocket transport**: OpenCode issue #13388 proposes a `/acp` WebSocket endpoint. If merged by implementation time, the adapter should prefer WebSocket over HTTP for lower latency. The HTTP path serves as the stable fallback.

## Adapter Registration

```python
# src/meridian/lib/harness/connections/__init__.py

from meridian.lib.core.types import HarnessId

_CONNECTION_REGISTRY: dict[HarnessId, type[HarnessConnection]] = {}

def register_connection(harness_id: HarnessId, cls: type[HarnessConnection]) -> None:
    _CONNECTION_REGISTRY[harness_id] = cls

def get_connection_class(harness_id: HarnessId) -> type[HarnessConnection]:
    if harness_id not in _CONNECTION_REGISTRY:
        raise ValueError(f"No bidirectional connection registered for {harness_id}")
    return _CONNECTION_REGISTRY[harness_id]

# Registration happens at module import
register_connection(HarnessId.CLAUDE, ClaudeConnection)
register_connection(HarnessId.CODEX, CodexConnection)
register_connection(HarnessId.OPENCODE, OpenCodeConnection)
```

**OCP compliance**: adding a new harness = one new file in `connections/`, one `register_connection()` call. Zero modifications to `SpawnManager`, `ws_endpoint`, or AG-UI mappers for existing harnesses.

**DIP compliance**: `SpawnManager` depends on `HarnessConnection` (the protocol), never on `ClaudeConnection` directly. The `get_connection_class()` factory resolves the concrete type at spawn time.

**LSP compliance**: any `HarnessConnection` implementation is substitutable. `SpawnManager.inject(spawn_id, message)` calls `connection.send_user_message(message)` without knowing which harness is underneath.

## Relationship to Existing `SubprocessHarness`

The existing `SubprocessHarness` protocol in `adapter.py` handles:
- Command building (`build_command`)
- Environment overrides (`env_overrides`)
- Report/session/usage extraction from artifacts
- Session seeding and prompt filtering

The new `HarnessConnection` handles:
- Transport establishment and teardown
- Bidirectional message passing
- Event streaming

These are **separate concerns, not a replacement**. A harness has both:
- A `SubprocessHarness` implementation (for fire-and-forget spawns and command building)
- A `HarnessConnection` implementation (for bidirectional spawns)

The `ConnectionConfig` may use information from the `SubprocessHarness` (e.g., model resolution, agent profile loading) but the connection itself doesn't depend on the subprocess harness protocol. This separation means:
- Every spawn uses the `HarnessConnection` path (bidirectional is universal — see phase-1-streaming.md)
- Fire-and-forget semantics are preserved: callers that never call `send_*()` get the same behavior as before
- Both paths share the same spawn state infrastructure (`.meridian/spawns/`, `spawn_store`, heartbeat, etc.)

### Capability model boundary

`HarnessCapabilities` (on `SubprocessHarness`) gains only a boolean `supports_bidirectional: bool = False` to indicate whether a `HarnessConnection` implementation exists for this harness. **No `mid_turn_injection` enum on the fire-and-forget side.** Code that needs injection semantics always goes through `ConnectionCapabilities` on `HarnessConnection`. This eliminates dual-source divergence — there is one place to look for bidirectional capability metadata, and it's `ConnectionCapabilities`.

## Thread Safety and Concurrency Model

All `HarnessConnection` methods are async and must be called from the same asyncio event loop. The connection is **not thread-safe** — it is owned by one `SpawnManager` task.

Concurrency within one connection:
- One task reads from `events()` (the outbound path — owned by the durable drain task, see phase-1-streaming.md)
- Other tasks call `send_user_message()` / `send_interrupt()` / `send_cancel()` (the inbound path)
- The adapter implementation must handle concurrent send/receive internally (typically via an asyncio Lock on the transport)
- State transitions are enforced by the adapter: `send_*()` methods raise `ConnectionNotReady` if `state != "connected"`, so callers don't need to implement defensive state-checking logic

Concurrency across connections:
- `SpawnManager` holds a `dict[SpawnId, HarnessConnection]` and dispatches inject requests by spawn ID
- Each connection is independent — no shared state between adapters for different spawns
