# S004: `PermissionResolver` implementation lacks `.config`

- **Source:** design/edge-cases.md E4 + p1411 finding H3 + L6
- **Added by:** @design-orchestrator (design phase)
- **Tester:** @unit-tester
- **Status:** verified

## Given
The `PermissionResolver` Protocol in v2 declares `config` as a required property returning a `PermissionConfig`. A developer adds a new resolver class but forgets to implement `config`.

## When
Pyright runs over the module containing the new resolver, and runtime code does `isinstance(resolver, PermissionResolver)`.

## Then
- Pyright reports that the class does not satisfy `PermissionResolver` because `config` is unimplemented.
- Runtime `isinstance(my_resolver, PermissionResolver)` returns `False` (because Protocol is `runtime_checkable`).
- Any call into `adapter.resolve_launch_spec(params, my_resolver)` is rejected by pyright.

## Verification
- Author a pytest fixture class `BrokenResolver` with only `resolve_flags` and no `config` property.
- Assert `isinstance(BrokenResolver(), PermissionResolver) is False`.
- Run `uv run pyright` against the fixture module and assert the "is not assignable to type PermissionResolver" diagnostic appears.
- Confirm the legacy `resolve_permission_config(perms)` getattr fallback helper is deleted from the tree.

## Result (filled by tester)
- **Date:** 2026-04-10
- **Status:** verified
- **Tests:** `tests/exec/test_permissions.py::test_s004_broken_resolver_without_config_is_not_protocol_instance`, `tests/exec/test_permissions.py::test_s004_broken_resolver_fixture_fails_pyright`, `tests/exec/test_permissions.py::test_s004_legacy_resolve_permission_config_helper_deleted`
- **Commands:**
  - `uv run pyright` -> `0 errors, 0 warnings, 0 informations`
  - `uv run pytest-llm tests/exec/test_permissions.py -v` -> `28 passed in 1.27s`
- **Evidence:**
  - Runtime protocol check is real: `BrokenResolver()` without `.config` is not a `PermissionResolver`.
  - The new fixture-backed pyright test asserts both failure modes required by the scenario: assignment to `PermissionResolver` and passing `BrokenResolver()` into `ClaudeAdapter().resolve_launch_spec(...)` both emit `"config" is not present` diagnostics.
  - `rg "resolve_permission_config\\(" src` returned exit code `1`, so the legacy getattr fallback helper is absent.
