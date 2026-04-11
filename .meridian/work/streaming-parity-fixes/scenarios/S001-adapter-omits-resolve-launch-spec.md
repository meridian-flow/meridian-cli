# S001: Adapter omits `resolve_launch_spec` override

- **Source:** design/edge-cases.md E1 + p1411 M2
- **Added by:** @design-orchestrator (design phase)
- **Tester:** @unit-tester
- **Status:** verified

## Given
A new harness subclasses `BaseHarnessAdapter` but omits `resolve_launch_spec`.

## When
Pyright runs and runtime instantiation is attempted.

## Then
- Pyright reports the missing method.
- `NewHarness()` raises `TypeError: Can't instantiate abstract class ... with abstract method resolve_launch_spec`.
- This runtime failure is from ABC abstract-method enforcement, not Protocol instantiation behavior.

## Verification
- Fixture class: `class NewHarness(BaseHarnessAdapter[ResolvedLaunchSpec]): ...` with no override.
- Assert runtime `TypeError` on instantiation.
- Assert pyright reports unsatisfied abstract/Protocol contract.

## Result (filled by tester)
- Date: 2026-04-10
- Tester agent id: n/a (interactive Codex session)
- Commit SHA: none
- Commands run:
  - `uv run pytest-llm tests/harness/test_typed_contracts.py -v`
  - `uv run pytest-llm tests/harness/ -v`
  - `uv run pyright`
  - `uv run ruff check tests/harness/`
- Passing output excerpt:
  - `tests/harness/test_typed_contracts.py ..........                         [100%]`
  - `============================== 10 passed in 0.26s ==============================`
  - `============================== 72 passed in 0.69s ==============================`
  - `0 errors, 0 warnings, 0 informations`
  - `All checks passed!`
- Test pointer:
  - `tests/harness/test_typed_contracts.py::test_s001_missing_only_resolve_launch_spec_mentions_that_method`
  - `tests/harness/test_typed_contracts.py::test_s001_base_adapter_requires_resolve_launch_spec_override`
