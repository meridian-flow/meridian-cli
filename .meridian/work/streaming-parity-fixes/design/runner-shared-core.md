# Runner Shared Core

## Purpose

Define the shared launch-context assembly used by both subprocess and streaming runners so policy cannot drift across transports.

## Scope

In scope:

- Shared constants in `launch/constants.py`
- Shared launch context builder in `launch/context.py`
- Adapter-owned preflight via `adapter.preflight(...)`
- Shared env-build path

Out of scope:

- Full runner decomposition. v2 keeps orchestrator logic in `runner.py` and `streaming_runner.py`.

## Target Shape

### Module Layout

- `src/meridian/lib/launch/context.py` — `LaunchContext`, `prepare_launch_context(...)`
- `src/meridian/lib/launch/constants.py` — shared constants
- `src/meridian/lib/launch/text_utils.py` — shared text helpers (`dedupe_nonempty`, `split_csv_entries`) consumed by launch/preflight and projection code paths
- `src/meridian/lib/harness/bundle.py` — typed harness registry (`HarnessBundle`, `get_harness_bundle`)
- `src/meridian/lib/harness/claude_preflight.py` — Claude-only preflight helpers used by `ClaudeAdapter.preflight`

`launch/text_utils.py` is the single home for launch-related string normalization used across harness boundaries (CSV-ish passthrough parsing and stable dedupe behavior) so runner/preflight/projection logic does not reimplement subtly different parsing.

### LaunchContext

```python
@dataclass(frozen=True)
class LaunchContext:
    run_params: SpawnParams
    perms: PermissionResolver
    spec: ResolvedLaunchSpec
    child_cwd: Path
    env: dict[str, str]
    env_overrides: dict[str, str]
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
    )

    spec = adapter.resolve_launch_spec(run_params, perms)

    runtime_overrides = {
        "MERIDIAN_REPO_ROOT": execution_cwd.as_posix(),
        "MERIDIAN_STATE_ROOT": resolve_state_paths(repo_root).root_dir.resolve().as_posix(),
    }
    merged_overrides = dict(plan.env_overrides)
    merged_overrides.update(runtime_overrides)
    merged_overrides.update(preflight.extra_env)

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
        env=env,
        env_overrides=merged_overrides,
        report_output_path=report_output_path,
    )
```

The shared core does not branch on `harness_id` for harness-specific logic. Harness-specific preflight lives behind `adapter.preflight(...)`.

## Parity Contract

- Both runners call `prepare_launch_context(...)` once.
- For identical inputs, `LaunchContext` is equal across callers.
- Permission config is read via `ctx.perms.config` (no duplicated `LaunchContext.permission_config` field).
- Dispatch cast/typing enforcement lives in `SpawnManager.start_spawn` (see [typed-harness.md](typed-harness.md)); `prepare_launch_context` does not perform connection dispatch.

## Interaction with Other Docs

- [typed-harness.md](typed-harness.md): adapter preflight contract and dispatch boundary.
- [launch-spec.md](launch-spec.md): factory mapping and `SpawnParams` accounting.
- [transport-projections.md](transport-projections.md): wire projection and reserved-flag policy.
