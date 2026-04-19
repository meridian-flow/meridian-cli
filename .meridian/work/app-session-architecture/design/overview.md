# App Session Architecture — Overview

## Problem

`meridian app` launches a local web UI for interacting with agent spawns. The current implementation is a single-page app with no URL routing — everything lives on one page, one spawn at a time, with a hardcoded port and no server lifecycle management. This design adds URL-routable sessions, a dashboard, server lifecycle management, multi-repo support, multi-tab support, and work item integration.

## Architecture

One server per machine, serving all repos — like Jupyter. The server is user-level, not repo-level.

```
┌─────────────────────────────────────────────────────────┐
│  Browser                                                │
│  ┌──────────────┐  ┌────────────────────────────────┐   │
│  │  Dashboard    │  │  Session View                  │   │
│  │  /            │  │  /s/<session_id>               │   │
│  │              │──▶│                                │   │
│  │  Sessions +   │  │  Thread + Composer + WS        │   │
│  │  Works        │  │  + Spawn Tree                  │   │
│  └──────────────┘  └────────────────────────────────┘   │
│         │                       │                        │
│         │  wouter client-side routing                    │
└─────────┼───────────────────────┼────────────────────────┘
          │ REST                  │ REST + WS
┌─────────┼───────────────────────┼────────────────────────┐
│  FastAPI Server (one per machine)                        │
│         │                       │                        │
│  ┌──────▼──────────────────────────────┐                 │
│  │  Session API (/api/sessions/...)    │                 │
│  │  session_id →                       │                 │
│  │  (project_key, spawn_id, repo_root, │                 │
│  │   work_id [nullable])               │                 │
│  └──────┬──────────────────────────────┘                 │
│         │                                                │
│  ┌──────▼──────────────────────────────┐                 │
│  │  SpawnManager                       │                 │
│  │  Runtime root from project_key      │                 │
│  │  Workspace root from repo_root      │                 │
│  │  Compound key:                      │                 │
│  │  (project_key, spawn_id)            │                 │
│  └─────────────────────────────────────┘                 │
│                                                          │
│  ┌─────────────────────────────────────┐                 │
│  │  AppSessionRegistry                 │                 │
│  │  ~/.meridian/app/sessions.jsonl     │                 │
│  │  session_id →                       │                 │
│  │  (project_key, spawn_id, repo_root, │                 │
│  │   work_id [nullable])               │                 │
│  └─────────────────────────────────────┘                 │
│                                                          │
│  ┌─────────────────────────────────────┐                 │
│  │  Project Runtime                    │                 │
│  │  ~/.meridian/projects/<project-key>/│                 │
│  │  spawns.jsonl                       │                 │
│  │  spawns/<spawn-id>/...              │                 │
│  └─────────────────────────────────────┘                 │
│                                                          │
│  ┌─────────────────────────────────────┐                 │
│  │  Server Lifecycle                   │                 │
│  │  User-level lockfile + flock        │                 │
│  └─────────────────────────────────────┘                 │
└──────────────────────────────────────────────────────────┘
```

## Core Concepts

### Sessions and Work Items Are Parallel

Sessions and work items are **parallel concepts**, not a strict hierarchy. A session can exist without a work item (quick exploration), and a work item can have multiple sessions attached.

```
Session (chat_id)               Work Item (work_id)
  ├── work_id [nullable] ────────────┤
  ├── spawns (via parent_id tree)    ├── scratch dir (.meridian/work/<id>/)
  └── session_id (URL alias)         └── design/, plan/, decisions.md
```

**Sessions** are interaction contexts — start chatting immediately, no ceremony required.

**Work items** are optional organization — attach a session to a work item when the exploration becomes structured work with artifacts.

### Spawn Tree Structure

Spawns form a tree via `parent_id`. Each spawn knows its parent spawn, enabling tree display:

```
Session
  └── Root Spawn (p42)
        ├── Child Spawn (p43)
        │     └── Grandchild (p45)
        └── Child Spawn (p44)
```

Spawns don't need to query their parent at runtime — they just do work and finalize. The `parent_id` exists for **display and tracking** by the observer (app, CLI, orchestrator).

