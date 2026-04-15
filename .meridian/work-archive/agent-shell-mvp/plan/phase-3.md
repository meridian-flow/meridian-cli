# Phase 3 — React UI (`meridian app`)

Phase 3 adapts `frontend-v2` from `meridian-collab/` into a standalone React application that consumes the Phase 2 WebSocket endpoint. Ships Claude-Code-only for first release.

**Dependencies**: Phase 2 complete (FastAPI server + AG-UI WebSocket endpoint working).
**Gate**: A single customer can run `meridian app`, interact with a Claude Code spawn, see the activity stream, inject mid-turn messages, and get meaningful responses.

**D56 OVERRIDE**: All frontend `THINKING_*` references from frontend-v2 must be renamed to `REASONING_*` to match the standard AG-UI events the Phase 2 mappers emit.

## Sub-step 3A: React Scaffold, WebSocket Client, and Build Pipeline

**Scope**: Set up the React project, copy essential frontend-v2 building blocks, create the two-layer WS client (generic `WsClient` + `SpawnChannel` per D57), and verify the build pipeline works end-to-end (Vite build → FastAPI serves static files).

**Round**: 7 (after Phase 2 complete).

### Files to Create

- `frontend/package.json` — React + Vite + TypeScript project config:
  - Dependencies: react, react-dom, tailwindcss, lucide-react (icons), clsx
  - Dev dependencies: vite, @vitejs/plugin-react, typescript, @types/react
  - Scripts: `dev` (Vite dev server with proxy to FastAPI), `build` (production build to dist/)

- `frontend/vite.config.ts` — Vite config:
  - React plugin
  - Proxy `/ws` and `/api` to FastAPI backend during development
  - Output to `frontend/dist/`

- `frontend/tsconfig.json` — TypeScript config
- `frontend/tailwind.config.ts` — Tailwind config
- `frontend/index.html` — Entry HTML
- `frontend/src/main.tsx` — React entry point
- `frontend/src/App.tsx` — Top-level component shell (SpawnSelector + SpawnView + StatusBar)

- `frontend/src/lib/ws/ws-client.ts` — `WsClient` (generic, extensible beyond spawn):
  ```typescript
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
  - Generic WebSocket transport — handles connection lifecycle, JSON frame send/receive, state tracking
  - No domain knowledge of spawns, AG-UI, or any specific protocol
  - Designed so future channels (projects, collaboration, cloud service) use the same transport
  - No reconnect logic for MVP (manual refresh acceptable)

- `frontend/src/lib/ws/spawn-channel.ts` — `SpawnChannel` (spawn-specific layer on top of WsClient):
  ```typescript
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
  - Constructs spawn URL: `ws://localhost:<port>/ws/spawn/{spawnId}`
  - Parses incoming JSON frames as StreamEvent via WsClient.onMessage
  - Sends typed outbound frames (user_message, interrupt, cancel) via WsClient.send
  - First consumer of WsClient — not the last

- `frontend/src/lib/ws/types.ts` — StreamEvent type definitions (AG-UI event shapes in TypeScript):
  - `RunStartedEvent`, `RunFinishedEvent`, `RunErrorEvent`
  - `TextMessageStartEvent`, `TextMessageContentEvent`, `TextMessageEndEvent`
  - `ReasoningMessageStartEvent`, `ReasoningMessageContentEvent`, `ReasoningMessageEndEvent` (D56: NOT THINKING_*)
  - `ToolCallStartEvent`, `ToolCallArgsEvent`, `ToolCallEndEvent`, `ToolCallResultEvent`
  - `CustomEvent` (for capabilities)
  - `StreamEvent` (discriminated union of all above)

### Files to Copy from frontend-v2

Copy the following from `meridian-collab/frontend-v2/` (or equivalent source), adjusting imports:

