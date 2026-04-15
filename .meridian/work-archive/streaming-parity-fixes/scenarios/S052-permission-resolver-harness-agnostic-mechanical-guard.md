# S052: `PermissionResolver.resolve_flags` stays harness-agnostic (mechanical guard)

- **Source:** design/edge-cases.md K4 reference + decisions.md K4 (revision round 3 convergence pass, F7)
- **Added by:** @design-orchestrator (revision round 3 convergence pass)
- **Tester:** @unit-tester
- **Status:** verified

## Given
K4 requires `PermissionResolver.resolve_flags(self) -> tuple[str, ...]` to be **harness-agnostic**: no `harness` / `harness_id` parameter, and no branching on harness identity inside any resolver implementation. The harness-specific wire translation lives in projection modules, not in the resolver.

Without a mechanical guard this invariant degrades silently: a developer can add a `harness` kwarg "just for this one case" and every existing caller keeps working because Python doesn't re-check Protocol conformance on mutation.

## When
The pre-commit / CI guard runs after any change to resolver or Protocol surface.

## Then
- `inspect.signature(PermissionResolver.resolve_flags)` contains exactly one parameter (`self`) and no `harness` / `harness_id` / `harness_name` keyword.
- For every concrete resolver class registered in the project (discovered via `__subclasses__` walk or an explicit test registry list), `inspect.signature(cls.resolve_flags)` matches the Protocol signature exactly.
- A repo-wide ripgrep for `HarnessId` inside any file under `src/meridian/lib/permissions/` returns **zero** matches. Resolvers must not import `HarnessId` at all — if they need to distinguish behavior, the work belongs in the projection layer.
- A repo-wide ripgrep for `harness[_ ]?id` (case-insensitive) inside any `resolve_flags` method body returns zero matches.

## Verification
- Unit test: assert `len(inspect.signature(PermissionResolver.resolve_flags).parameters) == 1` and the single parameter is named `self`.
- Unit test: iterate every concrete resolver class (`ClaudePermissionResolver`, `CodexPermissionResolver`, `OpenCodePermissionResolver`, `UnsafeNoOpPermissionResolver`) and assert each `resolve_flags` signature matches the Protocol exactly.
- Ripgrep regression test run from inside the test (via `subprocess.run(["rg", ...])`): `rg --type py "HarnessId" src/meridian/lib/permissions/` returns exit code 1 (no matches).
- Ripgrep regression test: `rg --type py -i "harness[_ ]?id" src/meridian/lib/permissions/` returns exit code 1.
- Negative fixture: declare a test-local `BadResolver` with `def resolve_flags(self, harness: HarnessId) -> tuple[str, ...]` and assert the signature-comparison helper raises / marks it noncompliant. This proves the guard actually catches the drift it is meant to catch.

## Result (filled by tester)
- **Date:** 2026-04-10
- **Status:** verified
- **Tests:** `tests/exec/test_permissions.py::test_s052_resolver_signatures_are_harness_agnostic`, `tests/exec/test_permissions.py::test_s052_permissions_module_has_no_harnessid_import`, `tests/exec/test_permissions.py::test_s052_permissions_module_has_no_harness_identity_references`, `tests/exec/test_permissions.py::test_s052_bad_resolver_with_harness_param_is_non_compliant`, `tests/exec/test_permissions.py::test_unsafe_no_op_permission_resolver_returns_no_flags`
- **Commands:**
  - `uv run pytest-llm tests/exec/test_permissions.py -v` -> `28 passed in 1.27s`
  - `uv run ruff check .` -> `All checks passed!`
  - `uv run pyright` -> `0 errors, 0 warnings, 0 informations`
- **Evidence:**
  - The signature guard is real: the shared helper compares each concrete resolver class against `PermissionResolver.resolve_flags(self)` exactly, and the negative `BadResolver` fixture with `resolve_flags(self, harness: HarnessId)` now fails that helper.
  - Ripgrep subprocess coverage is real and not skipped: both `rg --type py "HarnessId" src/meridian/lib/safety/permissions.py` and `rg --type py -i "harness[_ ]?(id|name)" src/meridian/lib/safety/permissions.py` are asserted to return exit code `1`.
  - Exploratory regression coverage was added for `UnsafeNoOpPermissionResolver.resolve_flags() == ()`.
