# Decision Log

## D1: Session ID format — 8-char lowercase hex

**Decision:** Session IDs use `secrets.token_hex(4)` — 8 lowercase hex characters (e.g., `a7f3b2c1`).

**Reasoning:** The ID needs to be URL-safe, short, and collision-resistant enough for a local dev tool. 2^32 (~4.3B) possible IDs is vastly more than any local instance will generate. Hex characters avoid case-sensitivity issues (unlike base64url) and special characters (unlike UUID dashes).

**Rejected:**
- Full UUID (`550e8400-e29b-...`) — too long for URLs. `/s/550e8400-e29b-41d4-a716-446655440000` is ugly.
- `secrets.token_urlsafe(6)` (8 chars base64url) — includes `-` and `_` characters, looks less clean in URLs.
- `uuid4().hex[:8]` — same entropy as token_hex(4) but semantically misleading (it's not a UUID).
- Base36 (a-z0-9) — no real advantage over hex, slightly larger alphabet is unnecessary.

## D2: Router choice — wouter

**Decision:** Use `wouter` (~1.5kb) for client-side routing.

**Reasoning:** The app has exactly two routes: `/` (dashboard) and `/s/:sessionId` (session view). wouter provides `useRoute`, `useLocation`, and `<Route>` — everything needed with no ceremony. It requires no provider wrapper, no data loading setup, and no build config changes.

**Rejected:**
- `react-router` v7 (~30kb) — brings data loading, nested layouts, actions, and loaders that we don't need. 20x the bundle size for features we won't use.
- `@tanstack/router` — type-safe routing is nice but heavy setup for 2 routes. Overkill.
- Manual routing (`window.location.pathname` + popstate) — doable but reinvents solved problems (param extraction, navigation, history).

## D3: Session storage — JSONL append-only file

**Decision:** Sessions persist to `.meridian/app/sessions.jsonl` as append-only JSONL. No update or delete events.

**Reasoning:** Sessions are immutable once created — the spawn behind them has its own lifecycle in `spawns.jsonl`. The session registry only needs to answer "what spawn does this session_id map to?" Append-only JSONL follows the existing pattern used by `spawns.jsonl` and `sessions.jsonl` (CLI sessions). No new abstractions needed.

**Rejected:**
- In-memory only — URLs wouldn't survive server restarts. A bookmarked `/s/a7f3b2c1` would 404 after a restart.
- SQLite — adds a dependency and complexity for what's essentially a key-value lookup.
- JSON file (not JSONL) — requires read-modify-write instead of append, which is less crash-safe.

## D4: Server discovery — per-server files in user-level directory

**Decision:** Each running server writes a JSON file to `~/.meridian/app/servers/<hash>.json` (hash of repo_root). `meridian app list` reads this directory and validates each entry.

**Reasoning:** `meridian app list` needs to find servers across all repos. The repo-level lockfile (`.meridian/app/server.json`) only tells you about the current repo. A user-level directory acts as a cross-repo index. One file per server is simpler than a shared JSONL because there's no need for event projection — just read the files and validate.

**Rejected:**
- User-level JSONL with start/stop events — requires projection logic, and concurrent writers from multiple server processes could interleave events. Per-file approach uses atomic tmp+rename per server.
- Scanning all repos for lockfiles — we don't know where all repos are.
- Unix socket registry — adds complexity and doesn't survive across reboots/crashes.

## D5: Port selection — probe from 8420 with a 10-port range

**Decision:** When no `--port` is specified, probe ports 8420-8429 using TCP socket bind test. Use the first available port.

**Reasoning:** Port 8420 is the default for familiarity. If it's taken (another repo's server, or another process), incrementing through a small range finds an available port without requiring the user to specify one. The 10-port range is small enough to probe instantly.

**Rejected:**
- `port=0` (OS-assigned random port) — produces unpredictable ports like 52341, which are hard to remember and look wrong in browser tabs. The Jupyter model uses sequential probing for the same reason.
- Always require `--port` when default is taken — poor UX for a common case (multiple repos running simultaneously).
- Large range (8420-8520) — unnecessary. If 10 ports are all taken, something unusual is happening and the user should know about it.

## D6: SPA static serving — SPAStaticFiles subclass

**Decision:** Subclass Starlette's `StaticFiles` to return `index.html` for any 404 (SPA fallback). Mount at `/` as currently done.