- `components/ui/` — UI atom library (buttons, inputs, cards, etc.)
- `components/theme-provider.tsx` — Theme setup (dark/light mode)
- `lib/utils.ts` — Utility functions (cn(), etc.)

**Important**: Do NOT copy the following (they are being replaced):
- `lib/ws/protocol.ts` — Go backend envelope protocol (replaced by WsClient + SpawnChannel)
- `lib/ws/ws-client.ts` — Go backend WS client (replaced)
- `lib/ws/doc-stream-client.ts` — Document streaming (cut)
- `features/threads/streaming/streaming-channel-client.ts` — Go backend coupling (replaced)
- `editor/` — CM6 + Yjs collaborative editor (cut)
- `features/docs/` — Document management (cut)

### Files to Modify

- `src/meridian/lib/app/server.py` — Enable static file serving from `frontend/dist/` when directory exists

### Dependencies

- Requires: Phase 2 complete (WebSocket endpoint at `/ws/spawn/{spawn_id}`)
- The frontend-v2 source needs to be accessible for copying. If `meridian-collab/` is not available as a sibling repo, @coder should scaffold the UI components from scratch following the component descriptions in `design/phase-3-react-ui.md`.

### Verification Criteria

- [ ] `cd frontend && pnpm install && pnpm build` succeeds
- [ ] `frontend/dist/` contains built assets
- [ ] `meridian app --no-browser` serves the built frontend at `http://localhost:<port>/`
- [ ] WsClient connects to arbitrary WebSocket URLs (generic, no spawn knowledge)
- [ ] SpawnChannel connects to a running spawn WebSocket endpoint via WsClient
- [ ] StreamEvent types compile without errors
- [ ] `pnpm tsc --noEmit` passes (TypeScript type check)

### Edge Cases

- **Frontend-v2 unavailable** — scaffold from scratch rather than blocking. The design doc has enough component specs to build without copying.
- **Vite proxy** — dev server proxies `/ws` and `/api` to FastAPI; production serves from same origin.

---

## Sub-step 3B: Activity Stream and Thread View

**Scope**: Implement the core value — rendering AG-UI events as a visual activity stream. This includes the event reducer, per-block renderers (text, reasoning, tool calls), and the thread view layout.

**Round**: 8 (after 3A scaffold is working).

### Files to Create or Adapt

- `frontend/src/features/activity-stream/streaming/reducer.ts` — Event reducer:
  - State shape: `{ items: ActivityItem[], isStreaming: boolean, error: string | null, isCancelled: boolean }`
  - Handles: RUN_STARTED, RUN_FINISHED, RUN_ERROR, TEXT_MESSAGE_*, REASONING_* (D56), TOOL_CALL_*, STEP_*, CUSTOM
  - Accumulates text deltas into message items
  - Tracks active tool calls by ID
  - Sets isStreaming/error/isCancelled on run lifecycle events
  - **D56**: Handle `REASONING_START`, `REASONING_MESSAGE_CONTENT`, `REASONING_MESSAGE_END` — NOT `THINKING_*`

- `frontend/src/features/activity-stream/streaming/events.ts` — StreamEvent type definitions and guards:
  - Type guard functions: `isTextMessageContent()`, `isToolCallStart()`, `isReasoningStart()` (D56), etc.
  - Event type constants matching AG-UI protocol

- `frontend/src/features/activity-stream/items/` — Per-item renderers:
  - `TextItem.tsx` — Markdown-rendered text message blocks
  - `ReasoningItem.tsx` — Collapsible reasoning/thinking blocks (D56: named "reasoning" not "thinking")
  - `ToolCallItem.tsx` — Tool call display (name, args, status indicator)
  - `ToolResultItem.tsx` — Tool result display (output text, truncation for large outputs)
  - `ErrorItem.tsx` — Error display
  - `ActivityItem.tsx` — Union component that dispatches to the right renderer