### Context Resolution

Agents query their context via CLI, not environment variables:

```bash
meridian context          # Returns work_id, repo_root, state_root, depth
meridian work current     # Returns just work_id (convenience alias)
```

Environment variables that are **kept**:
- `MERIDIAN_CHAT_ID` — inherited, used for work attachment lookup
- `MERIDIAN_DEPTH` — nesting level
- `MERIDIAN_REPO_ROOT`, `MERIDIAN_STATE_ROOT` — paths

Environment variables that are **removed** (replaced by query + convention):
- `MERIDIAN_WORK_ID` — query via `meridian work current`
- `MERIDIAN_WORK_DIR` — derive from convention: `.meridian/work/<work_id>/`
- `MERIDIAN_FS_DIR` — derive from convention: `.meridian/fs/`

## URL Scheme

| URL | Purpose |
|-----|---------|
| `http://localhost:8420/` | Dashboard — sessions (recent) + works (organized) |
| `http://localhost:8420/s/<session_id>` | Session view — thread, composer, spawn tree, streaming |
| `http://localhost:8420/api/sessions` | REST: list/create sessions |
| `http://localhost:8420/api/sessions/<sid>` | REST: get/cancel one session |
| `http://localhost:8420/api/sessions/<sid>/ws` | WebSocket: stream events for session |
| `http://localhost:8420/api/sessions/<sid>/tree` | REST: spawn tree for session |
| `http://localhost:8420/api/works` | REST: list works (optional, for dashboard) |
| `http://localhost:8420/api/health` | Health check (server discovery) |
| `http://localhost:8420/api/spawns/...` | Legacy spawn API (unchanged) |

Session IDs are random 8-char hex strings (e.g., `a7f3b2c1`). They are globally unique and not derived from spawn IDs.

## Key Concepts

**`project_key` is the stable project-scoped Meridian namespace.** Each logical project gets a stable, filesystem-safe `project_key` derived from normalized remote identity or canonical path fallback. User-level Meridian runtime state lives under `~/.meridian/projects/<project_key>/...`. Other designs should depend on this layer when they need project-scoped user-level state, especially harness-native profile/config projection.

**Runtime state is project-keyed; run state is spawn-keyed.** Project-scoped spawn records and per-run runtime artifacts live together:

```text
~/.meridian/projects/<project_key>/
  spawns.jsonl
  spawns/<spawn_id>/
```

`spawn_id` remains the Meridian run identity. Primary sessions launched from the app still get Meridian `spawn_id`s; there is no separate app-session runtime namespace.

**Sessions are metadata aliases, not storage boundaries.** A session is a thin mapping from `session_id` to `(project_key, spawn_id, repo_root, work_id)`. It exists so URLs are shareable, bookmarkable, and opaque. It does not define runtime directory layout. `session_id` and harness `chat_id` remain metadata, not filesystem namespaces.

**`repo_root` still matters, but for workspace shaping.** `repo_root` tells the harness which checkout to operate in and gives the UI a concrete path to display. It no longer doubles as the user-level runtime namespace.

**Harness workspace shaping is distinct from native home/state isolation.** For Codex, workspace shaping uses `--cd` plus `--add-dir`; `CODEX_HOME` is only for isolating native Codex state. For OpenCode, extra path access comes from launch root plus projected config/permissions, especially `permission.external_directory`; there is no dedicated `--add-dir` flag. The `project_key` layer exists so Meridian can project harness-native config/state without conflating that with workspace-root selection.

**One server per machine.** The entire machine gets at most one `meridian app` server. Running `meridian app` from any repo either starts the global server or opens the browser to the existing instance. There is no per-repo server discovery — just one lockfile at `~/.meridian/app/server.json`. This is the Jupyter model: a single dashboard at localhost:8420 showing all agent sessions across all repos.

