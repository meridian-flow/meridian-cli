# Phase 6: Shared Launch Context and Env Invariants

## Scope

Extract the deterministic shared launch core used by both runners and make `RuntimeContext.child_context()` the sole producer of `MERIDIAN_*` child-process overrides. This phase removes duplicated runner constants and centralizes adapter-owned preflight.

## Files to Modify

- `src/meridian/lib/launch/context.py` — new `LaunchContext`, `RuntimeContext`, `prepare_launch_context(...)`, and `merge_env_overrides(...)`
- `src/meridian/lib/launch/constants.py` — new shared runner constants and base-command tuples
- `src/meridian/lib/launch/text_utils.py` — shared text helpers consumed by preflight/projection code
- `src/meridian/lib/launch/env.py` — route environment assembly through the shared merge helper and reject leaked `MERIDIAN_*` keys
- `src/meridian/lib/launch/cwd.py` — keep child-CWD resolution centralized and referenced from the shared launch path
- `src/meridian/lib/harness/claude_preflight.py` — adapter-owned preflight returns `PreflightResult`
- `src/meridian/lib/launch/runner.py` and `src/meridian/lib/launch/streaming_runner.py` — consume `prepare_launch_context(...)` instead of assembling run/spec/env state locally
- `tests/test_launch_process.py`, `tests/exec/test_claude_cwd_isolation.py`, `tests/exec/test_streaming_runner.py`, `tests/exec/test_permissions.py` — parity and env-leak coverage

## Dependencies

- Requires: Phases 3-5
- Produces: shared launch context used by phases 7-8
- Independent of: final bundle bootstrap and lifecycle convergence

## Interface Contract

```python
def merge_env_overrides(
    *,
    plan_overrides: Mapping[str, str],
    runtime_overrides: Mapping[str, str],
    preflight_overrides: Mapping[str, str],
) -> dict[str, str]: ...

def prepare_launch_context(...) -> LaunchContext: ...
```

## Constraints

- No shared-core `if harness_id == ...` branches.
- Neither plan overrides nor preflight may inject any `MERIDIAN_*` key.
- The parity contract is limited to the deterministic subset: `run_params`, `spec`, `child_cwd`, `env_overrides`.

## Verification Criteria

- `uv run pytest-llm tests/test_launch_process.py`
- `uv run pytest-llm tests/exec/test_claude_cwd_isolation.py`
- `uv run pytest-llm tests/exec/test_streaming_runner.py`
- `uv run pytest-llm tests/exec/test_permissions.py`

## Scenarios to Verify

- `S024`
- `S025`
- `S026`
- `S046`
- `S046b`

Phase cannot close until every scenario above is marked `verified` in `scenarios/`.

## Agent Staffing

- `@coder` on `gpt-5.3-codex`
- `@verifier` on `gpt-5.4-mini`
- `@unit-tester` on `gpt-5.4`
- `@smoke-tester` on `claude-sonnet-4-6`
- Escalate to `@reviewer` on `gpt-5.2` for shared-core design alignment issues
