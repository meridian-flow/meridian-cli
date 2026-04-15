# Stream Topology Findings

## Bottom Line

The current active spawn stack is bidirectional for all three bundled harnesses:

- `claude` uses subprocess stdio plus SIGINT for cancel/interrupt.
- `codex` uses a local WebSocket to the app-server subprocess.
- `opencode` uses HTTP POST for control plus SSE/HTTP GET for events.

There is still a legacy one-way-ish fallback executor in the tree, but it is not selected by the current harness bundle. So the code has not fully deleted one-way subprocess streaming, but the active `claude` / `codex` / `opencode` paths have converged on bidirectional transports.

## 1. CLI Spawns

### Process shape

- `meridian spawn ...` resolves into the spawn execution layer and, for bidirectional harnesses, enters `execute_with_streaming` rather than the legacy finalization-only path. See [`src/meridian/lib/ops/spawn/execute.py`](src/meridian/lib/ops/spawn/execute.py) lines 462-476 and 773-794.
- In foreground mode, the live processes are the Meridian CLI/runner process plus the harness child process.
- In background mode, Meridian first launches a separate worker process (`python -m meridian.lib.ops.spawn.execute ...`), and that worker then launches the harness child. See [`src/meridian/lib/ops/spawn/execute.py`](src/meridian/lib/ops/spawn/execute.py) lines 490-676.

### Directionality

- Outbound prompt/input goes from Meridian to the harness over the harness-specific transport.
- Inbound events go from the harness back to Meridian through `HarnessConnection.events()` and the `SpawnManager` drain loop.
- `meridian spawn inject` does not open a second harness stream. It opens a per-spawn Unix control socket and sends one JSON control request. See [`src/meridian/cli/spawn_inject.py`](src/meridian/cli/spawn_inject.py) lines 22-112 and [`src/meridian/lib/streaming/control_socket.py`](src/meridian/lib/streaming/control_socket.py) lines 18-139.

### Single stream or multiple?

- There are two planes at the Meridian layer:
  - the live harness transport;
  - the per-spawn control socket (`control.sock`) for inject/interrupt.
- The durable event log (`output.jsonl`) is not a transport; it is the persisted event record written by the drain loop. See [`src/meridian/lib/streaming/spawn_manager.py`](src/meridian/lib/streaming/spawn_manager.py) lines 250-327 and 637-700.

## 2. App Spawns

### Process shape

- `meridian app` starts a FastAPI/Uvicorn process that owns a long-lived `SpawnManager`. See [`src/meridian/cli/app_cmd.py`](src/meridian/cli/app_cmd.py) lines 9-45 and [`src/meridian/lib/app/server.py`](src/meridian/lib/app/server.py) lines 115-129 and 195-236.
- `POST /api/spawns` creates a live `HarnessConnection` and stores it in the in-memory manager for that app process. See [`src/meridian/lib/app/server.py`](src/meridian/lib/app/server.py) lines 268-365.

### Bidirectional or not?

- Yes. The app server keeps a persistent connection object and routes both outbound control and inbound events through it.
- The app server also exposes a live WebSocket subscriber path at `/api/spawns/{spawn_id}/ws`, which consumes the same manager fan-out queue. See [`src/meridian/lib/app/ws_endpoint.py`](src/meridian/lib/app/ws_endpoint.py) lines 61-110 and 158-235.

## 3. Per Harness Transport Shape

### Claude

- The Claude connection is a subprocess stdio transport: `claude -p --input-format stream-json --output-format stream-json`.
- Meridian writes user turns to stdin and reads typed JSON events from stdout.
- Cancel/interrupt is delivered by `SIGINT`.
- See [`src/meridian/lib/harness/connections/claude_ws.py`](src/meridian/lib/harness/connections/claude_ws.py) lines 59-69, 129-197, and 197-260.
- The bundled Claude harness advertises `supports_bidirectional=True` and `supports_stdin_prompt=True`. See [`src/meridian/lib/harness/claude.py`](src/meridian/lib/harness/claude.py) lines 240-250.

### Codex

- The Codex connection launches a local `codex app-server` subprocess, then connects to it over `ws://127.0.0.1:<port>`.
- Meridian sends JSON-RPC requests over that WebSocket and receives JSON-RPC notifications/responses back on the same WebSocket.
- See [`src/meridian/lib/harness/connections/codex_ws.py`](src/meridian/lib/harness/connections/codex_ws.py) lines 132-255 and 402-545.
- The bundled Codex harness advertises `supports_bidirectional=True` and `supports_stdin_prompt=True`. See [`src/meridian/lib/harness/codex.py`](src/meridian/lib/harness/codex.py) lines 317-327.

### OpenCode

