# App Session Architecture — Overview

## Problem

`meridian app` launches a local web UI for interacting with agent spawns. The current implementation is a single-page app with no URL routing — everything lives on one page, one spawn at a time, with a hardcoded port and no server lifecycle management. This design adds URL-routable sessions, a dashboard, server lifecycle management, and multi-tab support.

## Architecture

The system has four layers that change together:

```
┌─────────────────────────────────────────────────────────┐
│  Browser                                                │
│  ┌──────────────┐  ┌────────────────────────────────┐   │
│  │  Dashboard    │  │  Session View                  │   │
│  │  /            │  │  /s/<session_id>               │   │
│  │              │──▶│                                │   │
│  │  List + Create│  │  Thread + Composer + WS        │   │
│  └──────────────┘  └────────────────────────────────┘   │
│         │                       │                        │
│         │  wouter client-side routing                    │
└─────────┼───────────────────────┼────────────────────────┘
          │ REST                  │ REST + WS
┌─────────┼───────────────────────┼────────────────────────┐
│  FastAPI Server (one per repo)  │                        │
│         │                       │                        │
│  ┌──────▼───────────────────────▼──────┐                 │
│  │  Session API (/api/sessions/...)    │                 │
│  │  Thin layer: session_id → spawn_id  │                 │
│  └──────┬──────────────────────────────┘                 │
│         │                                                │
│  ┌──────▼──────────────────────────────┐                 │
│  │  SpawnManager (unchanged)           │                 │
│  │  Connections, drain loops, fan-out   │                 │
│  └─────────────────────────────────────┘                 │
│                                                          │
│  ┌─────────────────────────────────────┐                 │
│  │  Session Registry                   │                 │
│  │  In-memory dict + .meridian/app/    │                 │
│  │  sessions.jsonl on disk             │                 │
│  └─────────────────────────────────────┘                 │
│                                                          │
│  ┌─────────────────────────────────────┐                 │
│  │  Server Lifecycle                   │                 │
│  │  Lockfile + user-level registry     │                 │
│  └─────────────────────────────────────┘                 │
└──────────────────────────────────────────────────────────┘
```

## URL Scheme

| URL | Purpose |
|-----|---------|
| `http://localhost:8420/` | Dashboard — list active sessions, create new spawns |
| `http://localhost:8420/s/<session_id>` | Session view — thread, composer, streaming |
| `http://localhost:8420/api/sessions` | REST: list/create sessions |
| `http://localhost:8420/api/sessions/<sid>` | REST: get/cancel one session |
| `http://localhost:8420/api/sessions/<sid>/ws` | WebSocket: stream events for session |
| `http://localhost:8420/api/health` | Health check (server discovery) |
| `http://localhost:8420/api/spawns/...` | Legacy spawn API (unchanged) |

Session IDs are random 8-char hex strings (e.g., `a7f3b2c1`). They are globally unique and not derived from spawn IDs.

## Key Concepts

**Session = URL-addressable spawn alias.** A session is a thin mapping from a random, URL-safe ID to a repo-scoped spawn_id. Every session has exactly one spawn. The session exists so that URLs are shareable, bookmarkable, and don't expose sequential spawn IDs.

**One server per repo.** Each repo gets at most one `meridian app` server. Running `meridian app` when a server is already active for the repo opens the browser to the existing instance. Servers register in a user-level directory so `meridian app list` can discover all instances.

**Sessions persist across server restarts.** Session-to-spawn mappings are written to `.meridian/app/sessions.jsonl` on creation. After a server restart, bookmarked session URLs resolve to the correct spawn. If the spawn is still active, the session reconnects for live streaming. If the spawn has completed, the session shows terminal state.

**Frontend uses client-side routing.** The server serves `index.html` for both `/` and `/s/<session_id>` (SPA fallback). The `wouter` router in the browser parses the URL and renders the correct view. The dashboard and session views are independent — each can be open in its own tab.

## Component Design Docs

| Doc | Covers |
|-----|--------|
| [server-lifecycle.md](server-lifecycle.md) | Lockfile, port selection, start/stop/list, user-level registry |
| [session-registry.md](session-registry.md) | Session ID generation, storage format, session API endpoints |
| [frontend-routing.md](frontend-routing.md) | Client-side routing, component restructuring, dashboard design |

## What Does NOT Change

- **SpawnManager** (`src/meridian/lib/streaming/spawn_manager.py`) — unchanged. Sessions are a layer above it.
- **WS event protocol** — AG-UI event format over WebSocket stays the same.
- **Harness connections** — no changes to connection lifecycle, drain loops, or control sockets.
- **Spawn store** (`src/meridian/lib/state/spawn_store.py`) — unchanged. Sessions reference spawn IDs but don't modify spawn state.
- **Legacy spawn API** — existing `/api/spawns/...` endpoints remain functional.

## Future: `--host 0.0.0.0` Auth

When `--host` support is added later, authentication will use a token query parameter (`?token=abc123`) that sets a cookie on first visit. The URL structure (`/`, `/s/<session_id>`, `/api/...`) stays identical. The token validation adds a middleware layer — no routing changes needed.

The session API already uses random IDs that aren't guessable, which is a prerequisite for the auth model. The health endpoint will need to be excluded from auth (or use a separate auth mechanism) so `meridian app list` can probe remote servers.
