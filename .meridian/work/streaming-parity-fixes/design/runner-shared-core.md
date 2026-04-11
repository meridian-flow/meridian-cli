# Runner Shared Core

## Purpose

Define the shared launch-context assembly used by both subprocess and streaming runners so policy cannot drift across transports.

Revision round 3 changes:

- K5: codify `RuntimeContext.child_context()` as the sole producer of `MERIDIAN_*` runtime overrides. `preflight.extra_env` **and** `plan_overrides` MUST NOT contain any `MERIDIAN_*` key; both inputs are scanned in `merge_env_overrides(...)` and violations raise `RuntimeError`. The child context is restricted to a whitelisted set `_ALLOWED_MERIDIAN_KEYS = frozenset({"MERIDIAN_REPO_ROOT", "MERIDIAN_STATE_ROOT", "MERIDIAN_DEPTH", "MERIDIAN_CHAT_ID", "MERIDIAN_FS_DIR", "MERIDIAN_WORK_DIR"})` so `fs_dir` and `work_dir` forwarding cannot be silently stripped by the guard.
- C1: narrow the `LaunchContext` parity claim to the deterministic subset. Ambient `os.environ` is not part of parity.

## Scope

In scope:

- Shared constants in `launch/constants.py`
- Shared launch context builder in `launch/context.py`
- Adapter-owned preflight via `adapter.preflight(...)`
- Shared env-build path with `MERIDIAN_*` sole-producer invariant

Out of scope:

- Full runner decomposition. v2 keeps orchestrator logic in `runner.py` and `streaming_runner.py`.

## Target Shape

### Module Layout

- `src/meridian/lib/launch/context.py` — `LaunchContext`, `RuntimeContext`, `prepare_launch_context(...)`
- `src/meridian/lib/launch/constants.py` — shared constants including `MERIDIAN_ENV_KEYS`
- `src/meridian/lib/launch/text_utils.py` — shared text helpers (`dedupe_nonempty`, `split_csv_entries`) consumed by launch/preflight and projection code paths
- `src/meridian/lib/harness/bundle.py` — typed harness registry (`HarnessBundle`, `register_harness_bundle`, `get_harness_bundle`, `get_connection_cls`)
- `src/meridian/lib/harness/claude_preflight.py` — Claude-only preflight helpers used by `ClaudeAdapter.preflight`

`launch/text_utils.py` is the single home for launch-related string normalization used across harness boundaries.

### `RuntimeContext` (K5 sole producer)

```python
# src/meridian/lib/launch/context.py
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

# The whitelisted MERIDIAN_* key set. Only RuntimeContext.child_context()
# may emit these keys; merge_env_overrides() rejects MERIDIAN_* keys from
# every other source (plan and preflight).
_ALLOWED_MERIDIAN_KEYS: frozenset[str] = frozenset({
    "MERIDIAN_REPO_ROOT",
    "MERIDIAN_STATE_ROOT",
    "MERIDIAN_DEPTH",
    "MERIDIAN_CHAT_ID",
    "MERIDIAN_FS_DIR",
    "MERIDIAN_WORK_DIR",
})


@dataclass(frozen=True)
class RuntimeContext:
    """Sole producer of MERIDIAN_* runtime environment overrides (K5).

    Any code path that needs to set a MERIDIAN_* variable for a child
    spawn MUST go through `RuntimeContext.child_context(...)`. This
    includes parent chat id propagation, state root forwarding, depth
    incrementing, shared filesystem dir, and the work-item dir.

    Neither `plan.env_overrides` nor `preflight.extra_env` may contain
    any `MERIDIAN_*` key. `merge_env_overrides(...)` scans both inputs
    and raises `RuntimeError` on violation (defence in depth against a
    plan builder or a harness preflight accidentally leaking one).
    """

    repo_root: Path
    state_root: Path
    parent_chat_id: str | None
    parent_depth: int
    fs_dir: Path | None
    work_dir: Path | None

    def child_context(self) -> dict[str, str]:
        overrides: dict[str, str] = {
            "MERIDIAN_REPO_ROOT": self.repo_root.as_posix(),
            "MERIDIAN_STATE_ROOT": self.state_root.as_posix(),
            "MERIDIAN_DEPTH": str(self.parent_depth + 1),
        }
        if self.parent_chat_id is not None:
            overrides["MERIDIAN_CHAT_ID"] = self.parent_chat_id
        if self.fs_dir is not None:
            overrides["MERIDIAN_FS_DIR"] = self.fs_dir.as_posix()
        if self.work_dir is not None:
            overrides["MERIDIAN_WORK_DIR"] = self.work_dir.as_posix()
        # Invariant: every emitted key is in the whitelist. If this fails
        # it's a drift between the class body and _ALLOWED_MERIDIAN_KEYS.
        assert set(overrides).issubset(_ALLOWED_MERIDIAN_KEYS), (
            f"RuntimeContext.child_context drift: "
            f"{sorted(set(overrides) - _ALLOWED_MERIDIAN_KEYS)}"
        )
        return overrides
```

