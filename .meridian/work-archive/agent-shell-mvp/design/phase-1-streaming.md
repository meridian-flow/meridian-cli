# Phase 1 — Bidirectional Streaming Foundation

Phase 1 delivers the universal bidirectional streaming layer. Every spawn — Claude Code, Codex, OpenCode — gains input-channel writability while it's reading from the output. **Not a flag. Not a mode. Not a new invocation shape.** The underlying mechanism is universal and always available; fire-and-forget spawns still work exactly as they do today if the caller ignores the input side.

This is the foundation that Phase 2 and 3 build on.

## Deliverables

1. **`HarnessConnection` implementations** for all three tier-1 harnesses (see [harness-abstraction.md](harness-abstraction.md))
2. **`SpawnManager`** — in-process registry of active connections with durable event drain
3. **Control socket** — per-spawn Unix domain socket for cross-process `inject`
4. **`meridian spawn inject <spawn_id> "message"`** — CLI command for mid-turn injection
5. **Headless runner** — `meridian streaming serve` for Phase 1-only testing without FastAPI
6. **Smoke tests** — per-harness manual smoke test guides

## SpawnManager

The `SpawnManager` is the central coordination point for all spawns. It lives at `src/meridian/lib/streaming/spawn_manager.py`.

### Durable drain architecture

The most critical architectural property: **one durable reader per spawn that always drains the harness transport into `output.jsonl`, independent of any UI client.** UI clients are strictly consumers of a fan-out mechanism — they never own the drain.

```
┌──────────────┐     events()     ┌─────────────────┐
│   Harness    │ ───────────────► │  Drain Task     │ ──► output.jsonl (always)
│  Connection  │                  │  (1 per spawn)  │ ──► Queue A → WS client 1
└──────────────┘                  │                  │ ──► Queue B → WS client 2
                                  └─────────────────┘ ──► Queue N → future clients
```

This design means:
- **Client disconnect cannot stall the harness stream.** The drain task reads `connection.events()` regardless of whether any UI is connected.
- **Output is always persisted.** Every `HarnessEvent` is appended to `output.jsonl` before fan-out to clients.
- **Reconnecting clients** can read `output.jsonl` for history and subscribe to the live fan-out for new events.
- **`meridian spawn log`** works for bidirectional spawns exactly as it does for fire-and-forget spawns.

### Fan-out mechanism

Each connected UI client gets an `asyncio.Queue` that the drain task feeds. When a client disconnects, its queue is removed from the subscriber set. The drain task never blocks on a slow consumer — if a queue is full (bounded at 1000 events), events are dropped for that subscriber with a warning logged.

**MVP simplification**: one UI client per spawn. If a second WebSocket client connects to the same spawn, the endpoint returns an error (`{"type": "RUN_ERROR", "message": "another client is already connected to this spawn"}`). Fan-out to multiple concurrent clients is post-MVP.

