# A00: Runtime Home and State Boundaries

## Summary

This architecture leaf defines Meridian's runtime-state model: project identity via UUID, user-level ephemeral state, and clear ownership boundaries.

## Realizes

- `../spec/runtime-boundaries.md` — `HOME-1.u1`, `HOME-1.u2`, `HOME-1.u3`, `HOME-1.u4`, `HOME-1.p1`, `HOME-1.p2`

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
                ├── output.jsonl
                ├── report.md
                ├── harness.pid
                └── heartbeat
```

## Project UUID

Project identity is a UUID stored in `.meridian/id`.

### Generation

- Generated on first spawn or `meridian init`
- Standard UUID v4 (`uuid.uuid4()`)
- Stored as plain text (36 characters, no newline)

### Stability

The UUID moves with the project folder. When you move or rename a project, the UUID comes along. No derivation from paths, git remotes, or other mutable state.

### Path Contract

```python
def get_project_uuid(meridian_dir: Path) -> str:
    """Read or generate the project UUID."""
    id_file = meridian_dir / "id"
    if id_file.exists():
        return id_file.read_text().strip()
    
    # Generate on first access
    new_uuid = str(uuid.uuid4())
    id_file.write_text(new_uuid)
    return new_uuid
```

## User State Root

The user-level state root holds all ephemeral runtime state.

### Platform Defaults

| Platform | Default Value |
|----------|---------------|
| Unix (macOS, Linux) | `~/.meridian/` |
| Windows | `%LOCALAPPDATA%\meridian\` |

If `LOCALAPPDATA` is missing on Windows, fall back to `%USERPROFILE%\AppData\Local\meridian\`.

### Resolution

```python
def get_user_state_root() -> Path:
    if env := os.environ.get("MERIDIAN_HOME"):
        return Path(env)
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "meridian"
        return Path(os.environ["USERPROFILE"]) / "AppData" / "Local" / "meridian"
    return Path.home() / ".meridian"
```

### Project State Path

```python
def get_project_state_dir(user_root: Path, project_uuid: str) -> Path:
    return user_root / "projects" / project_uuid
```

## Ownership Model

### Three Owners

| Owner | What it owns | Where |
|-------|--------------|-------|
| Repo `.meridian/` | Project UUID, committed artifacts | `<repo>/.meridian/` |
| User state root | Runtime state (spawns, sessions, cache) | `~/.meridian/projects/<UUID>/` |
| Harness adapters | Harness-native storage | `.claude/`, `~/.codex/`, etc. |

### Repo `.meridian/` Contents

Only committed/shared artifacts plus the UUID:

| File | Purpose |
|------|---------|
| `id` | Project UUID (36-char UUID v4) |
| `work/` | Work item artifacts (transitional) |
| `fs/` | Agent documentation (transitional) |
| `.gitignore` | Ignore policy |

### User State Root Layout

```
~/.meridian/
└── projects/
    └── <UUID>/
        ├── spawns.jsonl        # Spawn metadata index
        ├── sessions.jsonl      # Session metadata index
        ├── cache/              # Project-scoped cache
        └── spawns/
            └── <spawn-id>/
                ├── output.jsonl
                ├── report.md
                ├── harness.pid
                └── heartbeat
```

## Spawn-ID as Universal Key

All per-run state is keyed by `spawn_id`:

- Spawned subagents have `spawn_id`s
- Primary sessions also receive `spawn_id`s
- `chat_id` is harness-level session metadata, NOT a storage key
- Layout is uniform regardless of launch origin

## State Migration

When this design is implemented, runtime state migrates from repo-level to user-level:

| Artifact | Old Location | New Location |
|----------|--------------|--------------|
| Spawn index | `.meridian/spawns.jsonl` | `~/.meridian/projects/<UUID>/spawns.jsonl` |
| Session index | `.meridian/sessions.jsonl` | `~/.meridian/projects/<UUID>/sessions.jsonl` |
| Per-spawn artifacts | `.meridian/spawns/<sid>/` | `~/.meridian/projects/<UUID>/spawns/<sid>/` |
| Cache | `.meridian/cache/` | `~/.meridian/projects/<UUID>/cache/` |

**Migration strategy:** None. Per CLAUDE.md "No backwards compatibility needed." Fresh runs use the new layout.

## Why UUID Instead of Derivation

Previous designs proposed deriving a `project-key` from git remote URLs or canonicalized paths. This was complex and fragile:

- Git remote detection fails for non-git projects
- Path canonicalization has platform edge cases
- Neither survives project moves reliably

UUID is simpler:
- Generated once, stored in `.meridian/id`
- Moves with the project folder
- Works for any project type
- No normalization or derivation logic

The tradeoff is that cloning a repo creates a new UUID (the `id` file isn't typically committed). This is acceptable because ephemeral state doesn't need to be shared across clones.

## Module Ownership

| Module | Owns |
|--------|------|
| `src/meridian/lib/state/user_paths.py` (new) | User state root resolution, project UUID access, project state paths |
| `src/meridian/lib/state/paths.py` | Repo `.meridian/` directory structure (scope reduced) |

## Open Questions

None. The UUID model is deliberately simple.