**Reasoning:** Client-side routes (`/s/a7f3b2c1`) have no corresponding files in `frontend/dist/`. The current `StaticFiles(html=True)` only handles directory-level `index.html`, not arbitrary SPA paths. Subclassing with a 404→index.html fallback is the standard pattern for SPA hosting in Starlette/FastAPI. API routes registered via decorators take priority over mounts, so `/api/...` requests are handled correctly.

**Rejected:**
- Explicit page routes (`@app.get("/")`, `@app.get("/s/{session_id}")`) + separate asset mount — more verbose, requires handling root-level static files (favicon.ico) separately, and must be kept in sync with frontend route changes.
- Catch-all route (`@app.get("/{path:path}")`) — in FastAPI, decorated routes can take priority over mounts in confusing ways, and a catch-all would also match `/api/...` 404s unless carefully ordered.
- Nginx/reverse proxy SPA handling — adds infrastructure dependency for a local dev tool.

## D7: Session API as primary frontend interface

**Decision:** Frontend uses `POST/GET /api/sessions` exclusively. The existing `/api/spawns` endpoints remain for backward compatibility and direct API access.

**Reasoning:** The session API wraps the spawn API with session-level addressing. The frontend never needs to know about spawn IDs — it works entirely with session IDs. Keeping the spawn API unchanged means no migration burden for any direct API consumers. The session API is a thin layer that delegates to SpawnManager using the mapped spawn_id.

**Constraint discovered:** The WebSocket subscriber model in SpawnManager allows only one subscriber per spawn. This means only one browser tab can receive live events per session. This is existing behavior and acceptable for v1, but worth noting for the `--host` multi-user future where multiple people might open the same session URL.

## D8: Sessions namespace under `.meridian/app/`

**Decision:** All app-specific state lives under `.meridian/app/` — lockfile at `server.json`, sessions at `sessions.jsonl`.

**Reasoning:** `.meridian/` already has `sessions.jsonl` for CLI sessions (a completely different concept). Using `.meridian/app/sessions.jsonl` avoids naming collision and groups all app-specific state under a clear namespace. The `app/` directory is created on first `meridian app` invocation.

**Constraint discovered:** The existing `.meridian/.gitignore` uses a `*` (ignore everything) pattern with explicit `!` exclusions for tracked files. This means `.meridian/app/` is automatically ignored — no gitignore changes needed.

## D9: Startup serialization — flock across the entire startup flow

**Decision:** Add `.meridian/app/server.flock` held from stale-check through socket bind and lockfile write. Released before uvicorn starts accepting requests.

**Reasoning:** Reviewer (p1260) identified that two concurrent `meridian app` invocations could both miss the lockfile, both probe the same port, and race at bind. The startup flock serializes the entire startup sequence — the first invocation holds the lock through bind and lockfile creation, the second finds the lockfile and opens the browser to the existing server. This follows the existing `fcntl.flock` pattern used by `spawns.jsonl.flock` and `sessions.jsonl.flock`.

**Rejected:** Per-step locking (flock only around lockfile write) — doesn't prevent the port probe race because two processes can both find the port available before either writes the lockfile.

## D10: Bind-and-hold port selection (eliminates probe-to-bind race)

**Decision:** Bind a TCP socket during startup, hold it open through lockfile creation, and pass the file descriptor to uvicorn. No gap between port availability check and server bind.

**Reasoning:** Reviewer (p1260) identified the probe-then-bind race. By binding immediately and holding the socket, the port is owned by this process from the moment it's confirmed available. The actual port number is read from `sock.getsockname()` after bind, ensuring the lockfile contains the correct port.

**Rejected:** Probe-then-bind (original design) — accepted but dismissed race window. The bind-and-hold approach is equally simple and eliminates the race entirely.

## D11: Draining flag for clean shutdown

**Decision:** Set an `asyncio.Event` draining flag on SIGTERM. `POST /api/sessions` checks this flag and returns 503 during shutdown. Wait for in-flight creates to complete before SpawnManager.shutdown().

**Reasoning:** Reviewer (p1260) identified that `SpawnManager.shutdown()` only walks `_sessions`, but a spawn being created in `start_spawn()` isn't in `_sessions` until setup completes. The draining flag prevents new creates from starting, and the wait ensures in-flight ones complete before shutdown proceeds.

## D12: Session creation failure compensation

**Decision:** If session JSONL persistence fails after the spawn is already started, call `SpawnManager.stop_spawn()` to cancel the orphaned spawn and return 500.

**Reasoning:** Reviewer (p1260) identified that the "atomic" claim for `POST /api/sessions` was misleading — it's actually two sequential operations (start spawn, write session). If the second fails, we'd have a running spawn with no session URL. The compensating action (stop the spawn) ensures no orphaned spawns exist.

