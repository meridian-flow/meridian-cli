# Phase 1: CLI Changes

## Scope

Update `meridian context` and `meridian work current` to return expanded paths instead of work_id. Add CLI alias consistency.

## Files to Modify

### 1. src/meridian/lib/ops/context.py

**ContextOutput schema (lines 23-41):**
```python
class ContextOutput(BaseModel):
    """Output for context query operation."""

    model_config = ConfigDict(frozen=True)

    work_dir: str | None = None  # Changed from work_id
    fs_dir: str                   # NEW - always present
    repo_root: str
    state_root: str
    depth: int
    context_roots: list[str] = []  # NEW - from workspace.local.toml

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        lines: list[str] = []
        lines.append(f"work_dir: {self.work_dir or '(none)'}")
        lines.append(f"fs_dir: {self.fs_dir}")
        lines.append(f"repo_root: {self.repo_root}")
        lines.append(f"state_root: {self.state_root}")
        lines.append(f"depth: {self.depth}")
        if self.context_roots:
            lines.append(f"context_roots: {', '.join(self.context_roots)}")
        return "\n".join(lines)
```

**WorkCurrentOutput schema (lines 49-58):**
```python
class WorkCurrentOutput(BaseModel):
    """Output for work current operation."""

    model_config = ConfigDict(frozen=True)

    work_dir: str | None = None  # Changed from work_id - now expanded path

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        return self.work_dir or ""
```

**context_sync() function (lines 69-91):**
- Import `resolve_fs_dir` from `meridian.lib.state.paths`
- Import `resolve_work_scratch_dir` from `meridian.lib.state.paths`
- Import `resolve_workspace_snapshot, get_projectable_roots` from `meridian.lib.config.workspace`
- Compute `work_dir` by calling `resolve_work_scratch_dir(state_root, work_id)` if work_id exists
- Compute `fs_dir` by calling `resolve_fs_dir(repo_root)`
- Compute `context_roots` by calling `get_projectable_roots(resolve_workspace_snapshot(repo_root))` and converting to posix strings

**work_current_sync() function (lines 100-110):**
- Return expanded `work_dir` path instead of `work_id`
- Use `resolve_work_scratch_dir(state_root, work_id)` if work_id exists

### 2. src/meridian/lib/ops/manifest.py

**Line 656:** Change description from:
```python
description="Query runtime context: work_id, repo_root, state_root, depth.",
```
to:
```python
description="Query runtime context: work_dir, fs_dir, repo_root, state_root, depth, context_roots.",
```

**Line 668:** Change description from:
```python
description="Return just the current work_id (or empty if none attached).",
```
to:
```python
description="Return the current work directory path (or empty if none attached).",
```

### 3. src/meridian/cli/main.py

**Line 1256:** Change docstring from:
```python
"""Query runtime context: work_id, repo_root, state_root, depth."""
```
to:
```python
"""Query runtime context: work_dir, fs_dir, repo_root, state_root, depth, context_roots."""
```

### 4. src/meridian/cli/work_cmd.py

**Lines 62-65:** Add `--desc` alias:
```python
    description: Annotated[
        str,
        Parameter(name=["--description", "--desc"], help="Optional work item description."),
    ] = "",
```

### 5. src/meridian/cli/spawn.py

**Lines 193-196:** Add `--description` alias:
```python
    desc: Annotated[
        str,
        Parameter(name=["--desc", "--description"], help="Short description for the spawn."),
    ] = "",
```

### 6. Check work update

Check if `_work_update()` has a description parameter and add aliases if needed.

## Exit Criteria

- `meridian context` returns JSON with `work_dir`, `fs_dir`, `context_roots` (no `work_id`)
- `meridian work current` returns expanded path (not work_id)
- `--desc` and `--description` work on `spawn`, `work start`, and `work update`
- Tests pass (pyright, ruff, pytest)