```python
class SpawnManager:
    """Registry of active harness connections with durable event drain.

    Thin registry + lifecycle coordinator. Per-spawn state is grouped in
    SpawnSession (see below) to keep SpawnManager's responsibility narrow:
    it owns the collection, not the per-spawn concerns.
    """

    def __init__(self, state_root: Path, repo_root: Path):
        self._sessions: dict[SpawnId, "SpawnSession"] = {}
        self._state_root = state_root
        self._repo_root = repo_root

# Per-spawn state grouping:
@dataclass
class SpawnSession:
    """All per-spawn resources grouped together.

    SpawnManager holds a dict of these. Each SpawnSession owns its
    connection, drain task, subscriber queue, and control socket server.
    This keeps SpawnManager thin — it coordinates lifecycle across sessions
    but doesn't hold 5 parallel dicts keyed by spawn_id.
    """
    connection: HarnessConnection
    drain_task: asyncio.Task
    subscriber: asyncio.Queue[HarnessEvent | None] | None  # None if no UI client
    control_server: ControlSocketServer

    async def start_spawn(
        self,
        config: ConnectionConfig,
    ) -> HarnessConnection:
        """Launch a new spawn with bidirectional streaming.

        1. Resolves the connection class from config.harness_id
        2. Records the spawn in spawn_store (status: "running")
        3. Creates the HarnessConnection and calls start()
        4. Starts the durable drain task
        5. Starts the control socket listener
        6. Registers the connection

        Returns the connection for the caller to query capabilities.
        """
        ...

    async def _drain_loop(self, spawn_id: SpawnId, receiver: HarnessReceiver) -> None:
        """Durable drain: reads events from harness, persists to output.jsonl,
        fans out to any connected subscriber queues.

        Takes HarnessReceiver (not the full HarnessConnection) — the drain
        only needs to iterate events, not send messages or check capabilities.
        This keeps the ISP boundary honest and makes the drain testable with
        a mock receiver.

        This task runs for the lifetime of the spawn and is the ONLY consumer
        of receiver.events(). It never stops because a UI client disconnected.
        """
        output_path = self._state_root / "spawns" / str(spawn_id) / "output.jsonl"
        async with aiofiles.open(output_path, "a") as f:
            async for event in receiver.events():
                # Always persist first
                line = json.dumps({
                    "event_type": event.event_type,
                    "payload": event.payload,
                    "harness_id": event.harness_id,
                    "ts": time.time(),
                }) + "\n"
                await f.write(line)
                await f.flush()

                # Then fan out to subscribers (non-blocking)
                queue = self._subscribers.get(spawn_id)
                if queue is not None:
                    try:
                        queue.put_nowait(event)
                    except asyncio.QueueFull:
                        pass  # Drop event for slow subscriber; it's in output.jsonl

            # Signal end-of-stream to subscribers
            queue = self._subscribers.get(spawn_id)
            if queue is not None:
                await queue.put(None)  # Sentinel

    def subscribe(self, spawn_id: SpawnId) -> asyncio.Queue[HarnessEvent | None] | None:
        """Subscribe a UI client to a spawn's event stream.

        Returns a Queue that will receive HarnessEvents, or None if the
        spawn doesn't exist. Returns error if a subscriber already exists
        (MVP: one client per spawn).

        The sentinel value None signals end-of-stream.
        """
        if spawn_id not in self._connections:
            return None
        if spawn_id in self._subscribers:
            return None  # Already has a subscriber — reject
        queue: asyncio.Queue[HarnessEvent | None] = asyncio.Queue(maxsize=1000)
        self._subscribers[spawn_id] = queue
        return queue

    def unsubscribe(self, spawn_id: SpawnId) -> None:
        """Remove a UI client's subscription."""
        self._subscribers.pop(spawn_id, None)

    async def inject(self, spawn_id: SpawnId, message: str, source: str = "control_socket") -> InjectResult:
        """Send a user message to a running spawn.

        Write-ahead-log semantics: records the intent to inbound.jsonl BEFORE
        routing to the harness. If the process crashes between record and send,
        the audit trail still captures the user's intervention.

        Returns InjectResult indicating success, or an error if the spawn
        is not found, not running, or the adapter rejected the message.
        """
        connection = self._connections.get(spawn_id)
        if connection is None:
            return InjectResult(success=False, error="spawn not found")
        try:
            # Record intent first (write-ahead)
            await self._record_inbound(spawn_id, "user_message", {"text": message}, source=source)
            # Then deliver
            await connection.send_user_message(message)
            return InjectResult(success=True)
        except ConnectionNotReady as e:
            return InjectResult(success=False, error=f"connection not ready: {e}")
        except Exception as e:
            return InjectResult(success=False, error=str(e))

    async def interrupt(self, spawn_id: SpawnId, source: str = "control_socket") -> InjectResult:
        """Interrupt the current turn of a running spawn."""
        connection = self._connections.get(spawn_id)
        if connection is None:
            return InjectResult(success=False, error="spawn not found")
        try:
            await self._record_inbound(spawn_id, "interrupt", {}, source=source)
            await connection.send_interrupt()
            return InjectResult(success=True)
        except ConnectionNotReady as e:
            return InjectResult(success=False, error=f"connection not ready: {e}")
        except Exception as e:
            return InjectResult(success=False, error=str(e))

    async def cancel(self, spawn_id: SpawnId, source: str = "control_socket") -> InjectResult:
        """Cancel a running spawn entirely."""
        connection = self._connections.get(spawn_id)
        if connection is None:
            return InjectResult(success=False, error="spawn not found")
        try:
            await self._record_inbound(spawn_id, "cancel", {}, source=source)
            await connection.send_cancel()
            return InjectResult(success=True)
        except Exception as e:
            return InjectResult(success=False, error=str(e))

    async def _record_inbound(self, spawn_id: SpawnId, action: str, data: dict, source: str = "control_socket") -> None:
        """Record an inbound steering action to the spawn's inbound.jsonl.

        Called BEFORE routing to the harness (write-ahead-log semantics).
        See 'Inbound Action Recording' section below.
        """
        inbound_path = self._state_root / "spawns" / str(spawn_id) / "inbound.jsonl"
        record = json.dumps({
            "action": action,
            "data": data,
            "ts": time.time(),
            "source": source,
        }) + "\n"
        async with aiofiles.open(inbound_path, "a") as f:
            await f.write(record)

    async def get_connection(self, spawn_id: SpawnId) -> HarnessConnection | None:
        """Get the connection for a spawn, or None if not found."""
        return self._connections.get(spawn_id)

    async def stop_spawn(self, spawn_id: SpawnId) -> None:
        """Stop a spawn and clean up its resources."""
        ...

    async def shutdown(self) -> None:
        """Stop all spawns and clean up. Called on process exit."""
        ...
```

