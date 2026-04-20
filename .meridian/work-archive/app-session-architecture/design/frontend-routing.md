# Frontend Routing

## Router Choice: wouter

The frontend currently has no routing library. With exactly two routes (`/` and `/s/:sessionId`), a minimal router is the right fit.

**wouter** (~1.5kb gzipped) provides `useRoute`, `useLocation`, and a `<Route>` component — everything needed for two-route SPA routing without the overhead of react-router's data loading, nested layouts, or action patterns.

New dependency: `wouter` (add via `pnpm add wouter`).

## URL Routes

| Path | Component | Purpose |
|------|-----------|---------|
| `/` | `<Dashboard />` | List sessions grouped by repo, create new spawns |
| `/s/:sessionId` | `<SessionView />` | Thread view for one session |
| `*` (catch-all) | Redirect to `/` | Unknown paths go to dashboard |

## Component Restructuring

### Current Structure

```
App.tsx                    ← Conditional: SpawnSelector OR thread view
├── SpawnSelector.tsx      ← "Start New Spawn" form
├── SpawnHeader.tsx        ← Spawn ID + harness + status badges
├── ThreadView.tsx         ← Event stream rendering
├── Composer.tsx           ← User input + send
├── StreamingIndicator.tsx ← "Agent is typing..."
└── StatusBar.tsx          ← Footer with connection state
```

`App.tsx` manages all state: spawn selection, WebSocket connection, streaming state. It conditionally renders either the selector or the thread view based on whether `spawnId` is set.

### Target Structure

```
App.tsx                    ← Shell: header + router + footer
├── Dashboard.tsx          ← Route: /
│   ├── RepoGroup.tsx      ← Sessions grouped by repo
│   ├── SessionCard.tsx    ← One session in the list
│   └── SpawnSelector.tsx  ← "Start New Spawn" form (with repo selector)
├── SessionView.tsx        ← Route: /s/:sessionId
│   ├── SpawnHeader.tsx    ← Session ID + repo + harness + status badges
│   ├── ThreadView.tsx     ← Event stream rendering (unchanged)
│   ├── Composer.tsx       ← User input (unchanged)
│   └── StreamingIndicator ← (unchanged)
└── StatusBar.tsx          ← Footer (context-aware)
```

### App.tsx Changes

`App.tsx` becomes a thin shell with routing. All spawn/session state management moves into `SessionView.tsx`.

```tsx
// Simplified App.tsx
import { Route, Switch } from "wouter"

function App() {
  return (
    <TooltipProvider>
      <div className="flex min-h-screen flex-col bg-background text-foreground">
        <AppHeader />
        <main className="min-h-0 flex-1 px-6 py-6">
          <Switch>
            <Route path="/" component={Dashboard} />
            <Route path="/s/:sessionId" component={SessionView} />
            <Route>
              <Redirect to="/" />
            </Route>
          </Switch>
        </main>
      </div>
    </TooltipProvider>
  )
}
```

The header stays global but simplifies — no more spawn-specific badges in the top bar (those move into `SessionView`). The `StatusBar` component stays but becomes context-aware: on the dashboard it shows server status, on a session view it shows session connection status.

### Dashboard Component (new)

`Dashboard.tsx` composes three sections:

1. **Repo-grouped session list** — fetched from `GET /api/sessions`. Sessions are grouped by `repo_root`, with each group showing:
   - **Repo header** — repo name (last path component of `repo_root`) and full path as tooltip
   - **Session cards** within that repo, each showing:
     - Session ID (displayed as short code, e.g., `a7f3b2c1`)
     - Harness badge (claude/codex/opencode)
     - Status badge (running/succeeded/failed/cancelled/repo_unavailable)
     - Prompt preview (first ~100 chars)
     - Created timestamp (relative, e.g., "2 min ago")
     - Click → navigates to `/s/{session_id}`

2. **Spawn creation form** — the existing `SpawnSelector` component with changes:
   - Includes a **repo selector** — dropdown of known repos (from `GET /api/sessions` repo list, plus the ability to enter a custom path)
   - Passes `repo_root` to `POST /api/sessions`
   - On success, navigates to `/s/{session_id}` using `wouter`'s `useLocation`
   - No longer calls `onSpawnCreated` callback — navigation handles the transition

