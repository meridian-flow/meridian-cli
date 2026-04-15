# Phase 2: Launch Spec and Permission Pipeline

## Scope

Make permission intent mandatory, harness-agnostic, and immutable. Replace the current fallback-heavy launch-spec shape with import-time accounting and base validators that fail loudly before any spawn runs.

## Files to Modify

- `src/meridian/lib/safety/permissions.py` — non-optional resolver with `.config`, frozen `PermissionConfig`, `UnsafeNoOpPermissionResolver`, harness-agnostic `resolve_flags()`
- `src/meridian/lib/harness/launch_spec.py` — concrete spec subclasses, base `continue_fork` validator, restored `mcp_tools`, `_enforce_spawn_params_accounting(registry=None)`
- `src/meridian/lib/harness/adapter.py` — import the leaf `PermissionResolver` contract and keep `SpawnParams` aligned with handled-field accounting
- `src/meridian/lib/app/server.py` — reject missing permission metadata by default and only opt out via explicit unsafe mode
- `tests/exec/test_permissions.py` — frozen-config, resolver-shape, and environment-merge regression tests
- `tests/harness/test_launch_spec.py` — spec construction and validation coverage
- `tests/test_app_server.py` — strict REST default vs unsafe opt-out

## Dependencies

- Requires: Phase 1
- Produces: stable launch-spec and permission contracts consumed by phases 3-8
- Independent of: harness-specific projection modules

## Interface Contract

```python
class PermissionResolver(Protocol):
    @property
    def config(self) -> PermissionConfig: ...
    def resolve_flags(self) -> tuple[str, ...]: ...

class ResolvedLaunchSpec(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
    permission_resolver: PermissionResolver
    extra_args: tuple[str, ...] = ()
    mcp_tools: tuple[str, ...] = ()
```

## Patterns to Follow

- Mirror the frozen Pydantic usage in [ops/spawn/plan.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/ops/spawn/plan.py).
- Use explicit `ImportError`/`RuntimeError` failures rather than `assert` for guard behavior.

## Constraints

- No harness-specific branching inside resolver implementations.
- No `cast("PermissionResolver", None)` or `getattr(..., "config", None)` fallback chain survives this phase.
- Do not wire projection-side field accounting yet; phases 3-5 own per-harness projection modules.

## Verification Criteria

- `uv run pyright`
- `uv run pytest-llm tests/exec/test_permissions.py`
- `uv run pytest-llm tests/harness/test_launch_spec.py`
- `uv run pytest-llm tests/test_app_server.py`

## Scenarios to Verify

- `S003`
- `S004`
- `S006`
- `S013`
- `S020`
- `S051`
- `S052`

Phase cannot close until every scenario above is marked `verified` in `scenarios/`.

## Agent Staffing

- `@coder` on `gpt-5.3-codex`
- `@verifier` on `gpt-5.4-mini`
- `@unit-tester` on `gpt-5.4`
- `@smoke-tester` on `claude-sonnet-4-6`
- Escalate to `@reviewer` on `gpt-5.2` for permission-policy vs coordinator-boundary disagreements
