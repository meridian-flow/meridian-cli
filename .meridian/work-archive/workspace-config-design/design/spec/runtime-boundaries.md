# HOME-1: Runtime Home and State Boundaries

This spec defines the behavioral contract for Meridian's runtime-home model. It is the foundation for all other workspace-config specs.

## Realized by

- `../architecture/runtime-home.md` (A00)

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

## Normative Statements

### HOME-1.u1 — User State Root Resolution

**UBIQUITOUS:** When Meridian resolves the user-level runtime state root, it SHALL use the following resolution order:
1. `MERIDIAN_HOME` environment variable if set
2. Platform default otherwise

### HOME-1.u2 — Platform Default Paths

**UBIQUITOUS:** The platform default for the user state root SHALL be:
- **Unix (macOS, Linux):** `~/.meridian/`
- **Windows:** `%LOCALAPPDATA%\meridian\`

If `LOCALAPPDATA` is missing on Windows, fall back to `%USERPROFILE%\AppData\Local\meridian\`.

### HOME-1.u3 — Repo State Exclusivity

**UBIQUITOUS:** Repo-level `.meridian/` SHALL contain only committed/shared project artifacts plus the project UUID file. All runtime/ephemeral state SHALL live under the user state root.

### HOME-1.u4 — Project UUID Generation

**UBIQUITOUS:** On first spawn or `meridian init`, Meridian SHALL generate a UUID v4 and store it in `.meridian/id` as plain text. This UUID is the project identity.

### HOME-1.p1 — Project Identity Stability

**PROPERTY:** The project UUID stored in `.meridian/id` SHALL remain stable across:
- Repository moves within and across filesystems
- Meridian version upgrades
- Different user sessions on the same machine

The UUID moves with the project folder. No derivation algorithm is required.

### HOME-1.p2 — Spawn-ID Universal Keying

**PROPERTY:** All per-run runtime state (harness home, config, output, report) SHALL be keyed by `spawn_id` exclusively. Both spawned subagents and primary sessions receive `spawn_id`s.

## Ownership Boundaries

### HOME-1.s1 — State Owner Enumeration

**STATE BOUNDARY:** Meridian on-disk state has exactly three owners:

| Owner | Scope | What it owns |
|-------|-------|--------------|
| Repo `.meridian/` | Per-repo | Project UUID (`id`), committed artifacts (`work/`, `fs/`, `.gitignore`) |
| User state root | Per-user, per-project | Runtime state (spawns, sessions, cache) under `projects/<UUID>/` |
| Harness adapters | Per-harness | Harness-native storage and session discovery |

### HOME-1.s2 — No Cross-Owner Writes

**STATE BOUNDARY:** An owner SHALL NOT write to another owner's scope. Specifically:
- Meridian core SHALL NOT write to harness-native storage (`.claude/`, Codex DB)
- Harness adapters SHALL NOT write to user state root app-level state
- Repo-level code SHALL NOT write runtime state under repo `.meridian/` (except the UUID)

## Error Cases

### HOME-1.e1 — Invalid User State Root

**EXCEPTIONAL:** If the user state root:
- Does not exist and cannot be created -> fatal error with clear message
- Exists but is not a directory -> fatal error with clear message
- Exists but is not writable -> fatal error with clear message

### HOME-1.e2 — Missing Project UUID

**EXCEPTIONAL:** If runtime-state operations require project scope but no `.meridian/id` file exists in the walk-up from cwd, Meridian SHALL:
1. If `.meridian/` directory exists, generate and store a new UUID
2. Otherwise fail with a clear message directing the user to run `meridian init` or change to a directory containing `.meridian/`

## Context Boundaries

### HOME-1.c1 — Harness Storage Is Out of Scope

**CONTEXT:** Harness-native storage locations (Claude `.claude/`, Codex `~/.codex/`, OpenCode logs) are harness-owned. This spec does not define their paths or behavior.

### HOME-1.c2 — What Lives Where

| Location | Contents | Durability |
|----------|----------|------------|
| `project/.meridian/id` | Project UUID | Permanent (moves with project) |
| `project/.meridian/` | Committed config, work items, fs docs | Permanent |
| `~/.meridian/projects/<UUID>/` | Spawns, sessions, cache | Ephemeral (can be blown away) |