3. **Empty state** — when no sessions exist yet, show instructions to create the first spawn

**Repo grouping:** The frontend groups by `repo_root` client-side. The API returns a flat list with `repo_root` and `repo_name` on each entry. The dashboard sorts groups by most-recently-active repo first (based on the newest session in each group).

Session list polls `GET /api/sessions` on a 5-second interval to update status badges for active sessions. The poll stops when the component unmounts (tab/route switch).

### SessionView Component (new)

`SessionView.tsx` absorbs the session-specific state and rendering logic currently in `App.tsx`.

```tsx
function SessionView() {
  const [, params] = useRoute("/s/:sessionId")
  const sessionId = params?.sessionId ?? null
  
  // Load session metadata (includes repo_root, repo_name)
  const session = useSessionMetadata(sessionId)
  
  // Connect to WebSocket stream (only if spawn is active)
  const { state, capabilities, channel, cancel, connectionState } =
    useThreadStreaming(sessionId)
  
  // ... render thread view, composer, header, etc.
}
```

Key changes from current `App.tsx`:
- Gets `sessionId` from URL params (not React state)
- No "disconnect" button that clears state — instead, navigate back to dashboard
- The "back to dashboard" action is a link/navigation, not a state reset
- All session-specific state is local to this component
- The `SpawnHeader` shows repo context (repo name) alongside session ID and harness

### SpawnSelector Changes

Changes to the existing `SpawnSelector.tsx`:

1. **API endpoint**: `POST /api/sessions` instead of `POST /api/spawns`
2. **Repo selector**: New dropdown/input for selecting the target repo
3. **Request body**: Includes `repo_root` from the selector
4. **Navigation**: On success, use `useLocation` to navigate to `/s/{session_id}`
5. **Props**: Replace `onSpawnCreated: (spawnId: string) => void` with no callback needed (navigation handles it)

```tsx
// SpawnSelector.tsx — key changes
const [, navigate] = useLocation()
const [repoRoot, setRepoRoot] = useState<string>("")

async function handleCreateSpawn(event: FormEvent) {
  // ... same validation ...
  const response = await fetch("/api/sessions", {
    method: "POST",
    body: JSON.stringify({
      harness,
      prompt,
      model,
      agent,
      repo_root: repoRoot,
    }),
    ...
  })
  const payload = await response.json()
  navigate(`/s/${payload.session_id}`)
}
```

**Repo selector UX:** The repo dropdown is populated from the list of distinct repos that already have sessions (from `GET /api/sessions`). A "Browse..." option allows entering a custom absolute path. The most recently used repo is pre-selected. If no sessions exist yet, the field starts empty and the user must enter a repo path manually.

### useThreadStreaming Hook Changes

The hook currently accepts `spawnId: string | null` and builds a WebSocket URL using the spawn ID. It needs to accept `sessionId` instead and use the session-based WebSocket URL.

```tsx
// Before
export function useThreadStreaming(spawnId: string | null)
// SpawnChannel connects to: /api/spawns/{spawnId}/ws

// After
export function useThreadStreaming(sessionId: string | null)
// SpawnChannel connects to: /api/sessions/{sessionId}/ws
```

The `SpawnChannel` class needs an update to its URL builder:

```tsx
// Before
function buildSpawnWsUrl(spawnId: string, baseUrl?: string): string {
  return `${base}/api/spawns/${spawnId}/ws`
}

// After — rename to buildSessionWsUrl or make configurable
function buildSessionWsUrl(sessionId: string, baseUrl?: string): string {
  return `${base}/api/sessions/${sessionId}/ws`
}
```

The class can be renamed to `SessionChannel` or kept as `SpawnChannel` with the URL pattern updated — the protocol is identical, only the addressing changes.

### StatusBar Changes

The `StatusBar` currently shows spawn_id and harness_id. On the dashboard route, it should show server-level info instead. Two approaches:

