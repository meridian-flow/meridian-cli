# Phase 3 — React UI (`meridian app`)

Phase 3 adapts `frontend-v2` from `meridian-collab/` into a standalone React application that consumes the Phase 2 WebSocket endpoint. Primary validation is dogfooding — a developer using `meridian app` to build meridian itself.

## What Stays, What's Cut, What's Extended

### From frontend-v2 — KEEP

| Component/Module | Why |
|---|---|
| `features/activity-stream/` | Core value — renders AG-UI events as a visual timeline. Already written against the event shapes we emit. |
| `features/activity-stream/streaming/reducer.ts` | The event reducer. Works with our AG-UI event stream as-is (D48 ensures thinking event compatibility). |
| `features/activity-stream/streaming/events.ts` | StreamEvent type definitions. Match our outbound AG-UI events. |
| `features/threads/components/` | Thread view components — essential for the conversation display. |
| `features/threads/composer/` | Message input component — the "send" area where users type messages. |
| `features/activity-stream/items/` | Per-tool display components (BashDetail, EditDetail, SearchDetail, etc.). |
| `components/ui/` | UI atom library (buttons, inputs, cards, etc.). |
| `components/theme-provider.tsx` | Theme setup. |

### From frontend-v2 — CUT

| Component/Module | Why |
|---|---|
| `editor/` | CM6 + Yjs collaborative editor. Not needed for MVP dogfooding. If the agent drafts document content, it's displayed as markdown in the activity stream, not in a collaborative editor. |
| `features/docs/` | Document management UI. Out of scope. |
| `lib/ws/protocol.ts` | The Go backend's multi-lane envelope protocol (control/notify/stream/error with subscriptions). Our Phase 2 endpoint is simpler — direct AG-UI JSON frames on a bare WebSocket. Replace with a thin client. |
| `lib/ws/ws-client.ts` | Go backend WS client with auth, subscriptions, reconnect. Replace with a simpler client. |
| `lib/ws/doc-stream-client.ts` | Document streaming. Cut with editor. |
| `features/threads/streaming/streaming-channel-client.ts` | Coupled to the Go backend's subscription-based stream protocol. Replace. |

### From frontend-v2 — EXTEND

| Component/Module | Change |
|---|---|
| `features/threads/streaming/use-thread-streaming.ts` | Rewrite to consume our bare WebSocket (direct AG-UI frames, no envelope). |
| `features/threads/composer/` | Add capability-aware send button (see below). |
| `features/threads/transport-types.ts` | Simplify — remove `BackendTurn` / `BackendTurnBlock` REST types; the MVP has no REST paginated history. |
| Activity stream types | Add `capabilities` event handling for the CUSTOM capabilities event. |

## WebSocket Client — Two-Layer Architecture

Replace the Go backend's multi-lane WS client with a layered architecture: generic transport + spawn-specific channel. The generic layer is designed to support future channels beyond spawns (projects, collaboration, cloud service).

```typescript
// src/lib/ws/ws-client.ts — Generic transport (no domain knowledge)

export type WsState = "connecting" | "connected" | "disconnected"

export interface WsClient {
  readonly state: WsState
  readonly url: string

  connect(url: string): void
  disconnect(): void
  send(data: Record<string, unknown>): void

  onMessage(handler: (data: unknown) => void): () => void
  onStateChange(handler: (state: WsState) => void): () => void
}
```

```typescript
// src/lib/ws/spawn-channel.ts — Spawn-specific layer on top of WsClient

export interface SpawnChannel {
  readonly spawnId: string
  readonly client: WsClient

  connect(spawnId: string): void
  disconnect(): void

  sendUserMessage(text: string): void
  sendInterrupt(): void
  sendCancel(): void

  onEvent(handler: (event: StreamEvent) => void): () => void
}
```

`WsClient` handles connection lifecycle, JSON frame send/receive, and state tracking. `SpawnChannel` constructs the spawn URL, parses AG-UI events, and provides typed send methods. Future channels (e.g. project management, collaboration) create their own channel type on top of the same `WsClient`.

No reconnect logic for MVP (per requirements.md — "manual refresh on disconnect is acceptable").

## Capability-Aware Affordances

The Phase 2 server sends a `CUSTOM` capabilities event immediately after `RUN_STARTED`. The UI uses this to render the right send-button behavior:

```typescript
type HarnessCapabilities = {
  midTurnInjection: "queue" | "interrupt_restart" | "http_post"
  supportsSteer: boolean
  supportsInterrupt: boolean
  harnessId: string
}
```

### UI behavior per harness

| Capability | UI affordance |
|---|---|
| `queue` (Claude) | Send button always active. Tooltip: "Message queued for next turn." Input grayed slightly during active generation to signal queuing. |
| `interrupt_restart` (Codex) | Send button active. Warning indicator during active generation: "Sending will steer the current turn." Optional confirm dialog for destructive-looking steers. |
| `http_post` (OpenCode) | Send button always active. Normal send behavior — cleanest UX of the three. |

The interrupt and cancel buttons are always visible during active generation, regardless of harness.