- `frontend/src/features/threads/components/` — Thread view:
  - `ThreadView.tsx` — Main thread container: maps `items[]` from reducer state to `ActivityItem` components
  - `StreamingIndicator.tsx` — "Agent is working..." indicator when `isStreaming` is true
  - `ActivityBlock.tsx` — Groups items by turn (optional — can be flat list for MVP)

- `frontend/src/hooks/use-thread-streaming.ts` — Hook that wires SpawnChannel to the reducer:
  ```typescript
  function useThreadStreaming(spawnId: string) {
    const [state, dispatch] = useReducer(reducer, initialState)
    const [capabilities, setCapabilities] = useState<HarnessCapabilities | null>(null)
    
    useEffect(() => {
      const channel = createSpawnChannel()
      channel.connect(spawnId)
      const unsub = channel.onEvent((event) => {
        if (event.type === "CUSTOM" && event.name === "capabilities") {
          setCapabilities(event.value)
        } else {
          dispatch(event)
        }
      })
      return () => { unsub(); channel.disconnect() }
    }, [spawnId])
    
    return { state, capabilities, channel }
  }
  ```

### Dependencies

- Requires: Phase 3A (WsClient + SpawnChannel, StreamEvent types, UI atoms, build pipeline)
- Requires: Phase 2 emitting AG-UI events via WebSocket (for manual testing)

### Interface Contract

```typescript
// Reducer state shape
interface StreamState {
  items: ActivityItem[]
  isStreaming: boolean
  error: string | null
  isCancelled: boolean
}

// ActivityItem discriminated union
type ActivityItem =
  | { type: "text"; messageId: string; content: string }
  | { type: "reasoning"; messageId: string; content: string }
  | { type: "tool_call"; toolCallId: string; name: string; args: string; status: "running" | "complete" }
  | { type: "tool_result"; toolCallId: string; content: string }
  | { type: "error"; message: string }
```

### Verification Criteria

- [ ] `pnpm tsc --noEmit` passes
- [ ] `pnpm build` succeeds
- [ ] Reducer handles full AG-UI lifecycle: RUN_STARTED → text/tool/reasoning events → RUN_FINISHED
- [ ] Text messages render as markdown
- [ ] Reasoning blocks are collapsible (D56: labeled "Reasoning" not "Thinking")
- [ ] Tool calls show name, args, and running/complete status
- [ ] Tool results display output (with truncation for >100KB)
- [ ] Error events show error banner
- [ ] StreamingIndicator appears during active generation
- [ ] Activity stream auto-scrolls to latest content

### Edge Cases

- **EC7: Large tool output** — truncate display at 100KB, show "show full output" link
- **EC8: Malformed events** — reducer ignores unknown event types (no crash)
- **RUN_ERROR vs RUN_FINISHED** — error sets `error` field; RUN_FINISHED clears isStreaming
- **isCancelled** — user-initiated cancel suppresses error toast

---

## Sub-step 3C: Composer, Capability Affordances, and Spawn Selector

**Scope**: Implement the user interaction layer — message composer with capability-aware send button, interrupt/cancel buttons, spawn selector for starting new spawns, and the status bar. This completes the Phase 3 gate.

**Round**: 9 (after 3B activity stream works).

### Files to Create or Adapt

- `frontend/src/features/threads/composer/Composer.tsx` — Message input area:
  - `TextInput` — text area for user message
  - `SendButton` — capability-aware:
    - `queue` (Claude): always active, tooltip "Message queued for next turn", slight gray during generation
    - `interrupt_restart` (Codex): active with warning "Sending will steer the current turn"
    - `http_post` (OpenCode): always active, normal behavior
  - `InterruptButton` — visible during active generation, calls `channel.sendInterrupt()`
  - `CancelButton` — visible during active generation, calls `channel.sendCancel()`
  - Submit on Enter (Shift+Enter for newline)