### Merge Helper with Invariant Enforcement

```python
def merge_env_overrides(
    *,
    plan_overrides: Mapping[str, str],
    runtime_overrides: Mapping[str, str],
    preflight_overrides: Mapping[str, str],
) -> dict[str, str]:
    """Merge environment overrides in precedence order.

    Invariant (K5): neither `plan_overrides` nor `preflight_overrides`
    may contain any `MERIDIAN_*` key. The MERIDIAN namespace is owned
    exclusively by `RuntimeContext.child_context()`. Both inputs are
    scanned up-front and a single `RuntimeError` is raised listing
    every offending key with its source.

    Precedence (later wins): plan < preflight (harness-specific) < runtime.
    This ordering ensures that MERIDIAN_* from runtime always takes the
    final word, but the point is moot — the invariant check above means
    neither plan nor preflight can produce a MERIDIAN_* key in the first
    place.
    """
    forbidden: dict[str, str] = {}  # key -> source
    for key in plan_overrides:
        if key.startswith("MERIDIAN_"):
            forbidden[key] = "plan_overrides"
    for key in preflight_overrides:
        if key.startswith("MERIDIAN_"):
            forbidden[key] = "preflight_overrides"
    if forbidden:
        raise RuntimeError(
            "MERIDIAN_* keys may only be set by RuntimeContext.child_context(); "
            f"found leaks: {sorted(forbidden.items())}"
        )
    merged = dict(plan_overrides)
    merged.update(preflight_overrides)
    merged.update(runtime_overrides)
    return merged
```

S046 exercises this invariant with a fixture adapter whose `preflight` returns `{"MERIDIAN_DEPTH": "42"}` and asserts the merge raises. **S046b** (convergence pass) exercises the plan-side leak with `plan_overrides={"MERIDIAN_CHAT_ID": "spoofed"}` and asserts the merge also raises.

### LaunchContext

```python
@dataclass(frozen=True)
class LaunchContext:
    run_params: SpawnParams
    perms: PermissionResolver
    spec: ResolvedLaunchSpec
    child_cwd: Path
    env: Mapping[str, str]         # MappingProxyType wrapping resolved env
    env_overrides: Mapping[str, str]  # MappingProxyType
    report_output_path: Path
```

### `prepare_launch_context(...)`

