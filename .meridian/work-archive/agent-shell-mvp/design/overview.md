# Agent Shell MVP — Design Overview

This document is the entry point for the 3-phase agent shell design. It describes the system topology at runtime, how the three phases compose, and where each piece lives in the codebase.

## System Topology

At runtime, `meridian app` is a single Python process with three layers:

```
┌─────────────────────────────────────────────────────────────────┐
│  React UI (Phase 3)                                             │
│  Browser tab at http://localhost:<port>                          │
│  Renders AG-UI events, sends user_message/interrupt/cancel      │
└──────────────────────────┬──────────────────────────────────────┘
                           │ WebSocket (JSON frames)
┌──────────────────────────▼──────────────────────────────────────┐
│  FastAPI Server (Phase 2)                                       │
│  WS endpoint: /ws/spawn/{spawn_id}                              │
│  Translates harness wire → AG-UI events (outbound)              │
│  Routes user_message/interrupt/cancel → control layer (inbound) │
│  Serves static React build at /                                 │
├─────────────────────────────────────────────────────────────────┤
│  Bidirectional Streaming Layer (Phase 1)                        │
│  HarnessConnection per spawn — asyncio tasks                    │
│  SpawnManager: tracks active connections, routes inject msgs    │
│  Per-spawn control socket for cross-process `spawn inject`      │
├─────────────────────────────────────────────────────────────────┤
│  Harness Subprocesses                                           │
│  Claude Code (WS client → our WS server)                        │
│  Codex app-server (WS server ← our WS client)                  │
│  OpenCode (HTTP session API)                                    │
└─────────────────────────────────────────────────────────────────┘
```

**Key property**: Phase 1 is useful without Phase 2 or 3. The `meridian spawn inject` CLI command validates the bidirectional layer end-to-end from the command line. Phase 2 wraps Phase 1's control surface in a WebSocket API. Phase 3 wraps Phase 2 in a React UI. Each layer has its own gate and can be tested independently.

## Data Flow

### Outbound (harness → user)

1. Harness subprocess emits wire-format events (NDJSON for Claude, JSON-RPC notifications for Codex, HTTP/NDJSON for OpenCode)
2. Phase 1 adapter receives raw events via its transport (WebSocket or HTTP)
3. Phase 1 yields `HarnessEvent` objects on an async iterator
4. Phase 2 mapper transforms `HarnessEvent` → `ag_ui.core` event (e.g., `TextMessageContentEvent`)
5. Phase 2 serializes: `event.model_dump_json(by_alias=True, exclude_none=True)`
6. Phase 2 sends JSON string as a WebSocket text frame to the connected client
7. Phase 3 reducer dispatches the event into the activity stream state

### Inbound (user → harness)

1. Phase 3 UI sends a JSON frame: `{"type": "user_message", "text": "..."}`
2. Phase 2 WebSocket handler parses the frame, calls `spawn_manager.inject(spawn_id, message)`
3. Phase 1 `SpawnManager` looks up the `HarnessConnection` for the spawn
4. Phase 1 calls `connection.send_user_message(text)` on the adapter
5. Adapter translates to harness wire format and delivers:
   - Claude: sends `{"type": "user", "content": "..."}` JSON over WebSocket
   - Codex: sends `turn/start` or `turn/steer` JSON-RPC request
   - OpenCode: POSTs to session HTTP endpoint

### Cross-process inject (CLI → harness)

1. `meridian spawn inject <spawn_id> "message"` CLI command
2. Connects to Unix domain socket at `.meridian/spawns/<spawn_id>/control.sock`
3. Sends JSON control message: `{"type": "user_message", "text": "..."}`
4. Spawn manager's socket listener receives the message, routes to adapter
5. Same adapter path as inbound WebSocket

## Phase Dependencies

```
Phase 1 (bidirectional streaming)
  └── Phase 2 (FastAPI + AG-UI mapping)
        └── Phase 3 (React UI)
```

Phase 1 has no dependency on Phase 2 or 3. Phase 2 depends on Phase 1's `SpawnManager` and `HarnessConnection` interfaces. Phase 3 depends on Phase 2's WebSocket endpoint contract.

## Design Documents

| Document | Covers |
|---|---|
| [overview.md](overview.md) | This file — system topology, data flow, phase relationships |
| [harness-abstraction.md](harness-abstraction.md) | SOLID interface design, `HarnessConnection` protocol, per-harness topology hiding, capability introspection |
| [phase-1-streaming.md](phase-1-streaming.md) | Phase 1 — bidirectional adapters, `SpawnManager`, control socket, `meridian spawn inject`, refactoring scope against existing code |
| [phase-2-fastapi-agui.md](phase-2-fastapi-agui.md) | Phase 2 — FastAPI WebSocket endpoint, AG-UI event mapping per harness, inbound frame handling |
| [phase-3-react-ui.md](phase-3-react-ui.md) | Phase 3 — frontend-v2 adaptation, component tree, activity stream, capability-aware affordances |
| [edge-cases.md](edge-cases.md) | Failure modes, boundary conditions, error propagation across layers |

## Repository Layout

New code added to `meridian-channel`:

