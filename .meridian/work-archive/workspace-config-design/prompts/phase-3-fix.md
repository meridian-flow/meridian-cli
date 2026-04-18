# Fix: Bootstrap Creates Repo-Level Runtime Directories

## Problem

The smoke test revealed that `ensure_runtime_state_bootstrap_sync()` in `src/meridian/lib/ops/config.py` creates `artifacts/`, `cache/`, and `spawns/` directories at repo-level `.meridian/` when they should be at user-level `~/.meridian/projects/<UUID>/`.

## Root Cause

```python
def ensure_runtime_state_bootstrap_sync(repo_root: Path) -> None:
    state = resolve_state_paths(repo_root)  # Returns repo-level paths
    bootstrap_dirs = (
        state.root_dir,
        state.artifacts_dir,    # Creates at repo-level, WRONG
        state.cache_dir,        # Creates at repo-level, WRONG
        state.spawns_dir,       # Creates at repo-level, WRONG
        state.root_dir / "fs",
        state.root_dir / "work",
        ...
    )
```

## Fix Required

In `src/meridian/lib/ops/config.py`, update `ensure_runtime_state_bootstrap_sync()`:

```python
def ensure_runtime_state_bootstrap_sync(repo_root: Path) -> None:
    """Ensure first-run runtime state exists without creating project-root files."""
    
    # Repo-level directories (fs, work, work-archive, work-items)
    repo_state = resolve_repo_state_paths(repo_root)
    repo_dirs = (
        repo_state.root_dir,  # .meridian/
        repo_state.fs_dir,
        repo_state.work_dir,
        repo_state.work_archive_dir,
    )
    for dir_path in repo_dirs:
        dir_path.mkdir(parents=True, exist_ok=True)
    
    # Runtime-level directories (artifacts, cache, spawns)
    from meridian.lib.state.paths import resolve_runtime_state_root, StateRootPaths
    runtime_root = resolve_runtime_state_root(repo_root)
    runtime_state = StateRootPaths.from_root_dir(runtime_root)
    runtime_dirs = (
        runtime_state.root_dir,
        runtime_state.spawns_dir,
        # artifacts and cache will be created on-demand
    )
    for dir_path in runtime_dirs:
        dir_path.mkdir(parents=True, exist_ok=True)
    
    ensure_gitignore(repo_root)
```

Also verify:
1. `StatePaths` shouldn't have `artifacts_dir`, `cache_dir`, `spawns_dir` - those are runtime, not repo-level
2. Or rename the existing usage to clearly separate repo vs runtime paths

## DO NOT TOUCH

These files are being modified by parallel work:
- `src/meridian/lib/state/atomic.py`
- `src/meridian/lib/launch/signals.py`
- `src/meridian/lib/launch/runner_helpers.py`

## Verification

After fixing:
- `uv run pyright` must pass
- `uv run ruff check .` on touched files must pass
- `uv run pytest-llm tests/` should pass