- `frontend/src/features/spawn-selector/SpawnSelector.tsx` — Spawn selection and creation:
  - `HarnessDropdown` — claude / codex / opencode selection
  - `PromptInput` — text area for initial prompt
  - `StartButton` — calls `POST /api/spawn` with selected harness + prompt, then connects WS
  - Fetches available harnesses from `GET /api/spawn` or hardcoded list for MVP

- `frontend/src/features/spawn-selector/SpawnHeader.tsx` — Active spawn display:
  - Spawn ID, harness name, status
  - `CapabilityBadge` — shows harness + mid-turn injection semantics

- `frontend/src/components/StatusBar.tsx` — Bottom status bar:
  - WebSocket connection state (connecting/connected/disconnected)
  - Active spawn count

- `frontend/src/features/threads/composer/CapabilityBadge.tsx` — Shows current harness capability info:
  - Icon + text: "Queue" / "Steer" / "Direct" based on `midTurnInjection`
  - Tooltip with explanation

- Update `frontend/src/App.tsx` — Wire everything together:
  - State: selected spawn ID, SpawnChannel instance
  - Flow: SpawnSelector → start spawn → SpawnView (ThreadView + Composer + Header)
  - Conditional: show SpawnSelector when no active spawn, SpawnView when connected

### Dependencies

- Requires: Phase 3B (activity stream, reducer, ThreadView)
- Requires: Phase 2C (REST API for spawn creation)

### Interface Contract

```typescript
// Capabilities from CUSTOM event
type HarnessCapabilities = {
  midTurnInjection: "queue" | "interrupt_restart" | "http_post"
  supportsSteer: boolean
  supportsInterrupt: boolean
  harnessId: string
}

// Composer props
interface ComposerProps {
  channel: SpawnChannel
  capabilities: HarnessCapabilities | null
  isStreaming: boolean
  disabled: boolean  // true when no active spawn
}
```

### Verification Criteria

- [ ] `pnpm tsc --noEmit` passes
- [ ] `pnpm build` succeeds
- [ ] SpawnSelector allows selecting Claude harness and entering a prompt
- [ ] StartButton calls POST /api/spawn and connects WebSocket
- [ ] Activity stream renders in real time as harness works
- [ ] Send button delivers message to harness via WebSocket
- [ ] Injected message appears in harness output (verifiable in output.jsonl)
- [ ] Interrupt button stops current generation
- [ ] Cancel button terminates the spawn
- [ ] Capability badge shows correct mid-turn semantics
- [ ] Send button affordance matches harness capability
- [ ] Status bar shows connection state
- [ ] Error banner appears on RUN_ERROR
- [ ] UI is usable: scrolling, keyboard shortcuts, responsive layout

### Phase 3 Gate (End-to-End)

A single customer can:
1. Run `meridian app`
2. Browser opens to `http://localhost:<port>`
3. Select Claude Code harness
4. Start a new spawn with an initial prompt
5. See the activity stream rendering in real time (text, tools, reasoning)
6. Send a mid-turn message and see it delivered to the agent
7. See the agent's response to the injected message
8. Interrupt or cancel the spawn

### Edge Cases

- **EC2: Client disconnect** — spawn continues; user can refresh and reconnect (no automatic reconnect for MVP)
- **EC1: Harness dies** — RUN_ERROR event shows error banner, send button disabled
- **EC3: Message during tool execution** — message sent regardless; capability badge indicates behavior
- **Missing frontend build** — `meridian app` checks for `frontend/dist/` and gives clear error with build instructions
- **Empty prompt** — StartButton disabled when prompt is empty

### Browser Testing Criteria (for @browser-tester)

1. Page loads without console errors
2. SpawnSelector is visible and interactive
3. After starting a spawn, activity stream appears
4. Text messages render with proper formatting
5. Tool calls show names and arguments
6. Reasoning blocks are collapsible
7. Send button is functional and capability-aware
8. Interrupt and cancel buttons work
9. No layout overflow or scrolling issues
10. Dark mode toggle works (if theme provider supports it)