```
src/meridian/
├── lib/
│   ├── harness/
│   │   ├── adapter.py          # Extended with BidirectionalHarness protocol
│   │   ├── connections/        # NEW — per-harness connection implementations
│   │   │   ├── __init__.py
│   │   │   ├── base.py         # HarnessConnection ABC + HarnessEvent types
│   │   │   ├── claude_ws.py    # Claude --sdk-url WS server adapter
│   │   │   ├── codex_ws.py     # Codex app-server WS client adapter
│   │   │   └── opencode_http.py # OpenCode HTTP session adapter
│   │   ├── claude.py           # Unchanged — fire-and-forget stays
│   │   ├── codex.py            # Unchanged
│   │   └── opencode.py         # Unchanged
│   ├── streaming/              # NEW — Phase 1 control layer
│   │   ├── __init__.py
│   │   ├── spawn_manager.py    # Active connection registry + inject routing
│   │   ├── control_socket.py   # Unix domain socket listener per spawn
│   │   └── types.py            # ControlMessage, InjectResult types
│   └── app/                    # NEW — Phase 2 server
│       ├── __init__.py
│       ├── server.py           # FastAPI app + static file serving
│       ├── ws_endpoint.py      # WebSocket handler
│       └── agui_mapping/       # Per-harness → AG-UI translation
│           ├── __init__.py
│           ├── base.py         # AGUIMapper protocol
│           ├── claude.py       # Claude NDJSON → AG-UI
│           ├── codex.py        # Codex JSON-RPC → AG-UI
│           └── opencode.py     # OpenCode wire → AG-UI
├── cli/
│   ├── app.py                  # NEW — `meridian app` CLI command
│   ├── spawn_inject.py         # NEW — `meridian spawn inject` CLI command
│   └── streaming_serve.py      # NEW — `meridian streaming serve` headless runner
frontend/                       # NEW — Phase 3 React app (copied from frontend-v2)
├── src/
├── package.json
└── vite.config.ts
pyproject.toml                  # Updated: new deps (fastapi, uvicorn, websockets, ag-ui-protocol)
```

### What Changes vs. What's New

**Existing code that stays mostly unchanged:**
- `src/meridian/lib/harness/claude.py`, `codex.py`, `opencode.py` — fire-and-forget `SubprocessHarness` adapters. Command-building, report extraction, and session management logic is unchanged. `supports_bidirectional=True` added to capabilities.
- `src/meridian/lib/launch/runner.py`, `process.py`, `stream_capture.py` — existing subprocess launch and capture stay as internal implementation.
- `src/meridian/lib/harness/adapter.py` — `SubprocessHarness` protocol stays. `HarnessCapabilities` gains `supports_bidirectional: bool`.

**Integration point (how universality works):** The existing spawn launch path in `runner.py` is extended to, after launching the subprocess, also establish a `HarnessConnection` and start the control socket when the harness's `supports_bidirectional` capability is True. This is the bridge that makes every spawn injectable — the fire-and-forget launch path still owns the subprocess lifecycle, but it additionally sets up the bidirectional transport alongside. The `HarnessConnection` reads events from its own transport (WS/HTTP), while `stream_capture.py` continues to capture stdout/stderr to artifact files as before. Both run concurrently for the duration of the spawn.

**New code:**
- `src/meridian/lib/harness/connections/` — per-harness bidirectional connection implementations
- `src/meridian/lib/streaming/` — spawn manager (with durable drain + inbound recording) and control socket
- `src/meridian/lib/app/` — FastAPI server and AG-UI mapping
- `src/meridian/cli/app.py` — `meridian app` entry point
- `src/meridian/cli/spawn_inject.py` — `meridian spawn inject` entry point
- `src/meridian/cli/streaming_serve.py` — `meridian streaming serve` headless runner
- `frontend/` — React UI adapted from frontend-v2

### Dependencies Added

```toml
# pyproject.toml additions
[project.dependencies]
fastapi = ">=0.115"
uvicorn = {version = ">=0.34", extras = ["standard"]}
websockets = ">=14.0"
ag-ui-protocol = ">=0.1"

[project.optional-dependencies]
app = ["fastapi", "uvicorn[standard]", "websockets", "ag-ui-protocol"]
```

The `app` optional dependency group keeps the base `meridian` install lightweight. `meridian app` checks for the group and gives a clear error if missing.

## What `meridian app` Does

```bash
meridian app                    # Start server, open browser
meridian app --port 8420        # Custom port
meridian app --no-browser       # Start server only
```

On launch:
1. Creates a FastAPI application with the WebSocket endpoint and static file serving
2. Starts the `SpawnManager` (Phase 1 control layer)
3. Starts uvicorn on `localhost:<port>`
4. Opens the default browser to `http://localhost:<port>`

The user interacts with spawns through the React UI. The UI can:
- Start a new spawn (selecting harness and agent profile)
- View the real-time activity stream of a running spawn
- Send messages mid-turn (routed through Phase 1's inject mechanism)
- Interrupt or cancel a running spawn

## Relationship to Existing `meridian spawn`

After Phase 1, **every spawn gains input-channel writability** — not a flag, not a mode, not a new invocation shape. The existing `meridian spawn` command continues to work exactly as it does today. Fire-and-forget callers that never call `send_*()` or connect to the control socket get exactly the same behavior as before. The bidirectional capability is universal and always available.

- `meridian spawn -a agent -p "task"` → works as before; additionally has a control socket for injection if desired
- `meridian spawn inject <spawn_id> "message"` → **new**, sends a message to a running spawn via Phase 1's control layer
- `meridian streaming serve` → **new**, headless Phase 1 runner for testing without FastAPI
- `meridian app` → **new**, starts the full web UI

All spawns — whether started via `meridian app`, `meridian streaming serve`, or the existing `meridian spawn` — are visible to `meridian spawn list`, `meridian spawn show`, and `meridian spawn log`. They write to the same `.meridian/` state. The bidirectional layer adds the control socket, inbound action log, and connection metadata; the rest of the spawn lifecycle (state tracking, artifact storage, session recording) uses the existing infrastructure.