## Inbound Action Recording (Files-as-Authority)

All inbound steering actions — `user_message`, `interrupt`, `cancel` — are durably recorded to `.meridian/spawns/<spawn_id>/inbound.jsonl` **before** being routed to the harness (write-ahead-log semantics). If the process crashes between recording and delivery, the audit trail still captures the user's intent. This satisfies the files-as-authority principle: the most important user interventions during a spawn are recoverable from the filesystem.

Format:
```json
{"action": "user_message", "data": {"text": "reconsider the auth approach"}, "ts": 1712680000.0, "source": "websocket"}
{"action": "interrupt", "data": {}, "ts": 1712680010.0, "source": "control_socket"}
{"action": "cancel", "data": {}, "ts": 1712680020.0, "source": "websocket"}
```

The `source` field distinguishes whether the action came from a WebSocket UI client or a `meridian spawn inject` CLI call (via control socket). This audit trail is critical for dogfooding — when a user steers a run mid-turn, that decision must survive in the authority-bearing record.

## Headless Runner

Phase 1 must be independently testable without Phase 2 (FastAPI). A headless runner command starts a `SpawnManager`, launches a bidirectional spawn, and keeps the control socket alive:

```bash
meridian streaming serve --harness claude --agent my-agent -p "initial prompt"
# → Starts SpawnManager, launches spawn, prints spawn_id
# → Control socket at .meridian/spawns/<id>/control.sock
# → Events drain to output.jsonl
# → Ctrl-C sends cancel + graceful shutdown
```

This command:
1. Creates a `SpawnManager` instance
2. Starts a spawn with the specified harness/agent/prompt
3. Runs the drain task (events → output.jsonl)
4. Serves the control socket for `meridian spawn inject`
5. Blocks until the spawn completes or Ctrl-C
6. Prints a summary on exit

Without this command, Phase 1's "test independently via `meridian spawn inject`" claim only holds if FastAPI (`meridian app`) is the sole long-running owner of `SpawnManager`, which would make Phase 1 not independently testable.

## Control Socket

Each bidirectional spawn gets a Unix domain socket at `.meridian/spawns/<spawn_id>/control.sock`. This enables cross-process injection — `meridian spawn inject` from another terminal connects to this socket.

