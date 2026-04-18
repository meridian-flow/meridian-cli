# Simplified UUID-Based State Layout — Planning Prompt

## Goal

Implement the simplified workspace-config design with UUID-based project identity.
This replaces the complex workspace config model with a deliberately simple approach.

## What We're Building

### 1. Project UUID (`get_or_create_project_uuid`)
- Generate UUID v4 on first write to `.meridian/`
- Store in `.meridian/id` as plain text (36 chars, no newline)
- Lazy creation — only when state is first written

### 2. User State Root (`get_user_state_root`)
- Unix/macOS: `~/.meridian/`
- Windows: `%LOCALAPPDATA%\meridian\` (fallback: `%USERPROFILE%\AppData\Local\meridian\`)
- Environment override: `MERIDIAN_HOME`

### 3. State Layout Migration
```
OLD (repo-level):
project/.meridian/
├── spawns.jsonl
├── sessions.jsonl
└── spawns/<spawn-id>/

NEW (split):
project/.meridian/
├── id                    # Project UUID (new)
├── work/                 # Committed (unchanged)
├── fs/                   # Committed (unchanged)
└── .gitignore            # Updated

~/.meridian/
└── projects/
    └── <UUID>/
        ├── spawns.jsonl
        ├── sessions.jsonl
        └── spawns/<spawn-id>/
```

### 4. Path Resolution API Changes

**New module: `src/meridian/lib/state/user_paths.py`**
```python
def get_user_state_root() -> Path:
    """Return user-level state root (~/.meridian/ or platform equivalent)."""

def get_or_create_project_uuid(meridian_dir: Path) -> str:
    """Read or generate project UUID from .meridian/id."""

def get_project_state_root(uuid: str) -> Path:
    """Return user-level project state directory."""
```

**Updates to `src/meridian/lib/state/paths.py`**
- Add `id_file` property for `.meridian/id`
- Keep `StateRootPaths` for user-level state (now under `~/.meridian/projects/<UUID>/`)
- Keep `StatePaths` for repo-level committed artifacts

**Updates to `src/meridian/lib/ops/runtime.py`**
- `resolve_state_root()` returns user-level state root, not repo-level
- Lazy UUID generation on first state access

## Design Documents

Read before planning:
- `$MERIDIAN_WORK_DIR/simplified-requirements.md` — core model
- `$MERIDIAN_WORK_DIR/design/architecture/runtime-home.md` — full architecture
- `$MERIDIAN_WORK_DIR/design/architecture/paths-layer.md` — module ownership

## Constraints

1. **No backwards compatibility** — old `.meridian/spawns.jsonl` becomes orphaned
2. **No migration path** — fresh runs use new layout
3. **Must not break** — CLI flags, env vars, config precedence unchanged
4. **Lazy init** — don't create `.meridian/id` until first state write
5. **MERIDIAN_STATE_ROOT override** — should still work for explicit state root override

## Key Files to Understand

- `src/meridian/lib/state/paths.py` — current path resolution
- `src/meridian/lib/ops/runtime.py` — `resolve_state_root()` consumers
- `src/meridian/lib/state/spawn_store.py` — spawn state consumers
- `src/meridian/lib/state/session_store.py` — session state consumers
- `src/meridian/lib/core/context.py` — `RuntimeContext` env vars

## Verification Criteria

1. `uv run pyright` clean
2. `uv run ruff check .` clean
3. `uv run pytest-llm` passes
4. Smoke test: spawn creates state under `~/.meridian/projects/<UUID>/`
5. Smoke test: moving project folder preserves UUID, finds existing state
6. Smoke test: `MERIDIAN_HOME` override works
7. Windows: `%LOCALAPPDATA%\meridian\` path construction (can verify logic, not necessarily on actual Windows)

## What This Replaces

This supersedes the complex workspace config plan (phases 2-3 in existing plan).
Phase 1 (config surface convergence) remains valid if already complete.