## D13: Rename SessionRegistry → AppSessionRegistry

**Decision:** Use `AppSessionRegistry` and `AppSessionEntry` as class names. Module lives at `src/meridian/lib/app/session_registry.py`.

**Reasoning:** Reviewer (p1260) noted naming collision risk with existing `SpawnSession` in `spawn_manager.py` and CLI `sessions.jsonl`. The `App` prefix makes the scope unambiguous and keeps the URL-alias layer clearly in `lib/app/`, separate from the state layer in `lib/state/`.

## D14: v1 session URLs — metadata only for non-live sessions

**Decision:** For v1, session URLs for completed or server-restarted spawns show metadata (status, harness, prompt) but no event replay. Full replay from `output.jsonl` is a future enhancement.

**Reasoning:** Reviewer (p1260) identified that the design promised bookmarkable URLs without defining history hydration. Building output.jsonl replay is significant scope. For v1, showing terminal status and metadata is sufficient — the URL is still navigable and informative, just not a full transcript. The architecture supports adding replay later without URL changes.

## D15: Stale detection uses PID-alive only, not health check

**Decision:** A lockfile is stale if and only if the PID is dead. If the PID is alive but the health check fails, the server is treated as "starting" (not stale).

**Reasoning:** Re-reviewer (p1261) identified that the startup flock was released before uvicorn was ready to serve `/api/health`. A second `meridian app` arriving during this window would see "PID alive, health check fails" and incorrectly treat the lockfile as stale. By using PID-alive as the sole validity check, the startup window is harmless — the second invocation sees a valid lockfile and defers to the first server.

**Rejected:** Keep health check as validity gate — introduces the startup window race. Extend flock until health check passes — complicates the flow (flock must be held across async uvicorn startup) and blocks the second invocation unnecessarily.

## D16: Counter-based in-flight tracking for shutdown

**Decision:** Use an atomic counter incremented on `POST /api/sessions` entry and decremented on completion (try/finally). Shutdown waits for counter == 0 with a 10s safety timeout.

**Reasoning:** Re-reviewer (p1261) identified that the "wait up to 5s" approach was time-based and didn't account for actual in-flight state. A counter tracks exactly how many create requests are in progress. The timeout is a safety bound for truly stuck requests, not the primary synchronization mechanism.

**Overruling reviewer on timeout completeness (p1265):** Reviewer p1265 flagged the 10s timeout as "not a true guarantee" since shutdown proceeds anyway after timeout. This is intentional: a local dev tool should not hang indefinitely on Ctrl-C because a spawn creation is stuck. The counter-based approach closes the normal-case race (creates that take <10s, which is all of them). The timeout handles the pathological case (stuck harness, network hang) by proceeding with a warning log. An indefinite wait would create a worse problem — an unresponsive shutdown requiring SIGKILL.

## D17: Single server per machine (Jupyter model)

**Decision:** Change from one server per repo to one server per machine. A single `meridian app` server at localhost:8420 serves all repos.

**Reasoning:** The per-repo model required cross-repo discovery (`~/.meridian/app/servers/` directory, hash-based filenames, reconciliation between repo-level and user-level state). A single server eliminates this complexity entirely: one lockfile, one sessions registry, one flock, one port. The Jupyter model is familiar — developers already expect a single dashboard at one URL showing all their work. It also avoids the port exhaustion issue where many repos each claim a port from the 8420-8429 range.

**Rejected:**
- Per-repo servers (original design) — more complex lifecycle management (server registry, hash-based discovery, dual lockfiles), port range exhaustion with many repos, confusing UX when the user has to remember which port maps to which repo.
- Hybrid (one server, but lockfile per repo) — unnecessary indirection. With one server, one lockfile at `~/.meridian/app/server.json` is sufficient.

## D18: SpawnManager removes global state_root/repo_root

**Decision:** `SpawnManager.__init__()` takes no path arguments. Each `SpawnSession` carries its own `state_root` and `repo_root` derived from `ConnectionConfig.repo_root`.

**Reasoning:** With a single server handling multiple repos, there is no single "state root" or "repo root." Each spawn belongs to a specific repo, and its artifacts (output.jsonl, inbound.jsonl, control.sock) live in that repo's `.meridian/spawns/` directory. The `ConnectionConfig` already carries `repo_root` per-spawn — the SpawnManager just needs to use it instead of a global.

