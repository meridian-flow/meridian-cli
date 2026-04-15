# Phase 1: Contract Leaves and Adapter ABCs

## Scope

Create the typed leaf modules and abstract contract surfaces that later phases build on. This phase does not change harness-specific wire behavior yet; it makes the contract failures loud instead of implicit.

## Files to Modify

- `src/meridian/lib/launch/launch_types.py` — add the leaf home for `SpecT`, `PermissionResolver`, `ResolvedLaunchSpec`, and `PreflightResult`
- `src/meridian/lib/harness/ids.py` — add the single source of truth for `HarnessId` and `TransportId`
- `src/meridian/lib/harness/adapter.py` — replace `BaseSubprocessHarness` with `BaseHarnessAdapter`, make `id` and `resolve_launch_spec` abstract, split `consumed_fields` and `explicitly_ignored_fields`
- `src/meridian/lib/harness/connections/base.py` — replace facet Protocol composition with one generic `HarnessConnection[SpecT]` ABC
- `src/meridian/lib/harness/launch_types.py` — keep only session/prompt helper types that still belong under `harness/`
- `tests/harness/test_adapter_ownership.py` and/or a new `tests/harness/test_typed_contracts.py` — add Protocol/ABC reconciliation coverage

## Dependencies

- Requires: nothing
- Produces: leaf import targets every later phase depends on
- Independent of: harness-specific projection modules

## Interface Contract

```python
SpecT = TypeVar("SpecT", bound="ResolvedLaunchSpec")

class BaseHarnessAdapter(Generic[SpecT], ABC):
    @property
    @abstractmethod
    def id(self) -> HarnessId: ...

    @property
    @abstractmethod
    def consumed_fields(self) -> frozenset[str]: ...

    @property
    @abstractmethod
    def explicitly_ignored_fields(self) -> frozenset[str]: ...

    @property
    def handled_fields(self) -> frozenset[str]:
        return self.consumed_fields | self.explicitly_ignored_fields

    @abstractmethod
    def resolve_launch_spec(self, run: SpawnParams, perms: PermissionResolver) -> SpecT: ...
```

## Patterns to Follow

- Use the frozen DTO style already present in [ops/spawn/plan.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/ops/spawn/plan.py).
- Keep the new leaf modules import-light; phase 1 is where import-cycle pressure is removed, not shuffled.

## Constraints

- Do not introduce harness-specific projection logic here.
- Do not convert dispatch to bundle bootstrap yet; phase 7 owns that integration.
- Do not keep a base `resolve_launch_spec(...)` fallback.

## Verification Criteria

- `uv run pyright`
- `uv run pytest-llm tests/harness/test_adapter_ownership.py`
- `uv run pytest-llm tests/test_spawn_manager.py -k contract`

## Scenarios to Verify

- `S001`
- `S040`

Phase cannot close until both scenarios above are marked `verified` in `scenarios/`.

## Agent Staffing

- `@coder` on `gpt-5.3-codex`
- `@verifier` on `gpt-5.4-mini`
- `@unit-tester` on `gpt-5.4`
- Escalate to `@reviewer` on `gpt-5.4` if Protocol/ABC or generic binding remains unresolved after one coder loop
