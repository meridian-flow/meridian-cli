# Phase 2 Coder Prompt: UUID and User-State Foundation

## Task

Implement the split repo/user path model for Meridian. This moves ephemeral runtime state (spawns, sessions) from repo-level `.meridian/` to user-level `~/.meridian/projects/<UUID>/`.

## IMPORTANT: Parallel Work Warning

**DO NOT modify these files** — they're being changed by parallel spawn p2206:
- `src/meridian/lib/state/atomic.py`
- `src/meridian/lib/launch/signals.py`
- `src/meridian/lib/launch/runner_helpers.py`

You CAN use `from meridian.lib.platform import IS_WINDOWS, IS_POSIX` — that's already stable.

## What to Build

### 1. Create `src/meridian/lib/state/user_paths.py` (NEW FILE)

```python
"""User-level state root resolution and project UUID management."""

from pathlib import Path
import uuid
import os

from meridian.lib.platform import IS_WINDOWS

def get_user_state_root() -> Path:
    """Return the user-level state root directory.
    
    Resolution order:
    1. MERIDIAN_HOME env var if set
    2. Platform default:
       - Unix/macOS: ~/.meridian/
       - Windows: %LOCALAPPDATA%\meridian\ (fallback: %USERPROFILE%\AppData\Local\meridian\)
    """

def get_or_create_project_uuid(meridian_dir: Path) -> str:
    """Read or generate the project UUID from .meridian/id.
    
    - If .meridian/id exists, read and return it
    - If not, generate UUID v4, create .meridian/ and id file atomically, return UUID
    - UUID is 36 chars, no trailing newline
    """

def get_project_state_root(project_uuid: str) -> Path:
    """Return the user-level project state directory.
    
    Returns: get_user_state_root() / "projects" / project_uuid
    """
```

### 2. Update `src/meridian/lib/state/paths.py`

Current state has `StateRootPaths` used for both repo and runtime state. Split it:

**Keep for repo-level artifacts:**
- `StatePaths.root_dir` → `.meridian/`
- Add `StatePaths.id_file` → `.meridian/id`
- `fs_dir`, `work_dir`, `work_archive_dir` stay as repo-level paths

**`StateRootPaths` becomes user-level runtime state:**
- All spawn/session paths under `~/.meridian/projects/<UUID>/`
- `spawns_jsonl`, `sessions_jsonl`, `spawns_dir` etc.

**Update resolve_state_paths():**
- For now, don't change the return value semantics — Phase 3 will migrate callers
- Add new helper `resolve_repo_state_paths()` that returns repo-level StatePaths only

### 3. Update `src/meridian/lib/ops/runtime.py`

Add new helper functions that Phase 3 callers will use:

```python
def get_project_uuid(repo_root: Path) -> str:
    """Get/create project UUID, returns UUID string."""
    
def resolve_user_state_root(repo_root: Path) -> Path:
    """Resolve user-level state root for a project.
    
    If MERIDIAN_STATE_ROOT is set, return that (explicit override).
    Otherwise: get UUID, return get_project_state_root(uuid).
    """
```

### 4. Update `.meridian/.gitignore`

Add `id` to the gitignore content (the UUID file should be ignored by default):
```
# Ignore the project UUID
id
```

## Implementation Notes

- Use `atomic_write_text()` from `meridian.lib.state.atomic` for UUID file creation
- UUID format: standard 36-char UUID v4, e.g. `f47ac10b-58cc-4372-a567-0e02b2c3d479`
- No trailing newline in the id file
- Create parent directories as needed with `mkdir(parents=True, exist_ok=True)`
- On Windows, handle `%LOCALAPPDATA%` and `%USERPROFILE%` env vars

## Testing Requirements

After implementation:
- `uv run ruff check .` must pass
- `uv run pyright` must pass
- Don't break existing tests

## Exit When Done

When implementation is complete, report what was built and verify linting passes.