**Sessions persist across server restarts.** Session-to-spawn mappings are written to `~/.meridian/app/sessions.jsonl` on creation. After a server restart, bookmarked session URLs still resolve — the `AppSessionRegistry` reloads from disk. For completed spawns, the session shows terminal status and metadata. Live streaming is only available for spawns started in the current server process (SpawnManager connections don't survive restarts). Full event replay from `output.jsonl` is a future enhancement.

**Frontend uses client-side routing.** The server serves `index.html` for both `/` and `/s/<session_id>` (SPA fallback). The `wouter` router in the browser parses the URL and renders the correct view. The dashboard and individual session views can be open in separate tabs. However, only one tab can receive live WebSocket events per session (existing SpawnManager subscriber exclusivity). A second tab opening the same session URL sees session metadata but cannot stream live events.

## Dashboard Design

The dashboard shows two views:

**Sessions view (default)** — recent sessions across all projects, session-first entry for quick exploration. Start a new session without picking a work item.

**Works view** — work items grouped by status (active/paused/completed). Each work shows attached sessions and can be expanded to see the spawn tree.

Users can:
1. Start a session immediately (no work item)
2. Attach a running session to a work item later
3. Start a session within an existing work item
4. Browse work items and their sessions/spawns

## Session View

Shows:
- Thread (conversation history)
- Composer (input)
- Spawn tree (collapsible, built from `parent_id` relationships)
- Work attachment (if any, with link to work artifacts)
- Session metadata (model, harness, timestamps)

## Component Design Docs

| Doc | Covers |
|-----|--------|
| [project-key.md](project-key.md) | Stable project identity, runtime artifact paths, harness workspace shaping |
| [server-lifecycle.md](server-lifecycle.md) | User-level lockfile, port selection, start/stop, flock |
| [session-registry.md](session-registry.md) | Session ID generation, project/session storage model, session API endpoints |
| [frontend-routing.md](frontend-routing.md) | Client-side routing, component restructuring, dashboard design |

## What Changes

- **Project-scoped runtime state** — runtime files move under `~/.meridian/projects/<project_key>/...`. Project-scoped spawn records and per-spawn artifact directories share that namespace.
- **SpawnManager** (`src/meridian/lib/streaming/spawn_manager.py`) — removes global `state_root` and `repo_root` constructor params. Each spawn resolves `project_key` from `repo_root`, uses that project root for runtime paths, and uses `repo_root` only for workspace shaping.
- **AppSessionRegistry** — lives at `~/.meridian/app/sessions.jsonl`. Session entries include `project_key`, `repo_root`, and `work_id` (nullable).
- **Server lifecycle** — remains machine-scoped with a user-level lockfile at `~/.meridian/app/server.json`.
- **Session creation API** — `POST /api/sessions` accepts `repo_root` and optional `work_id`, resolves `project_key`, and creates project-scoped runtime state from that key.
- **Dashboard** — shows sessions (recent) and works (organized) with session-first entry.
- **Session view** — adds spawn tree display built from `parent_id` relationships.
- **Context resolution** — `meridian context` command replaces env var projection for work context.

## What Does NOT Change

- **Session ID format** — 8-char hex strings.
- **Meridian run identity** — `spawn_id` remains the per-run storage key inside a project. Sessions do not replace it, and `chat_id` stays metadata only.
- **URL scheme** — `/`, `/s/<session_id>`, `/api/sessions/...`.
- **Frontend routing** — wouter, Dashboard + SessionView components.
- **WS event protocol** — AG-UI event format over WebSocket stays the same.
- **Harness connections** — no changes to connection lifecycle, drain loops, or control sockets.
- **Legacy spawn API** — existing `/api/spawns/...` endpoints remain functional.
- **Shutdown draining** — flock serialization and draining flag work the same way, just at user level.
- **Work item storage** — `.meridian/work-items/`, `.meridian/work/`, `.meridian/work-archive/` stay repo-local.
- **Work attachment mechanism** — `chat_id → work_id` on session records.

## Future: `--host 0.0.0.0` Auth

When `--host` support is added later, authentication will use a token query parameter (`?token=abc123`) that sets a cookie on first visit. The URL structure (`/`, `/s/<session_id>`, `/api/...`) stays identical. The token validation adds a middleware layer — no routing changes needed.

The session API already uses random IDs that aren't guessable, which is a prerequisite for the auth model. The health endpoint will need to be excluded from auth (or use a separate auth mechanism) so discovery probes can reach it.
