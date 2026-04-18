# Migrations

State transformations for Meridian projects. Completely decoupled from runtime code.

## Philosophy

1. **Standalone** — Each migration is an independent script. No runtime coupling.
2. **Per-project** — Migration state tracked per-project, not globally.
3. **Manual** — Migrations don't auto-run. User explicitly triggers them.
4. **Idempotent** — Safe to re-run. Check before mutating.
5. **Forward-only** — Rollbacks are separate scripts, not automatic.

## Structure

```
migrations/
  README.md                 # This file
  AGENTS.md                 # Agent instructions
  registry.toml             # Available migrations + metadata
  v001_uuid_state_split/    # Each migration is a directory
    migrate.py              # Migration script
    README.md               # What it does, when to run
    check.py                # Detection: is this migration needed?
    rollback.py             # Optional: undo the migration
```

## Tracking

Migration state is tracked **per-project** in two locations:

### Repo-local tracking (gitignored)
```
.meridian/.migrations.json
```

Format:
```json
{
  "applied": ["v001", "v002"],
  "history": [
    {"id": "v001", "applied_at": "2024-01-15T10:30:00Z", "result": "ok"},
    {"id": "v002", "applied_at": "2024-01-16T14:00:00Z", "result": "ok"}
  ]
}
```

### User-level tracking (for user-root state)
```
~/.meridian/projects/<uuid>/.migrations.json
```

Same format. Some migrations affect repo state, some affect user state, some affect both.

## Detection

Each migration includes a `check.py` that returns:
- `needed` — Migration should run
- `done` — Already applied (idempotent check)
- `not_applicable` — This project doesn't need this migration (e.g., fresh project)

```bash
python migrations/v001_uuid_state_split/check.py /path/to/repo
# Output: {"status": "needed", "reason": "legacy spawns.jsonl found in repo root"}
```

## Running Migrations

### Check what's pending
```bash
python -m migrations.check /path/to/repo
# Lists migrations and their status (needed/done/not_applicable)
```

### Run a specific migration
```bash
python migrations/v001_uuid_state_split/migrate.py /path/to/repo
# Runs the migration, updates tracking
```

### Future: CLI integration
```bash
meridian migrate status          # Show pending migrations
meridian migrate run v001        # Run specific migration
meridian migrate run --all       # Run all pending migrations
```

## Writing Migrations

1. Create directory: `migrations/vNNN_short_name/`
2. Add `README.md` explaining what/why/when
3. Add `check.py` for detection
4. Add `migrate.py` for the actual transformation
5. Add entry to `registry.toml`
6. Optional: add `rollback.py`

### Migration script template

```python
#!/usr/bin/env python3
"""Migration vNNN: Short description."""

import json
import sys
from pathlib import Path

def check(repo_root: Path) -> dict:
    """Return migration status."""
    # Return {"status": "needed"|"done"|"not_applicable", "reason": "..."}
    ...

def migrate(repo_root: Path) -> dict:
    """Run the migration."""
    status = check(repo_root)
    if status["status"] != "needed":
        return status
    
    # ... do the migration ...
    
    # Update tracking
    tracking_file = repo_root / ".meridian" / ".migrations.json"
    tracking = json.loads(tracking_file.read_text()) if tracking_file.exists() else {"applied": [], "history": []}
    tracking["applied"].append("vNNN")
    tracking["history"].append({"id": "vNNN", "applied_at": "...", "result": "ok"})
    tracking_file.write_text(json.dumps(tracking, indent=2))
    
    return {"status": "ok", "message": "..."}

if __name__ == "__main__":
    repo_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    result = migrate(repo_root)
    print(json.dumps(result, indent=2))
```

## When to Create a Migration

Create a migration when:
- State file format changes (schema migration)
- State file location changes (like UUID split)
- State needs transformation (data migration)

Don't create a migration for:
- New features that don't affect existing state
- Bug fixes that don't require state changes
- Additive changes (new optional fields)
