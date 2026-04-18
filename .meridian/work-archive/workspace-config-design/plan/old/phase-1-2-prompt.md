# Phase 1+2: SpawnRequest Type + RuntimeContext Unification

You are implementing the first two phases of R06 (hexagonal launch core refactor). These are additive type changes with no behavioral changes.

## Phase 1: Add SpawnRequest DTO

### What to do

Add a `SpawnRequest` frozen Pydantic model alongside the existing `SpawnParams` in `src/meridian/lib/harness/adapter.py`. SpawnRequest represents user-facing launch arguments. SpawnParams continues to carry all its current fields unchanged — this is an additive change.

SpawnRequest fields (user-facing only):
```python
class SpawnRequest(BaseModel):
    """User-facing arguments for requesting a spawn."""
    model_config = ConfigDict(frozen=True)

    prompt: str
    model: ModelId | None = None
    effort: str | None = None
    skills: tuple[str, ...] = ()
    agent: str | None = None
    extra_args: tuple[str, ...] = ()
    interactive: bool = False
    mcp_tools: tuple[str, ...] = ()
```

This is a subset of SpawnParams's current fields. SpawnParams keeps ALL its fields unchanged (including the resolved-only ones like repo_root, continue_harness_session_id, continue_fork, report_output_path, appended_system_prompt, adhoc_agent_payload).

Add SpawnRequest to `__all__` exports where SpawnParams is exported.

### Exit criteria
- `rg "^class SpawnRequest\b" src/` → exactly 1 match
- `rg "^class SpawnParams\b" src/` → exactly 1 match (unchanged)
- No callers change in this phase — SpawnParams construction sites are unchanged
- pyright 0 errors, ruff clean, all tests pass

## Phase 2: Unify RuntimeContext

### What to do

There are currently TWO `RuntimeContext` types:
1. `src/meridian/lib/launch/context.py:42` — frozen dataclass, used for spawn child env production
2. `src/meridian/lib/core/context.py:13` — Pydantic BaseModel, used for reading current env state

Unify into ONE `RuntimeContext` at `src/meridian/lib/core/context.py`. The unified type must:
- Keep the Pydantic BaseModel approach (to stay consistent with the rest of the codebase)
- Merge fields from both types:
  - From core: spawn_id, depth, repo_root (optional), state_root (optional), chat_id, work_id
  - From launch: parent_chat_id → chat_id, parent_depth → depth, fs_dir, work_dir
- Keep `from_environment()` class method (from core, reads MERIDIAN_* env vars)
- Keep `to_env_overrides()` method (from core, for producing child env vars)  
- Keep `child_context()` method semantics from launch's version (producing child MERIDIAN_* overrides including depth+1 and fs/work dir)
- Keep `with_work_id()` from launch's version

After unification:
- `src/meridian/lib/launch/context.py` imports RuntimeContext from `meridian.lib.core.context` instead of defining its own
- All files that imported `RuntimeContext` from `launch/context.py` switch to importing from `core/context`
- `src/meridian/lib/launch/command.py` already imports from `core/context` — should still work
- The `_ALLOWED_MERIDIAN_KEYS` allowlist from launch/context.py's RuntimeContext.child_context moves to the unified type

**Finding all usages:**
```bash
rg "from meridian.lib.launch.context import.*RuntimeContext" src/
rg "from meridian.lib.core.context import.*RuntimeContext" src/
rg "RuntimeContext" src/ --type py
```

Update ALL imports to point at `meridian.lib.core.context`.

### Key files to modify
- `src/meridian/lib/core/context.py` — expand RuntimeContext to cover both use cases
- `src/meridian/lib/launch/context.py` — remove RuntimeContext definition, import from core
- `src/meridian/lib/launch/command.py` — already imports from core, verify still works
- Any other files importing RuntimeContext from launch/context.py

### Exit criteria
- `rg "^class RuntimeContext\b" src/` → exactly 1 match (in core/context.py)
- pyright 0 errors, ruff clean, all tests pass

## General instructions
- Run `uv run pyright` after changes to verify type safety
- Run `uv run ruff check .` for linting
- Run `uv run pytest-llm` for tests (use pytest-llm not pytest for token-efficient output)
- Do NOT change any behavioral code — these are type additions and import unification only
- Commit the changes with a descriptive message when done
