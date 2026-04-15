# Phase 1: Launch Spec Foundation

## Scope

Add the transport-neutral launch-spec layer and make every subprocess adapter able to resolve one from `SpawnParams` plus `PermissionResolver`.

This is the policy phase. It defines the new spec types and the completeness guard, but it does not change how commands or connections are built yet.

## Files to Modify

- `src/meridian/lib/harness/launch_spec.py` (new)
  Add `ResolvedLaunchSpec`, `ClaudeLaunchSpec`, `CodexLaunchSpec`, and `OpenCodeLaunchSpec`.
- `src/meridian/lib/harness/adapter.py`
  Extend the subprocess harness protocol with `resolve_launch_spec(run, perms)`.
- `src/meridian/lib/harness/claude.py`
  Implement `resolve_launch_spec()` and move Claude effort normalization into spec construction.
- `src/meridian/lib/harness/codex.py`
  Implement `resolve_launch_spec()` and normalize Codex effort plus approval/sandbox semantics.
- `src/meridian/lib/harness/opencode.py`
  Implement `resolve_launch_spec()` and normalize OpenCode model prefix and effort.
- `src/meridian/lib/harness/__init__.py`
  Re-export the new spec types if the package currently re-exports harness primitives.
- `tests/harness/test_launch_spec.py` (new)
  Add per-adapter fixture coverage for representative `SpawnParams` -> spec resolution.

## Dependencies

- Requires: Phase 0
- Produces: the single mapping layer every later phase consumes
- Blocks: Phase 2 through Phase 6

## Interface Contract

Each adapter must expose:

```python
def resolve_launch_spec(
    self,
    run: SpawnParams,
    perms: PermissionResolver,
) -> ResolvedLaunchSpec: ...
```

And `launch_spec.py` must enforce:

```python
_SPEC_HANDLED_FIELDS == set(SpawnParams.model_fields)
```

The spec stays semantic:
- permissions stay as `PermissionConfig` plus `PermissionResolver`
- normalized effort values are stored as plain strings
- no CLI flag tokens or JSON-RPC method names live in the spec models

## Patterns to Follow

- Match the existing frozen Pydantic style in `src/meridian/lib/harness/adapter.py`.
- Keep harness-specific normalization inside adapter-owned helpers, not in the transport layers.
- Record unsupported-but-known fields in the spec rather than silently dropping them.

## Verification Criteria

- [ ] `uv run pytest-llm tests/harness/test_launch_spec.py`
- [ ] `uv run pyright`
- [ ] Importing the harness package fails loudly if `SpawnParams` fields and `_SPEC_HANDLED_FIELDS` drift

## Staffing

- Builder: `@coder` on `gpt-5.3-codex`
- Testing lanes: `@verifier` on `gpt-5.4-mini`, `@unit-tester` on `gpt-5.2`

## Constraints

- Do not change `build_command()` yet.
- Do not change any connection adapter yet.
- The only new source of truth should be `resolve_launch_spec()`, not a second strategy layer.