**Constraint discovered:** Spawn IDs (`p1`, `p2`) are only unique within a repo. Two spawns from different repos can have the same spawn_id. The SpawnManager's internal `_sessions` dict must use a compound key — see D19.

## D19: Compound spawn key — `(repo_root, spawn_id)` tuple

**Decision:** SpawnManager uses `(repo_root, spawn_id)` as the compound key for its internal `_sessions` dict, with a `SpawnKey = tuple[Path, SpawnId]` type alias.

**Reasoning:** Spawn IDs are repo-scoped, not globally unique. With multiple repos in one server, `p1` from repo-alpha and `p1` from repo-beta are different spawns. A compound key is the simplest correct approach — explicit, type-safe, and doesn't require inventing a new ID format.

**Rejected:**
- Hash-based compound ID (e.g., `sha256(repo_root + spawn_id)[:12]`) — obscures the components, harder to debug, and gains nothing since the tuple works fine as a dict key.
- Globally unique spawn IDs — would require changing the spawn_store ID generation, which is out of scope and breaks the simplicity of per-repo sequential IDs.

## D20: Eliminate server registry directory

**Decision:** Remove `~/.meridian/app/servers/` entirely. With one server per machine, `~/.meridian/app/server.json` (single lockfile) is the only server state file.

**Reasoning:** The servers directory existed to answer "what servers are running across all my repos." With a single server, this question is trivially answered by one file. The hash-based filenames, reconciliation logic between repo-level and user-level state, and the "crash between lockfile and registry write" edge case all disappear.

## D21: Session entries include `repo_root`

**Decision:** Each entry in `~/.meridian/app/sessions.jsonl` includes a `repo_root` field — the absolute path to the repo the spawn belongs to.

**Reasoning:** The sessions registry is now user-level (not per-repo), so it must know which repo each session belongs to. This is how the server finds spawn artifacts (in `<repo_root>/.meridian/spawns/<spawn_id>/`), how the dashboard groups sessions by repo, and how `POST /api/sessions` spawn creation targets the correct repo's state root.

## D22: `POST /api/sessions` requires `repo_root`

**Decision:** The `repo_root` field is required in `POST /api/sessions`. The server has no default repo — every spawn must explicitly declare which repo it belongs to.

**Reasoning:** With a single server handling multiple repos, the server cannot assume which repo the user means. The CLI resolves `repo_root` from `cwd` before calling the API. The frontend includes it from a repo selector. Validation ensures the path exists and contains `.meridian/`.

**Rejected:**
- Default to the repo of the last session — fragile and surprising when working across repos.
- Optional `repo_root` with server-level default — the server is repo-agnostic by design; adding a default contradicts that.

## D23: AppSessionRegistry keyed by `(repo_root, spawn_id)` for reverse lookup

