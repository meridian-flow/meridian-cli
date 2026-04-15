# Phase 0: Effort Plumbing

## Scope

Fix the upstream child-spawn bug where `effort` is resolved during prepare time but then disappears before either runner rebuilds `SpawnParams`.

This phase is intentionally narrow. Do not start launch-spec work here. The only goal is to make `PreparedSpawnPlan` carry `effort` all the way to both execution paths.

## Files to Modify

- `src/meridian/lib/ops/spawn/plan.py`
  Add `effort: str | None = None` to `PreparedSpawnPlan`.
- `src/meridian/lib/ops/spawn/prepare.py`
  Populate `PreparedSpawnPlan.effort` from `resolved.effort`.
- `src/meridian/lib/launch/runner.py`
  Include `effort=plan.effort` when reconstructing `SpawnParams`.
- `src/meridian/lib/launch/streaming_runner.py`
  Include `effort=plan.effort` when reconstructing `SpawnParams`.
- `tests/ops/test_spawn_prepare_fork.py`
  Extend or clone the existing prepare-path fixture to assert the prepared plan preserves effort.
- `tests/exec/test_lifecycle.py`
  Assert the foreground runner forwards plan effort into the adapter-facing `SpawnParams`.
- `tests/exec/test_streaming_runner.py`
  Assert the streaming runner forwards plan effort into the connection path.

## Dependencies

- Requires: none
- Produces: trustworthy `plan.effort` data for every later phase
- Blocks: every launch-spec phase

## Interface Contract

After this phase, these invariants must hold:

```python
PreparedSpawnPlan.effort: str | None
SpawnParams.effort == plan.effort  # in runner.py
SpawnParams.effort == plan.effort  # in streaming_runner.py
```

The preview command built in `prepare.py` and the executed command built in the runners must now agree on effort.

## Verification Criteria

- [ ] `uv run pytest-llm tests/ops/test_spawn_prepare_fork.py`
- [ ] `uv run pytest-llm tests/exec/test_lifecycle.py tests/exec/test_streaming_runner.py`
- [ ] `uv run pyright`
- [ ] Manual spot-check: dry-run a spawn with `--effort high` and confirm the prepared CLI preview still shows the effort flag for the selected harness

## Staffing

- Builder: `@coder` on `gpt-5.3-codex`
- Testing lanes: `@verifier` on `gpt-5.4-mini`, `@unit-tester` on `gpt-5.4`

## Constraints

- No behavior change beyond plumbing.
- Do not touch `launch/plan.py` for primary launches in this phase.
- Do not introduce `ResolvedLaunchSpec` yet.
