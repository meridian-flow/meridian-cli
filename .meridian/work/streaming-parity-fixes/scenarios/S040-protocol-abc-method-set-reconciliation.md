# S040: `HarnessAdapter` Protocol and `BaseHarnessAdapter` ABC method sets stay reconciled

- **Source:** design/edge-cases.md E40 + decisions.md K3 (revision round 3)
- **Added by:** @design-orchestrator (revision round 3)
- **Tester:** @unit-tester
- **Status:** verified

## Given
`HarnessAdapter[SpecT]` is a `@runtime_checkable Protocol` declaring required attributes: `id`, `handled_fields`, `resolve_launch_spec`, `preflight`. `BaseHarnessAdapter(Generic[SpecT], ABC)` must mark the same required attributes as `@abstractmethod`.

## When
A new concrete adapter subclasses `BaseHarnessAdapter` but forgets to declare `id`.

## Then
- `MyAdapter()` raises `TypeError: Can't instantiate abstract class MyAdapter with abstract method id`.
- The failure happens at **instantiation**, not after the first dispatch `AttributeError`.
- pyright also flags the structural Protocol noncompliance at type-check time.

## Verification
- Unit test: declare a reconciliation helper `_required_protocol_attrs(HarnessAdapter)` that uses `inspect.getmembers` or the Protocol `__protocol_attrs__` internal to enumerate required attributes.
- Enumerate the `abstractmethod` set of `BaseHarnessAdapter` (via `__abstractmethods__`).
- Assert the two sets are equal.
- Regression fixture: `class Incomplete(BaseHarnessAdapter[ResolvedLaunchSpec]): def resolve_launch_spec(self, run, perms): ...` — missing `id` and `handled_fields`. Assert instantiation raises `TypeError` and the error message mentions both missing methods.

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
  - `tests/harness/test_typed_contracts.py::test_s040_protocol_and_abc_required_member_sets_reconcile`
  - `tests/harness/test_typed_contracts.py::test_s040_incomplete_adapter_lists_all_missing_members`
  - `tests/harness/test_typed_contracts.py::test_s040_missing_id_raises_instantiation_error`