**Decision:** The `_spawn_to_session` reverse lookup dict uses `(Path, SpawnId)` as the key (matching SpawnManager's compound key).

**Reasoning:** Since spawn IDs are only unique within a repo, a reverse lookup from spawn_id to session_id must also include repo_root to be unambiguous. The `get_by_spawn()` method requires both parameters.

## D24: Extend existing frontend-ui-redesign.md rather than rewrite

**Decision:** Add edge cases, failure modes, loading states, scope boundaries, and accessibility sections to the existing `frontend-ui-redesign.md` rather than creating a new design doc.

**Reasoning:** The existing doc was written to address these exact requirements and covers layout architecture, component hierarchy, file structure, routing, all four composer controls, model browser, hooks, session creation flow, backend endpoints, state flow, and implementation ordering. Rewriting would duplicate 90% of the content and create confusion about which doc is canonical. The gaps (edge cases, loading states, a11y) are additive sections that slot into the existing structure.

**Rejected:**
- **New doc in a separate work item** — the design is part of `app-session-architecture`, and the existing doc establishes the canonical location.
- **Minimal delta doc** — edge cases need to be co-located with the components they affect, not in a separate file that implementers have to cross-reference.

## D25: Multi-repo deferred in frontend only

**Decision:** Frontend assumes single-repo. No repo selector, no repo grouping in sidebar. `POST /api/sessions` omits `repo_root`; backend uses server's launch context. Backend session registry retains multi-repo support (each session carries `repo_root`).

**Reasoning:** Requirements explicitly drop "Multi-repo support / Jupyter-style repo switching." The backend's multi-repo support is essentially free (session entries already have `repo_root`), so keeping it doesn't add complexity. Removing it from the frontend eliminates the repo selector, repo grouping in sidebar, and repo context in headers — significant UX surface area with no current use case.

**Constraint discovered:** `repo_root` is still required in the session registry JSONL format because spawn IDs are only unique within a repo. Even in single-repo mode, the backend must record which repo a session belongs to for artifact path resolution.

## D26: No event replay for completed sessions in v1

**Decision:** Completed sessions show metadata only (harness, model, agent, status, timestamps). No historical thread content. Event replay from `output.jsonl` is a future enhancement.

**Reasoning:** Replay requires reading the full `output.jsonl`, re-processing through the streaming reducer, handling partial/interrupted events, and performance consideration for long sessions. The architecture supports adding replay later without changes to session URLs, component structure, or the streaming protocol — the reducer already processes events incrementally, so feeding historical events is the same code path.

## D27: Effort is creation-time only (reviewers p1362, p1364)

**Decision:** The effort level is set when the session is created and cannot be changed mid-session. The `POST /api/sessions/{sid}/effort` endpoint is removed from the design.

**Reasoning:** Both the gpt-5.4 alignment reviewer and gpt-5.2 feasibility reviewer identified that effort injection mid-session is not feasible with the current harness architecture. Claude maps effort to `--budget-tokens` CLI flag at spawn start. Codex maps to `--model-reasoning-effort` at spawn start. Neither harness adapter supports changing effort after the process launches. `SpawnManager.inject()` sends a user message — injecting an effort-change "command" as a user message would pollute the conversation and is unlikely to change the harness's behavior.

**Rejected:**
- **Inject effort via text command** — would pollute the conversation with a non-user message. Harness adapters don't parse injected messages as configuration changes.
- **Add a new harness capability for runtime effort** — significant new architecture across all adapters, out of scope for v1.
- **Effort via control socket** — the control socket routes through `SpawnManager.inject()` which sends a user message. Same problem.

## D28: Extract SessionConfigBar from Composer (reviewer p1363)

**Decision:** Session configuration controls (HarnessToggle, ModelButton, EffortSelector, AgentSelector) are extracted into a separate `SessionConfigBar` component with its own `useSessionConfig` hook. The Composer stays focused on text authoring (textarea + send/interrupt/cancel).

**Reasoning:** The opus structural reviewer (p1363) flagged that loading session configuration onto the Composer would make it a god component with mixed responsibilities — text input, harness selection, model browsing, effort control, and agent selection. Extracting `SessionConfigBar` gives it one job (config controls) and keeps Composer's existing single job (text authoring). The `useSessionConfig` hook provides a single source of truth for the bidirectional harness ↔ model state.

**Rejected:**
- **Keep controls in Composer** — creates a component with 6+ concerns. Violates single responsibility.
- **Inline state management per control** — the bidirectional harness/model sync requires coordinated state. Without a single hook, the sync logic would be split across components.

## D29: Rename SpawnChannel → SessionChannel (reviewer p1363)

**Decision:** Rename `SpawnChannel` to `SessionChannel` and its file from `spawn-channel.ts` to `session-channel.ts`. The class API is identical — only the URL builder and naming change.

**Reasoning:** The opus structural reviewer (p1363) flagged the naming confusion: `useThreadStreaming(sessionId)` creating a `SpawnChannel(sessionId)` is misleading because `sessionId !== spawnId`. The session-to-spawn resolution happens server-side. The frontend works exclusively with session IDs, so the transport class should reflect that.

## D30: repo_root optional in POST /api/sessions for v1 (resolving D22 conflict)

**Decision:** `repo_root` is optional in `POST /api/sessions`. If omitted, the backend uses the server's launch context. This resolves the conflict between the UI redesign doc (which says frontend omits repo_root) and the session-registry doc (which says repo_root is required).

**Reasoning:** The gpt-5.4 alignment reviewer and gpt-5.2 feasibility reviewer both identified this contract conflict. Making `repo_root` optional with a server default satisfies both: the v1 single-repo frontend omits it, and future multi-repo frontends can send it explicitly. The session registry still records `repo_root` on every entry for artifact path resolution (spawn IDs are only unique within a repo).

## D31: Session schema extended with agent and effort fields (reviewer p1362)

**Decision:** The session JSONL entry and `GET /api/sessions/{id}` response include `agent` and `effort` fields alongside the existing `harness` and `model`.

**Reasoning:** The gpt-5.4 alignment reviewer identified that the locked SessionConfigBar in SessionView needs to display the session's agent and effort, but the session registry only stored harness and model. Without these fields, there's no read path for the selected agent or effort level after navigation/reload. Adding them to the session entry is trivial — they're recorded at creation time and never change.