```python
def prepare_launch_context(
    *,
    plan: PreparedSpawnPlan,
    execution_cwd: Path,
    state_root: Path,
    repo_root: Path,
    passthrough_args: tuple[str, ...],
    report_output_path: Path,
    harness_id: HarnessId,
) -> LaunchContext:
    # Registry provides adapter/spec/connection pairing by harness_id.
    bundle = get_harness_bundle(harness_id)
    adapter = bundle.adapter
    perms = plan.execution.permission_resolver

    child_cwd = resolve_child_execution_cwd(
        repo_root=execution_cwd,
        spawn_id=plan.spawn_id,
        harness_id=harness_id.value,
    )
    child_cwd.mkdir(parents=True, exist_ok=True)

    preflight = adapter.preflight(
        execution_cwd=execution_cwd,
        child_cwd=child_cwd,
        passthrough_args=passthrough_args,
    )

    run_params = SpawnParams(
        prompt=plan.prompt,
        model=plan.model,
        effort=plan.effort,
        skills=plan.skills,
        agent=plan.agent_name,
        adhoc_agent_payload=plan.adhoc_agent_payload,
        extra_args=preflight.expanded_passthrough_args,
        repo_root=child_cwd.as_posix(),
        continue_harness_session_id=plan.session.harness_session_id,
        continue_fork=plan.session.continue_fork,
        report_output_path=report_output_path.as_posix(),
        appended_system_prompt=plan.appended_system_prompt,
        interactive=plan.interactive,
        mcp_tools=plan.mcp_tools,
    )

    spec = adapter.resolve_launch_spec(run_params, perms)

    runtime_ctx = RuntimeContext(
        repo_root=execution_cwd,
        state_root=resolve_state_paths(repo_root).root_dir.resolve(),
        parent_chat_id=plan.parent_chat_id,
        parent_depth=plan.parent_depth,
        fs_dir=plan.fs_dir,
        work_dir=plan.work_dir,
    )
    merged_overrides = merge_env_overrides(
        plan_overrides=plan.env_overrides,
        runtime_overrides=runtime_ctx.child_context(),
        preflight_overrides=preflight.extra_env,
    )

    env = build_harness_child_env(
        base_env=os.environ,
        adapter=adapter,
        run_params=run_params,
        permission_config=perms.config,
        runtime_env_overrides=merged_overrides,
    )

    return LaunchContext(
        run_params=run_params,
        perms=perms,
        spec=spec,
        child_cwd=child_cwd,
        env=MappingProxyType(env),
        env_overrides=MappingProxyType(merged_overrides),
        report_output_path=report_output_path,
    )
```

The shared core does not branch on `harness_id` for harness-specific logic. Harness-specific preflight lives behind `adapter.preflight(...)`.

## Parity Contract (C1: narrowed)

- Both runners call `prepare_launch_context(...)` once.
- Permission config is read via `ctx.perms.config` (no duplicated `LaunchContext.permission_config` field).
- Dispatch cast/typing enforcement lives in `SpawnManager.start_spawn` (see [typed-harness.md](typed-harness.md)); `prepare_launch_context` does not perform connection dispatch.

### Deterministic parity subset (C1)

The parity claim is explicitly about the **deterministic subset** of `LaunchContext`:

- `run_params` — pure function of inputs
- `spec` — pure function of `(run_params, permission_config, adapter)`
- `child_cwd` — pure function of `(execution_cwd, spawn_id, harness_id)`
- `env_overrides` — the merged override mapping (plan + preflight + runtime), deterministic
- `MERIDIAN_*` keys inside `env_overrides` — produced solely by `RuntimeContext.child_context()`

The `env` field as a whole is **NOT** in the parity contract because it depends on ambient `os.environ`, which differs between runners, CI hosts, and developer machines. Only the override subset is testable for parity.

S024 is updated to assert parity on the deterministic subset only. The delta test verifying `env_overrides` parity runs in CI; an ambient-environ test would be flaky by design.

## Interaction with Other Docs

- [typed-harness.md](typed-harness.md): adapter preflight contract, dispatch boundary, cancel/interrupt semantics.
- [launch-spec.md](launch-spec.md): factory mapping, `SpawnParams` accounting, per-adapter `handled_fields`.
- [transport-projections.md](transport-projections.md): wire projection, verbatim `extra_args`, `mcp_tools` mapping.
- [permission-pipeline.md](permission-pipeline.md): non-optional resolver, frozen config, harness-agnostic `resolve_flags`.
