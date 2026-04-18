# Migrations — Agent Instructions

## Key Principles

1. **Never import migrations from runtime code.** Migrations import from `meridian.*`, never the reverse. The main codebase must work without the migrations directory.

2. **Migrations are standalone scripts.** Each can run via `python migrations/vNNN_name/migrate.py /path/to/repo`. No framework dependencies beyond what Meridian itself needs.

3. **Check before mutating.** Every migration must detect if it's already been applied and no-op gracefully.

4. **Track both locations.** Some migrations affect repo state (`.meridian/`), some affect user state (`~/.meridian/projects/<uuid>/`), some affect both. Update tracking in the appropriate location(s).

## Creating a New Migration

### 1. Choose a version number
Look at `registry.toml` for the next available `vNNN`. Use 3 digits, zero-padded.

### 2. Create the directory structure
```
migrations/vNNN_short_name/
  README.md      # Required: what, why, when
  check.py       # Required: detection logic
  migrate.py     # Required: transformation logic
  rollback.py    # Optional: undo logic
```

### 3. Write the check script
Must return JSON to stdout:
```json
{"status": "needed", "reason": "human-readable explanation"}
{"status": "done", "reason": "already migrated"}
{"status": "not_applicable", "reason": "fresh project, no legacy state"}
```

### 4. Write the migrate script
- Call check first, exit early if not needed
- Perform transformation
- Update `.migrations.json` tracking
- Return JSON result to stdout

### 5. Register in registry.toml
```toml
[v001]
name = "uuid_state_split"
description = "Move runtime state from repo to user-level directory"
introduced = "0.0.34"
affects = ["repo", "user"]  # Which state roots are affected
```

## Testing Migrations

1. Create a test fixture with pre-migration state
2. Run the migration
3. Verify post-migration state
4. Run again to verify idempotency
5. Test on fresh project to verify not_applicable path

## Common Patterns

### Reading legacy state
```python
from meridian.lib.state.paths import resolve_repo_state_paths
repo_state = resolve_repo_state_paths(repo_root)
legacy_spawns = repo_state.root_dir / "spawns.jsonl"
```

### Writing to user state
```python
from meridian.lib.state.user_paths import get_project_uuid, get_project_state_root
uuid = get_project_uuid(repo_root / ".meridian")
if uuid:
    user_root = get_project_state_root(uuid)
```

### Atomic file operations
```python
from meridian.lib.state.atomic import atomic_write_text
atomic_write_text(target_path, content)
```

## Don't

- Don't auto-run migrations on CLI startup
- Don't delete source data until migration is confirmed successful
- Don't assume paths exist — check and handle missing state gracefully
- Don't import from `migrations.*` anywhere in `src/meridian/`
