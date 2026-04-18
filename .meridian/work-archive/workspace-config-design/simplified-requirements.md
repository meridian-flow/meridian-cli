# Workspace Config — Simplified Requirements

## Core Model

```
project-folder/
└── .meridian/
    └── id                    # UUID (generated once, stable forever)

~/.meridian/                  # Windows: %LOCALAPPDATA%\meridian\
└── projects/
    └── <UUID>/               # ephemeral state keyed by project UUID
        ├── spawns.jsonl
        ├── sessions.jsonl  
        └── spawns/
            └── <spawn-id>/
```

## Principles

1. **UUID = project identity** — generated on first use, stored in `.meridian/id`
2. **Ephemeral user state** — `~/.meridian/` is cache, can be blown away
3. **Survives renames** — UUID moves with project folder
4. **No derivation** — no git remote hashing, no path normalization

## What Lives Where

| Location | Contents | Durability |
|----------|----------|------------|
| `project/.meridian/id` | Project UUID | Permanent (moves with project) |
| `project/.meridian/` | Committed config, work items, fs docs | Permanent |
| `~/.meridian/projects/<UUID>/` | Spawns, sessions, cache | Ephemeral |

## Platform Defaults

| Platform | User State Root |
|----------|-----------------|
| Unix/macOS | `~/.meridian/` |
| Windows | `%LOCALAPPDATA%\meridian\` |

If `LOCALAPPDATA` is missing on Windows, fall back to `%USERPROFILE%\AppData\Local\meridian\`.

## UUID Generation

- Generated on first spawn or `meridian init`
- Standard UUID v4 (`uuid.uuid4()`)
- Stored as plain text in `.meridian/id`

## What This Replaces

- ❌ `project_key` derived from git remote or path hash
- ❌ Complex normalization rules
- ❌ "Stable across moves" via derivation algorithm

## What's Deferred

- App server state (`~/.meridian/app/`) — separate concern
- Multi-project server — future work
- Cloud sync — future work

## Lazy Initialization

- **`.meridian/` created on first write** — not preemptively
- **UUID generated at same time** — when `.meridian/` is first created
- **No explicit init required** — just start using it

```
Need to write state (spawn, session, etc.)?
    ↓
.meridian/ exists?
    ↓
No  → Create .meridian/, generate UUID in id file, then write
Yes → Just write
```

Standard lazy initialization. Don't create structure until needed.