```python
# src/meridian/lib/streaming/control_socket.py

class ControlSocketServer:
    """Unix domain socket listener for one spawn's control channel.

    Protocol: each connection sends one JSON message and receives one JSON response.

    Request:  {"type": "user_message", "text": "..."} | {"type": "interrupt"} | {"type": "cancel"}
    Response: {"ok": true} | {"ok": false, "error": "reason"}
    """

    def __init__(self, spawn_id: SpawnId, socket_path: Path, manager: SpawnManager):
        self._spawn_id = spawn_id
        self._socket_path = socket_path
        self._manager = manager
        self._server: asyncio.AbstractServer | None = None

    async def start(self) -> None:
        """Start listening on the Unix domain socket."""
        self._socket_path.parent.mkdir(parents=True, exist_ok=True)
        self._socket_path.unlink(missing_ok=True)
        self._server = await asyncio.start_unix_server(
            self._handle_client,
            path=str(self._socket_path),
        )

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Handle one control socket connection."""
        try:
            data = await asyncio.wait_for(reader.readline(), timeout=5.0)
            msg = json.loads(data)
            msg_type = msg.get("type")

            if msg_type == "user_message":
                result = await self._manager.inject(self._spawn_id, msg["text"])
            elif msg_type == "interrupt":
                result = await self._manager.interrupt(self._spawn_id)
            elif msg_type == "cancel":
                result = await self._manager.cancel(self._spawn_id)
            else:
                result = InjectResult(success=False, error=f"unknown message type: {msg_type}")

            response = {"ok": result.success}
            if not result.success:
                response["error"] = result.error
            writer.write(json.dumps(response).encode() + b"\n")
            await writer.drain()
        except Exception as e:
            writer.write(json.dumps({"ok": False, "error": str(e)}).encode() + b"\n")
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def stop(self) -> None:
        """Stop the socket server and clean up the socket file."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
        self._socket_path.unlink(missing_ok=True)
```

### Socket path convention

```
.meridian/spawns/<spawn_id>/control.sock
```

This is within the existing per-spawn artifact directory, so cleanup happens naturally when the spawn's artifacts are cleaned up. The socket file is removed when the control server stops.

## `meridian spawn inject` CLI Command

```python
# src/meridian/cli/spawn_inject.py

async def inject_message(spawn_id: str, message: str) -> None:
    """Send a user message to a running bidirectional spawn.

    Connects to the spawn's control socket, sends the message, and
    prints the result.
    """
    socket_path = resolve_spawn_log_dir(repo_root, SpawnId(spawn_id)) / "control.sock"

    if not socket_path.exists():
        # Spawn exists but no control socket → spawn not running or already finished
        print(f"Error: spawn {spawn_id} has no control socket (spawn not running or already finished)")
        sys.exit(1)

    reader, writer = await asyncio.open_unix_connection(str(socket_path))
    try:
        request = json.dumps({"type": "user_message", "text": message}) + "\n"
        writer.write(request.encode())
        await writer.drain()

        response_data = await asyncio.wait_for(reader.readline(), timeout=10.0)
        response = json.loads(response_data)

        if response.get("ok"):
            print(f"Message delivered to spawn {spawn_id}")
        else:
            print(f"Error: {response.get('error', 'unknown error')}")
            sys.exit(1)
    finally:
        writer.close()
        await writer.wait_closed()
```

**CLI interface**:
```bash
meridian spawn inject <spawn_id> "reconsider the approach for auth middleware"
meridian spawn inject <spawn_id> --interrupt
meridian spawn inject <spawn_id> --cancel
```

## Integration With Existing Spawn Infrastructure

### Spawn state recording — universal, not a mode

Per D41, bidirectionality is universal — not a flag, not a mode, not a new invocation shape. There is no `kind="bidirectional"` or `launch_mode="bidirectional"` that distinguishes "special" spawns. Every spawn launched after Phase 1 gets a `HarnessConnection` and a control socket. The existing `kind` and `launch_mode` values are unchanged.

```python
# In SpawnManager.start_spawn():
spawn_id = spawn_store.start_spawn(
    state_root,
    chat_id=chat_id,
    model=config.model,
    agent=config.agent,
    harness=str(config.harness_id),
    kind="spawn",                    # Same as existing — NOT "bidirectional"
    prompt=config.prompt,
    execution_cwd=str(config.repo_root),
    launch_mode="background",        # Same as existing
    work_id=work_id,
    status="running",
)
```

