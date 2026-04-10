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
