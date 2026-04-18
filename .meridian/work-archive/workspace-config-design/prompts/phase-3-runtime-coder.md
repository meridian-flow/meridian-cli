# Phase 3 Coder Prompt: Runtime Consumers and Smoke

## Task

Migrate all runtime callers from `resolve_state_root()` to use the new user-level state root via `resolve_user_state_root()`. After this phase, spawn and session state will land under `~/.meridian/projects/<UUID>/` by default.

## IMPORTANT: Parallel Work Warning

**DO NOT modify these files** — they're being changed by parallel spawn p2206:
- `src/meridian/lib/state/atomic.py`
- `src/meridian/lib/launch/signals.py`
- `src/meridian/lib/launch/runner_helpers.py`

## What to Change

### 1. Update `resolve_state_root()` in `runtime.py`

Change `resolve_state_root()` to use the new user-level state root:

```python
def resolve_state_root(repo_root: Path) -> Path:
    """Resolve the Meridian state root for a repository.
    
    Returns user-level state root for runtime state (spawns, sessions).
    """
    return resolve_user_state_root(repo_root)
```

This single change propagates to all existing callers automatically.

### 2. Update `resolve_roots()` in `runtime.py`

```python
def resolve_roots(repo_root: str | None) -> ResolvedRoots:
    resolved_repo_root, _ = resolve_runtime_root_and_config(repo_root)
    return ResolvedRoots(
        repo_root=resolved_repo_root,
        state_root=resolve_state_root(resolved_repo_root),  # Now returns user-level
    )
```

### 3. Verify Work/FS Dir Paths Stay Repo-Scoped

`MERIDIAN_WORK_DIR` and `MERIDIAN_FS_DIR` must continue pointing to repo-level `.meridian/`:

In `src/meridian/lib/core/context.py`, the `to_env_overrides()` method should derive work_dir from repo-level paths (check if it uses `state_root` and fix if needed).

In `src/meridian/lib/launch/env.py`, verify that `MERIDIAN_FS_DIR` is derived from the repo `.meridian/fs`, not the user state root.

### 4. Files That Need Review/Update

Check each file that calls `resolve_state_root()` and verify it should use user-level state:

**Should use user-level state (spawns, sessions, cache):**
- `src/meridian/cli/spawn.py`
- `src/meridian/cli/app_cmd.py`
- `src/meridian/cli/streaming_serve.py`
- `src/meridian/lib/ops/spawn/*.py`
- `src/meridian/lib/ops/session_log.py`
- `src/meridian/lib/ops/session_search.py`
- `src/meridian/lib/ops/diag.py`
- `src/meridian/lib/ops/report.py`
- `src/meridian/lib/launch/*.py`
- `src/meridian/lib/streaming/*.py`
- `src/meridian/lib/app/*.py`

**Should stay repo-level (work, fs, config):**
- Work items in `src/meridian/lib/ops/work_*.py` → use `resolve_repo_state_paths()`
- FS dir resolution → use `resolve_repo_state_paths().fs_dir`

### 5. Update StateRootPaths Usage

Where `StateRootPaths.from_root_dir(state_root)` is used for spawn/session operations, it should now receive the user-level state root.

Where it's used for work items or fs operations, those should be updated to use repo-level paths.

### 6. Context.py Work Dir Fix

In `context.py`, `to_env_overrides()` derives `MERIDIAN_WORK_DIR` from `self.state_root`:

```python
if self.work_id:
    overrides["MERIDIAN_WORK_ID"] = self.work_id
    if self.state_root is not None:
        overrides["MERIDIAN_WORK_DIR"] = resolve_work_scratch_dir(
            self.state_root,
            self.work_id,
        ).as_posix()
```

This needs to use the repo-level `.meridian/work/<work_id>`, not the user-level state root. Fix this to derive from `repo_root` directly.

## Key Invariants

1. `spawns.jsonl`, `sessions.jsonl`, and `spawns/<spawn-id>/` go to user-level state
2. `work/`, `fs/`, and project config stay in repo `.meridian/`
3. `MERIDIAN_STATE_ROOT` override bypasses UUID resolution (explicit override wins)
4. `MERIDIAN_FS_DIR` and `MERIDIAN_WORK_DIR` remain repo-scoped

## Testing Requirements

After implementation:
- `uv run pyright` must pass
- `uv run ruff check .` on touched files must pass
- `uv run pytest-llm tests/` should pass (may need test updates)

## Exit When Done

Report what was changed and verification results.