Fire-and-forget callers that never call `send_*()` or connect to the control socket get exactly the same behavior as before. The presence of `control.sock` in the artifact directory indicates the spawn accepts injection — callers discover this by checking `control.sock` existence, not by reading a `kind` field.

### Artifact storage

All spawns write to the same artifact directory:
- `.meridian/spawns/<spawn_id>/output.jsonl` — raw harness events, durably drained (for replay/debugging)
- `.meridian/spawns/<spawn_id>/stderr.log` — harness stderr
- `.meridian/spawns/<spawn_id>/heartbeat` — liveness signal
- `.meridian/spawns/<spawn_id>/control.sock` — **new**: control socket (presence = injectable)
- `.meridian/spawns/<spawn_id>/inbound.jsonl` — **new**: durable record of all inject/interrupt/cancel actions
- `.meridian/spawns/<spawn_id>/connection.json` — **new**: connection metadata (harness, capabilities, transport details)

### Heartbeat

The `SpawnManager` maintains the heartbeat file for each active connection, using the existing `heartbeat_scope` from `launch/heartbeat.py`. Orphan detection (`meridian doctor`) works the same way.

## Refactoring Scope Against Existing Code

### What stays unchanged

| File | Why |
|---|---|
| `harness/claude.py` | `ClaudeAdapter.build_command()` and extraction logic unchanged. `supports_bidirectional=True` added to capabilities. |
| `harness/codex.py` | Same — command building, extraction stay. |
| `harness/opencode.py` | Same. |
| `harness/registry.py` | Unchanged — still resolves `SubprocessHarness` instances. |
| `launch/process.py` | Unchanged — primary interactive launch with PTY. |
| `launch/stream_capture.py` | Unchanged — stdout/stderr capture stays for artifact files. |

### What's extended

**`harness/adapter.py`** — `HarnessCapabilities` gains one new boolean:

```python
class HarnessCapabilities(BaseModel):
    # ... existing fields ...
    supports_stream_events: bool = True
    supports_stdin_prompt: bool = False
    # ... etc ...

    # NEW: indicates a HarnessConnection implementation exists
    supports_bidirectional: bool = False
```

Each existing adapter (`ClaudeAdapter`, `CodexAdapter`, `OpenCodeAdapter`) gets `supports_bidirectional=True` added to their `capabilities` property. **No `mid_turn_injection` enum on this side** — that semantic detail lives exclusively in `ConnectionCapabilities` on `HarnessConnection` (see harness-abstraction.md, Capability model boundary).

**`launch/runner.py`** — The async subprocess runner is extended to wire up the bidirectional layer for harnesses where `supports_bidirectional=True`. After launching the subprocess, it:
1. Creates a `HarnessConnection` from the connection registry
2. Calls `connection.start()` to establish the bidirectional transport
3. Starts the durable drain task (events → `output.jsonl`)
4. Starts the control socket server
5. Registers the connection with the global `SpawnManager`

This is the integration point that makes universality concrete. The fire-and-forget subprocess lifecycle (launch, capture, heartbeat, finalize) continues to own the process. The bidirectional layer runs alongside it — same subprocess, additional transport. If `supports_bidirectional=False` for a harness, none of this fires and the spawn works exactly as before.

**`state/spawn_store.py`** — no schema changes. Spawns use existing `kind` and `launch_mode` values. The bidirectional layer is additive infrastructure, not a new spawn category.

### What's new

| New file | Purpose |
|---|---|
| `harness/connections/__init__.py` | Connection registry |
| `harness/connections/base.py` | `HarnessConnection` ABC, `HarnessEvent`, `ConnectionConfig`, `ConnectionCapabilities`, `ConnectionState` |
| `harness/connections/claude_ws.py` | `ClaudeConnection` — WS server adapter |
| `harness/connections/codex_ws.py` | `CodexConnection` — WS client adapter |
| `harness/connections/opencode_http.py` | `OpenCodeConnection` — HTTP adapter |
| `streaming/__init__.py` | Package init |
| `streaming/spawn_manager.py` | `SpawnManager` with durable drain + fan-out + inbound recording |
| `streaming/control_socket.py` | `ControlSocketServer` |
| `streaming/types.py` | `ControlMessage`, `InjectResult`, `ConnectionNotReady` |
| `cli/spawn_inject.py` | `meridian spawn inject` command |
| `cli/streaming_serve.py` | `meridian streaming serve` headless runner |

