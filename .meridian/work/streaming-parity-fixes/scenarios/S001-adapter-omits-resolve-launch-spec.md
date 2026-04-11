# S001: Adapter omits `resolve_launch_spec` override

- **Source:** design/edge-cases.md E1 + p1411 M2
- **Added by:** @design-orchestrator (design phase)
- **Tester:** @unit-tester
- **Status:** pending

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
_pending_