- The OpenCode connection launches `opencode serve` as a subprocess.
- Outbound control uses HTTP POSTs to session/message/action endpoints.
- Inbound events use an SSE/HTTP event stream GET.
- So it is bidirectional, but not through a single duplex socket; it is an HTTP control plane plus an event-stream plane.
- See [`src/meridian/lib/harness/connections/opencode_http.py`](src/meridian/lib/harness/connections/opencode_http.py) lines 47-57, 147-236, and 338-567.
- The bundled OpenCode harness advertises `supports_bidirectional=True` and `supports_stdin_prompt=True`. See [`src/meridian/lib/harness/opencode.py`](src/meridian/lib/harness/opencode.py) lines 193-203.

## 4. Inject Path

- `meridian spawn inject p1234 --message "hi"` resolves the spawn directory, opens `spawns/p1234/control.sock`, writes one JSON request, and waits for one JSON response. See [`src/meridian/cli/spawn_inject.py`](src/meridian/cli/spawn_inject.py) lines 22-112.
- The request body is either:
  - `{"type":"user_message","text":"..."}` or
  - `{"type":"interrupt"}`
- The control socket server routes those requests to `SpawnManager.inject()` or `SpawnManager.interrupt()`. See [`src/meridian/lib/streaming/control_socket.py`](src/meridian/lib/streaming/control_socket.py) lines 62-129.
- `SpawnManager._record_inbound()` appends the action to `inbound.jsonl` before forwarding it to the harness connection, so `inbound.jsonl` is an audit log, not the transport itself. See [`src/meridian/lib/streaming/spawn_manager.py`](src/meridian/lib/streaming/spawn_manager.py) lines 387-509 and 683-685.

## 5. Cancel Path

- For CLI-owned spawns, `SignalCanceller` resolves the runner PID and sends `SIGTERM`. See [`src/meridian/lib/streaming/signal_canceller.py`](src/meridian/lib/streaming/signal_canceller.py) lines 79-113.
- For app-owned spawns in the same process, `SignalCanceller` calls `SpawnManager.stop_spawn()`, which in turn calls `send_cancel()` on the harness connection. See [`src/meridian/lib/streaming/signal_canceller.py`](src/meridian/lib/streaming/signal_canceller.py) lines 114-138 and [`src/meridian/lib/streaming/spawn_manager.py`](src/meridian/lib/streaming/spawn_manager.py) lines 525-582.
- For cross-process app cancel, `SignalCanceller` uses an `aiohttp.UnixConnector` to POST `http://localhost/api/spawns/{spawn_id}/cancel` over `app.sock`. See [`src/meridian/lib/streaming/signal_canceller.py`](src/meridian/lib/streaming/signal_canceller.py) lines 140-207.
- The FastAPI app cancel route delegates back into the same manager/canceller pair. See [`src/meridian/lib/app/server.py`](src/meridian/lib/app/server.py) lines 421-449.

## 6. Observability

- The live inbound event flow is:
  - harness connection yields `HarnessEvent`;
  - `SpawnManager._drain_loop()` writes the event envelope to `output.jsonl`;
  - `SpawnManager._fan_out_event()` pushes the event to any live subscriber queue.
- See [`src/meridian/lib/streaming/spawn_manager.py`](src/meridian/lib/streaming/spawn_manager.py) lines 250-327 and 647-700.
- Live subscribers exist for:
  - the app WebSocket endpoint;
  - the streaming runner path used by CLI/app live streaming.
- See [`src/meridian/lib/app/ws_endpoint.py`](src/meridian/lib/app/ws_endpoint.py) lines 61-110 and [`src/meridian/lib/launch/streaming_runner.py`](src/meridian/lib/launch/streaming_runner.py) lines 389-529 and 534-739.

## 7. One-Way Path Status

- The legacy one-way-ish subprocess executor still exists in `execute_with_finalization()` / `spawn_and_stream()`. It reads stdout/stderr and can feed an initial stdin prompt, but it does not expose the control socket / live mid-turn injection model used by the bidirectional stack. See [`src/meridian/lib/launch/runner.py`](src/meridian/lib/launch/runner.py) lines 216-431 and 434-760.
- That path is still referenced as the fallback for any harness whose capabilities report `supports_bidirectional=False`. See [`src/meridian/lib/ops/spawn/execute.py`](src/meridian/lib/ops/spawn/execute.py) lines 462-476 and 773-794.
- None of the current bundled harnesses do that. Claude, Codex, and OpenCode all declare `supports_bidirectional=True`. See [`src/meridian/lib/harness/claude.py`](src/meridian/lib/harness/claude.py) lines 240-250, [`src/meridian/lib/harness/codex.py`](src/meridian/lib/harness/codex.py) lines 317-327, and [`src/meridian/lib/harness/opencode.py`](src/meridian/lib/harness/opencode.py) lines 193-203.

## Conclusion

User-facing summary:

- `meridian spawn` is bidirectional for the active harnesses.
- Inject is a separate per-spawn control socket, not a second harness stream.
- Cancel is `SIGTERM` for CLI-owned spawns, local manager shutdown for in-process app spawns, and HTTP-to-app-sock for cross-process app cancellation.
- The old one-way executor is still present as fallback code, but it is not on the active path for Claude, Codex, or OpenCode today.
