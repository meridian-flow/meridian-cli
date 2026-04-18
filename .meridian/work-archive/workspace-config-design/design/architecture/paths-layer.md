# A01: Paths Layer

## Summary

This leaf defines the repo-level file ownership boundary. It builds on A00 (runtime-home), which defines the UUID-based project identity and user-level state root.

The target shape has two path abstractions:
- **`UserStatePaths`** — user-level runtime state under `~/.meridian/projects/<UUID>/` (from A00)
- **`StatePaths`** — repo `.meridian/` committed artifacts only (scope reduced)

## Realizes

- `../spec/config-location.md` — `CFG-1.u1`, `CFG-1.u3`
- `../spec/workspace-file.md` — `WS-1.u1`, `WS-1.u2`
- `../spec/bootstrap.md` — `BOOT-1.u1`, `BOOT-1.e2`

## Target State

### StatePaths (Repo-Level)

`StatePaths` owns the repo `.meridian/` directory structure:

```
.meridian/
├── id              # Project UUID (36-char UUID v4)
├── work/           # Work item artifacts
├── fs/             # Agent documentation
├── work-archive/   # Archived work items
└── .gitignore      # Ignore policy
```

### UserStatePaths (User-Level)

`UserStatePaths` owns runtime state under the user state root:

```
~/.meridian/
└── projects/
    └── <UUID>/
        ├── spawns.jsonl
        ├── sessions.jsonl
        ├── cache/
        └── spawns/
            └── <spawn-id>/
```

### Proposed Shape

```python
@dataclass
class StatePaths:
    """Repo-level .meridian/ structure."""
    root_dir: Path          # .meridian/
    
    @property
    def id_file(self) -> Path:
        return self.root_dir / "id"
    
    @property
    def work_dir(self) -> Path:
        return self.root_dir / "work"
    
    @property
    def fs_dir(self) -> Path:
        return self.root_dir / "fs"


@dataclass  
class UserStatePaths:
    """User-level runtime state."""
    user_root: Path         # ~/.meridian/
    project_uuid: str       # from .meridian/id
    
    @property
    def project_dir(self) -> Path:
        return self.user_root / "projects" / self.project_uuid
    
    @property
    def spawns_path(self) -> Path:
        return self.project_dir / "spawns.jsonl"
    
    @property
    def sessions_path(self) -> Path:
        return self.project_dir / "sessions.jsonl"
    
    def spawn_dir(self, spawn_id: str) -> Path:
        return self.project_dir / "spawns" / spawn_id
```

## Ownership Boundary

| Concern | Owner |
|---------|-------|
| `.meridian/` structure, UUID file, work/fs artifacts | `StatePaths` |
| User state root resolution, platform defaults | `UserStatePaths` |
| Runtime spawn/session indexes, per-spawn artifacts | `UserStatePaths` |

## Module Layout

| Module | Ownership |
|--------|-----------|
| `src/meridian/lib/state/user_paths.py` | **New.** User state root resolution, platform defaults, project UUID access, `UserStatePaths`. |
| `src/meridian/lib/state/paths.py` | Repo `.meridian/` directory structure. `StatePaths`. |

## UUID Access

The project UUID is accessed via `StatePaths`:

```python
def get_project_uuid(state_paths: StatePaths) -> str:
    """Read or generate the project UUID."""
    id_file = state_paths.id_file
    if id_file.exists():
        return id_file.read_text().strip()
    
    # Generate on first access
    new_uuid = str(uuid.uuid4())
    state_paths.root_dir.mkdir(parents=True, exist_ok=True)
    id_file.write_text(new_uuid)
    return new_uuid
```

## What Moves from Repo to User State

| Artifact | Old (Repo) | New (User) |
|----------|------------|------------|
| Spawn metadata index | `.meridian/spawns.jsonl` | `~/.meridian/projects/<UUID>/spawns.jsonl` |
| Session metadata index | `.meridian/sessions.jsonl` | `~/.meridian/projects/<UUID>/sessions.jsonl` |
| Per-spawn artifacts | `.meridian/spawns/<spawn-id>/` | `~/.meridian/projects/<UUID>/spawns/<spawn-id>/` |
| Cache | `.meridian/cache/` | `~/.meridian/projects/<UUID>/cache/` |

## What Stays in Repo `.meridian/`

| Artifact | Status |
|----------|--------|
| `id` | Project UUID (permanent) |
| `work/`, `fs/`, `work-archive/` | Transitional — awaiting cloud/shared alternative |
| `.gitignore` | Committed — manages ignore policy |

## Open Questions

None.