1. **Context-aware**: `StatusBar` receives props that differ based on the current route.
2. **Simpler**: `StatusBar` only shows in `SessionView`, dashboard has its own footer or none.

Approach 1 is cleaner. The `StatusBar` accepts optional session-specific props:

```tsx
interface StatusBarProps {
  connectionStatus?: "connecting" | "connected" | "disconnected"
  sessionId?: string | null
  harnessId?: string | null
  repoName?: string | null
}
```

When `sessionId` is null (dashboard), it shows server-level info (e.g., "3 active sessions across 2 repos"). When populated, it shows session info including the repo name.

## SPA Static File Serving

The server needs to serve `index.html` for both `/` and `/s/{session_id}` since these are client-side routes with no corresponding files in `frontend/dist/`.

Replace the current `StaticFiles(html=True)` mount with a SPA-aware subclass:

```python
class SPAStaticFiles(StaticFiles):
    """StaticFiles with SPA fallback — serves index.html for unmatched paths."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code == 404:
                # Client-side route — serve the SPA shell
                return await super().get_response("index.html", scope)
            raise
```

This is mounted last (as currently done) at `/`. API routes registered via `@app.post`/`@app.get`/`@app.websocket` take priority over mounts, so `/api/...` requests never hit the static handler.

The `SPAStaticFiles` class lives in `src/meridian/lib/app/server.py` alongside the app factory.

## Vite Dev Server Config

Update `vite.config.ts` proxy rules to include the new session endpoints:

```ts
server: {
  proxy: {
    "/api": "http://localhost:8420",
    "/ws": { target: "ws://localhost:8420", ws: true },
  },
},
```

The existing proxy config already covers all `/api/...` paths, so no change is needed for REST endpoints. WebSocket connections to `/api/sessions/{id}/ws` are also covered by the `/api` proxy. The `/ws` proxy entry may be unused legacy — verify during implementation.

## Navigation Flows

### Dashboard → Session

1. User is on `/` (Dashboard)
2. Selects a repo from the repo selector (or uses the pre-selected most-recent repo)
3. Clicks "Start Spawn" → `POST /api/sessions` with `repo_root`
4. On success → `navigate("/s/{session_id}")`
5. `SessionView` mounts, reads `sessionId` from URL params
6. `useThreadStreaming(sessionId)` opens WebSocket to `/api/sessions/{sessionId}/ws`

### Session → Dashboard

1. User is on `/s/{sessionId}` (SessionView)
2. Clicks "Back to Dashboard" or the "meridian" logo
3. `<Link href="/">` navigates to dashboard
4. `SessionView` unmounts, WebSocket closes (useEffect cleanup)
5. `Dashboard` mounts, fetches session list across all repos

### Direct URL Navigation

1. User pastes `http://localhost:8420/s/a7f3b2c1` into a new tab
2. Server serves `index.html` (SPA fallback)
3. `wouter` reads URL, renders `SessionView` with `sessionId = "a7f3b2c1"`
4. Component loads session metadata via `GET /api/sessions/a7f3b2c1` (includes repo context)
5. If spawn is active in current server process → connect WebSocket for live streaming
6. If spawn is terminal → show terminal status badge (succeeded/failed/cancelled), prompt, harness, and repo info. No WebSocket connection attempted. Full event replay from `output.jsonl` is a future enhancement — v1 shows metadata only for completed sessions.
7. If spawn was active but server restarted since it started → show stale status from spawn store. No live streaming available (the SpawnManager connection doesn't survive restarts). Future: replay from output.jsonl.
8. If session not found → show "Session not found" error with link back to dashboard

### Multiple Tabs

The dashboard and different session views can be open in separate tabs. No shared state between tabs — each tab maintains its own React state.

**Limitation: one live viewer per session.** SpawnManager's subscriber model allows only one WebSocket subscriber per spawn. If two tabs open the same session URL, the first tab gets live streaming; the second receives an "another client is already connected" error via the WebSocket and falls back to showing session metadata without live events. This is existing SpawnManager behavior and acceptable for a local dev tool.
