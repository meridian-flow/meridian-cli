# Server Model Abstraction (Superseded)

Superseded on 2026-04-19 by:
- `../backend-gaps.md`
- `./frontend-routing.md`
- `./server-lifecycle.md`

This previous document assumed legacy server primitives (`/api/sessions*`, `/api/explorer/*`, and `RootRegistry`). Those assumptions are stale.

## Current Canonical Model

- `meridian app` starts a local server for the **current project**.
- One server process serves one project root.
- No project keys, no multi-repo routing within a single server, no root registry.
- Files mode is a single-root project file tree.

## Current API Namespace Contract

- Spawn/session lifecycle: `/api/spawns*`
- File browsing and reads: `/api/files*`
- Work-item state and sync: `/api/work*`

Do not add new `/api/sessions*` or `/api/explorer/*` dependencies. Use the docs listed above for detailed request/response contracts.