### What's NOT touched

The `launch/process.py` (PTY interactive mode) and `launch/stream_capture.py` (stdout/stderr capture) are not modified. The bidirectional transport runs alongside the existing capture — same subprocess, separate communication channel (WebSocket for Claude/Codex, HTTP for OpenCode).

The existing `SubprocessHarness` adapters' command-building, report extraction, and session management logic stays as-is. Only the `capabilities` property gains the `supports_bidirectional` flag.

## Phase 1 Gate: Smoke Tests

Each harness gets a smoke test guide (markdown) verifying the end-to-end bidirectional path. Format follows the `smoke-test` skill methodology.

### Claude Code smoke test

```
1. Start a bidirectional Claude spawn via headless runner:
   meridian streaming serve --harness claude -p "List the files in the current directory"
   → Prints spawn_id, e.g. p200

2. In another terminal, verify the spawn is running:
   meridian spawn list  →  shows spawn p200 with status="running"

3. Verify events are draining to output.jsonl:
   tail -f .meridian/spawns/p200/output.jsonl
   → Should see harness events appearing in real time

4. Inject a mid-turn message:
   meridian spawn inject p200 "What files have you read so far?"

5. Verify in inbound.jsonl that the inject was recorded:
   cat .meridian/spawns/p200/inbound.jsonl
   → {"action": "user_message", "data": {"text": "What files..."}, ...}

6. Verify in output.jsonl that:
   - The user message was delivered (a "user" type event appears)
   - Claude responded to the injected message (an "assistant" type event follows)

7. Inject an interrupt:
   meridian spawn inject p200 --interrupt

8. Verify the spawn handled the interrupt gracefully.
```

### Codex smoke test

Same structure, but verifying:
- `turn/steer` delivery (mid-turn) or `turn/start` (new turn)
- Codex responded to the injected message
- `turn/interrupt` works

### OpenCode smoke test

Same structure, but verifying:
- HTTP POST delivery to the session endpoint
- OpenCode processed the message and produced a response

## Implementation Notes

### Port allocation

Both Claude and Codex need a port for their WebSocket (Claude: our server port; Codex: Codex's server port). Use port 0 to let the OS auto-assign, then read the actual port from the socket info.

For Claude: `websockets.serve(handler, "127.0.0.1", 0)` → read `server.sockets[0].getsockname()[1]`
For Codex: let Codex choose its own port via `--listen ws://127.0.0.1:0`, then read the port from Codex's startup output.

### Subprocess management

The bidirectional path uses `asyncio.create_subprocess_exec()` (same as `runner.py`) but does NOT capture stdout/stderr via pipes in the same way. Instead:
- Claude: communication is over WS, not stdio. Stdout/stderr are captured to artifact files for debugging.
- Codex: communication is over WS (JSON-RPC). Same artifact capture pattern.
- OpenCode: communication is over HTTP. Same artifact capture pattern.

The subprocess is still managed with SIGTERM → timeout → SIGKILL shutdown, reusing the patterns from `launch/timeout.py`.

### Error propagation

If the harness subprocess dies unexpectedly:
1. The transport (WS or HTTP) raises an exception
2. The `HarnessConnection.events()` iterator yields a final error event and completes
3. The `SpawnManager` marks the spawn as failed in `spawn_store`
4. The control socket server is shut down
5. Phase 2 (if running) sends a `RUN_ERROR` AG-UI event to the connected client

### Graceful shutdown

When `SpawnManager.shutdown()` is called (process exit):
1. Send `cancel` to each active connection
2. Wait for each harness subprocess to exit (with timeout)
3. Close all control sockets
4. Finalize spawn states in `spawn_store`