## Component Tree

```
App
├── SpawnSelector              # Choose harness + agent profile, start new spawn
│   ├── HarnessDropdown        # claude / codex / opencode
│   ├── AgentProfileSelector   # List from .agents/ directory
│   └── StartButton
├── SpawnView                  # Active spawn display
│   ├── SpawnHeader            # Spawn ID, harness, model, status
│   ├── ThreadView             # (from frontend-v2)
│   │   ├── ActivityBlock      # (from frontend-v2, per turn)
│   │   │   ├── ContentItem    # Text blocks (markdown rendered)
│   │   │   ├── ThinkingItem   # Thinking blocks (collapsible)
│   │   │   └── ToolItem       # Tool calls (BashDetail, EditDetail, etc.)
│   │   └── StreamingIndicator # "Agent is working..."
│   ├── Composer               # (adapted from frontend-v2)
│   │   ├── TextInput          # User message input
│   │   ├── SendButton         # Capability-aware (see above)
│   │   ├── InterruptButton    # Stop current turn
│   │   └── CancelButton       # Cancel entire spawn
│   └── CapabilityBadge        # Shows harness + mid-turn semantics
└── StatusBar                  # Connection state, spawn count
```

## State Management

Simple React state with `useReducer` — no external state library needed for MVP.

```typescript
// Thread state: powered by the existing activity stream reducer
const [streamState, dispatch] = useReducer(reduceStreamEvent, createInitialState(spawnId))

// Connection state
const [wsState, setWsState] = useState<WsState>("disconnected")

// Capabilities (from CUSTOM event)
const [capabilities, setCapabilities] = useState<HarnessCapabilities | null>(null)

// Effect: connect SpawnChannel and dispatch events
useEffect(() => {
  const channel = createSpawnChannel()
  channel.connect(spawnId)

  const unsub = channel.onEvent((event) => {
    if (event.type === "CUSTOM" && event.name === "capabilities") {
      setCapabilities(event.value as HarnessCapabilities)
    } else {
      dispatch(event)
    }
  })

  return () => { unsub(); channel.disconnect() }
}, [spawnId])
```

## Interactive Tool Protocol

Domain-specific tools (e.g., PyVista point picking for biomedical) are NOT UI components in the shell. They are standalone Python processes that the agent calls as tools:

1. Agent calls `pick_points_on_mesh(file="scan.vtp")` via its tool-use mechanism
2. The tool opens a standalone PyVista window (X11/Wayland, separate from the browser)
3. User interacts with the PyVista window (rotate, zoom, click landmarks)
4. Window closes, tool returns coordinates as JSON
5. Agent continues with the returned data

The shell renders this as a normal tool call in the activity stream:
- `TOOL_CALL_START` with `toolCallName: "pick_points_on_mesh"`
- `TOOL_CALL_ARGS` with the file path
- (Spinner while waiting for user interaction in the PyVista window)
- `TOOL_CALL_RESULT` with the coordinates JSON

No special shell UI is needed for interactive tools — they are self-contained standalone applications. The shell just shows the tool call lifecycle like any other tool.

## Spawn Selector

The spawn selector lets the user start a new spawn. It needs:

1. **Harness selection** — dropdown with available harnesses. Initially shows harnesses detected on the system (`which claude`, `which codex`, `which opencode`).

2. **Agent profile selection** — reads from `.agents/profiles/` to list available agent profiles. Each profile shows name and description.

3. **Initial prompt** — text area for the first message.

4. **Start** — calls `POST /api/spawn` with `{harness, agent, prompt}`, then connects the WebSocket to the new spawn.

## Build and Serving

The React app is built with Vite and served as static files by the FastAPI server:

```bash
# Development (hot reload)
cd frontend && pnpm dev     # Vite dev server on :5173, proxied to FastAPI

# Production (bundled)
cd frontend && pnpm build   # Outputs to frontend/dist/
meridian app                # FastAPI serves frontend/dist/ + WS endpoint
```

The `meridian app` command checks for `frontend/dist/` and gives a clear error if the frontend hasn't been built yet, with instructions to run `pnpm build`.

## Phase 3 Gate

A single customer can:
1. Run `meridian app`
2. Browser opens to `http://localhost:<port>`
3. Select Claude Code harness and an agent profile
4. Start a new spawn with an initial prompt
5. See the activity stream rendering in real time (text, tools, thinking)
6. Send a mid-turn message and see it delivered to the agent
7. See the agent's response to the injected message
8. Interrupt or cancel the spawn

**First release ships Claude-Code-only** even though Phase 1 and Phase 2 proved all three harnesses. Codex and OpenCode in the UI are incremental work after the first Claude Code demo validates.

## What's NOT in Phase 3 MVP

- Multi-spawn visibility (tabs/panels for multiple spawns)
- Session persistence across process restarts
- Reconnect on WebSocket disconnect (manual refresh)
- Permission gating (approve-before-tool-call UX)
- Collaborative editor (CM6+Yjs)
- Document management
- REST-based paginated history (no history — current session only)
