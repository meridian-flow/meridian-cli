# Phase 3: Domain Core — Factory, LaunchContext Sum Type, Pipeline Stages, LaunchResult/LaunchOutcome, observe_session_id

This is the central phase of R06. You are building the hexagonal domain core: one factory (`build_launch_context()`), one `LaunchContext` sum type, pipeline stages, result types, and the `observe_session_id()` adapter seam.

**This phase creates the infrastructure. Phases 4-6 will rewire driving adapters to use it. This phase does NOT change any calling code in plan.py, prepare.py, or server.py.**

## 1. LaunchContext sum type

Replace the current `LaunchContext` dataclass at `src/meridian/lib/launch/context.py:122-131` with a sum type:

```python
@dataclass(frozen=True)
class NormalLaunchContext:
    """Complete resolved launch context for one harness run."""
    run_params: SpawnParams
    perms: PermissionResolver
    spec: ResolvedLaunchSpec
    child_cwd: Path
    env: Mapping[str, str]
    env_overrides: Mapping[str, str]
    report_output_path: Path
    # Note: session_id is NOT here — it's on LaunchResult

@dataclass(frozen=True)
class BypassLaunchContext:
    """Launch context for MERIDIAN_HARNESS_COMMAND bypass."""
    argv: tuple[str, ...]
    env: Mapping[str, str]
    cwd: Path

# Union type
LaunchContext = NormalLaunchContext | BypassLaunchContext
```

Keep the old `LaunchContext` name as a type alias for the union so existing imports don't break yet. The old `LaunchContext` class has fields matching `NormalLaunchContext` — rename the class to `NormalLaunchContext` and add `LaunchContext = NormalLaunchContext | BypassLaunchContext`.

## 2. LaunchResult and LaunchOutcome types

Add to `src/meridian/lib/launch/context.py` (or a new `src/meridian/lib/launch/result.py`):

```python
@dataclass(frozen=True)
class LaunchOutcome:
    """Raw executor output before adapter post-processing."""
    exit_code: int
    child_pid: int | None = None
    captured_stdout: bytes | None = None  # PTY-captured output, if any

@dataclass(frozen=True)
class LaunchResult:
    """Post-processed launch result returned to driving adapters."""
    exit_code: int
    child_pid: int | None = None
    session_id: str | None = None  # populated by adapter.observe_session_id()
```

## 3. observe_session_id() adapter seam

Add to `src/meridian/lib/harness/adapter.py`:

On the `SubprocessHarness` protocol:
```python
def observe_session_id(
    self,
    *,
    launch_context: NormalLaunchContext,
    launch_outcome: LaunchOutcome,
) -> str | None: ...
```

On `BaseHarnessAdapter` (default impl returns None):
```python
def observe_session_id(
    self,
    *,
    launch_context: NormalLaunchContext,
    launch_outcome: LaunchOutcome,
) -> str | None:
    _ = launch_context, launch_outcome
    return None
```

Import `NormalLaunchContext` and `LaunchOutcome` from `meridian.lib.launch.context`. Watch for circular imports — if adapter.py importing from launch/context.py creates a cycle (since context.py already imports from adapter.py), use `TYPE_CHECKING` guards.

## 4. Pipeline stages (new files)

Create pipeline stage files. These are **stubs for now** — they define the function signatures and contain the core logic extracted from existing code. The actual driving-adapter rewiring happens in phases 4-6.

### `src/meridian/lib/launch/policies.py`
Extract `resolve_policies()` from `src/meridian/lib/launch/resolve.py`. The function already exists there — just re-export it or move it. For now, create a thin wrapper that re-exports:
```python
"""Policy resolution pipeline stage."""
from .resolve import resolve_policies, ResolvedPolicies

__all__ = ["resolve_policies", "ResolvedPolicies"]
```

### `src/meridian/lib/launch/permissions.py`
Create wrapper that re-exports from safety:
```python
"""Permission pipeline stage."""
from meridian.lib.safety.permissions import resolve_permission_pipeline

__all__ = ["resolve_permission_pipeline"]
```

### `src/meridian/lib/launch/fork.py`
Create the `materialize_fork()` function by extracting the common fork logic from:
- `src/meridian/lib/launch/process.py:68-105` (`_resolve_command_and_session`)  
- `src/meridian/lib/ops/spawn/prepare.py:296-311`

