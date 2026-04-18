# Requirements: Runtime Home and State Boundaries

## Problem Statement

Meridian's on-disk state model has unclear boundaries:

1. **No clear project identity.** Meridian implicitly uses the repo path as identity, but paths change when projects move.

2. **Runtime state mixed with committed artifacts.** `.meridian/` currently holds both committed shared artifacts and ephemeral runtime state (spawns, sessions).

3. **No user-level state root.** Ephemeral state should live outside the repo so it doesn't pollute version control and can be blown away without losing project config.

## Solution: UUID + User State Root

A deliberately simple model:

1. **Project UUID** — stored in `.meridian/id`, generated once, moves with the project folder
2. **User-level ephemeral state** — `~/.meridian/projects/<UUID>/` holds spawns, sessions, cache
3. **Repo `.meridian/` for committed artifacts only** — work items, fs docs, gitignore

## Goals

### G1: Project Identity via UUID

Each project has a UUID stored in `.meridian/id`:
- Generated on first spawn or `meridian init`
- Standard UUID v4 format
- Moves with the project folder when renamed or relocated

### G2: User-Level State Root

Ephemeral runtime state lives under the user's home directory:
- **Unix default:** `~/.meridian/`
- **Windows default:** `%LOCALAPPDATA%\meridian\`
- **Override:** `MERIDIAN_HOME` environment variable
- **Fallback on Windows:** `%USERPROFILE%\AppData\Local\meridian\` if `LOCALAPPDATA` missing

### G3: State Ownership Clarity

Clear separation of concerns:

| Owner | What it owns |
|-------|--------------|
| Repo `.meridian/` | Project UUID (`id`), committed artifacts (`work/`, `fs/`) |
| User state root | Ephemeral runtime state (`spawns.jsonl`, `sessions.jsonl`, `spawns/`) |
| Harness adapters | Harness-native storage (`.claude/`, `~/.codex/`) |

### G4: Spawn-ID as Universal Key

All per-run state is keyed by `spawn_id`:
- Spawned subagents have spawn IDs
- Primary sessions also receive spawn IDs
- `chat_id` is metadata for session continuity, NOT a storage key

## Non-Goals

### What This Design Explicitly Avoids

- **No derivation algorithm** — no git remote hashing, no path canonicalization
- **No migration path** — fresh runs use the new layout, old state is orphaned
- **No shared UUID** — the `id` file is typically gitignored; cloning creates a new project identity
- **No complex normalization** — no platform-specific path handling beyond the basic defaults

## Target Layout

```
project-folder/
└── .meridian/
    ├── id                # UUID (generated once, stable forever)
    ├── work/             # Work item artifacts (committed)
    ├── fs/               # Agent documentation (committed)
    └── .gitignore        # Manages ignore policy

~/.meridian/              # Windows: %LOCALAPPDATA%\meridian\
└── projects/
    └── <UUID>/           # Ephemeral state keyed by project UUID
        ├── spawns.jsonl
        ├── sessions.jsonl  
        └── spawns/
            └── <spawn-id>/
                ├── output.jsonl
                ├── report.md
                └── ...
```

## Constraints

- Must not break existing config precedence (CLI > ENV > profile > project > user > harness default)
- No backward compatibility required — old `.meridian/spawns.jsonl` is not migrated
- User state root must work on Unix and Windows with sensible defaults

## Target Audience

Researchers who just want Meridian to work. They don't care about git, path normalization, or identity algorithms. They move project folders around and expect things to keep working.