```python
"""Fork materialization pipeline stage."""

from meridian.lib.core.types import HarnessId
from meridian.lib.harness.adapter import SpawnParams, SubprocessHarness

def materialize_fork(
    *,
    adapter: SubprocessHarness,
    run_params: SpawnParams,
    dry_run: bool = False,
) -> SpawnParams:
    """Materialize a fork if conditions are met, returning updated params."""
    should_fork = (
        run_params.continue_fork
        and not dry_run
        and adapter.id == HarnessId.CODEX
        and bool((run_params.continue_harness_session_id or "").strip())
    )
    if not should_fork:
        return run_params

    source_session_id = run_params.continue_harness_session_id or ""
    forked_session_id = adapter.fork_session(source_session_id).strip()
    if not forked_session_id:
        raise RuntimeError("Harness adapter returned empty fork session ID.")

    return run_params.model_copy(
        update={
            "continue_harness_session_id": forked_session_id,
            "continue_fork": False,
        }
    )
```

### `src/meridian/lib/launch/env.py` already exists
`build_env_plan()` is not a separate function yet. For now, keep the existing `build_harness_child_env` and `merge_env_overrides` in env.py. Phase 3 doesn't need to rename them — the factory in phase 4+ will call them.

## 5. build_launch_context() factory

Add the factory function to `src/meridian/lib/launch/context.py`. This is the **canonical** composition entry point. For now, it wraps the existing `prepare_launch_context()` logic:

```python
def build_launch_context(
    *,
    spawn_id: str,
    run_prompt: str,
    run_model: str | None,
    plan: PreparedSpawnPlan,
    harness: SubprocessHarness,
    execution_cwd: Path,
    state_root: Path,
    plan_overrides: Mapping[str, str],
    report_output_path: Path,
    runtime_work_id: str | None = None,
) -> NormalLaunchContext:
    """Build deterministic launch context for one runner attempt.

    This is the canonical entry point for launch composition.
    All driving adapters must call this factory.
    """
    # For now, delegate to the existing prepare_launch_context logic
    # Phases 4-6 will expand this to handle all driving adapter cases
    return prepare_launch_context(
        spawn_id=spawn_id,
        run_prompt=run_prompt,
        run_model=run_model,
        plan=plan,
        harness=harness,
        execution_cwd=execution_cwd,
        state_root=state_root,
        plan_overrides=plan_overrides,
        report_output_path=report_output_path,
        runtime_work_id=runtime_work_id,
    )
```

Keep `prepare_launch_context()` for now — it still works and callers still use it. The factory delegates to it. Phases 4-6 will fold the logic directly into the factory and remove `prepare_launch_context()`.

## 6. Update __all__ exports

In `src/meridian/lib/launch/context.py`, update `__all__` to include:
- `NormalLaunchContext`
- `BypassLaunchContext`  
- `LaunchContext` (the union alias)
- `LaunchOutcome`
- `LaunchResult`
- `build_launch_context`
- `prepare_launch_context` (keep for now)
- `merge_env_overrides`
- `RuntimeContext` (re-exported from core)

## Key constraints

- **Do NOT change any callers** — plan.py, prepare.py, server.py, process.py, streaming_runner.py all keep their current code. Phases 4-6 handle those.
- **Do NOT delete anything** — just add new types, new files, new functions
- Keep `prepare_launch_context()` working — it's still called by existing code
- The old `LaunchContext` class becomes `NormalLaunchContext`. Add `LaunchContext = NormalLaunchContext | BypassLaunchContext` so existing `LaunchContext` imports resolve to the union.
- Watch for circular imports between adapter.py and context.py — use TYPE_CHECKING if needed
- `observe_session_id()` on the adapter protocol needs `NormalLaunchContext` and `LaunchOutcome` — these may need TYPE_CHECKING imports

## Verification

```bash
uv run pyright        # Must be 0 errors
uv run ruff check .   # Must pass
uv run pytest-llm     # All 658 tests must pass (no behavioral change)
```

Check exit criteria:
```bash
rg "^class NormalLaunchContext\b" src/     # → 1 match
rg "^class BypassLaunchContext\b" src/     # → 1 match  
rg "^class LaunchResult\b" src/            # → 1 match
rg "^class LaunchOutcome\b" src/           # → 1 match
rg "observe_session_id\(" src/meridian/lib/harness/adapter.py  # → matches
rg "^def build_launch_context\(" src/      # → 1 match
rg "^def materialize_fork\(" src/          # → 1 match
```

Commit when done.
