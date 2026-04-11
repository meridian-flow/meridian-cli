# S003: Caller passes `None` as `PermissionResolver`

- **Source:** design/edge-cases.md E3 + p1411 finding H3 + L6
- **Added by:** @design-orchestrator (design phase)
- **Tester:** @verifier
- **Status:** verified

## Given
The codebase forbids `cast("PermissionResolver", None)` patterns. Every call site must pass a real resolver.

## When
A developer attempts to add `adapter.resolve_launch_spec(params, None)` or reintroduces the `cast("PermissionResolver", None)` pattern.

## Then
- Pyright rejects the call: `None` is not assignable to parameter `perms: PermissionResolver`.
- The two v1 sites (`streaming_runner.py:457` and `server.py:203`) no longer contain the cast — grep across the tree returns zero matches for `cast("PermissionResolver"` and zero matches for `cast('PermissionResolver'`.

## Verification
- `uv run pyright` against the full tree reports zero errors. Any attempt to reintroduce the cast pattern shows up in the diff.
- `uv run ruff check .` clean.
- Manual grep: `rg "cast\\(\\s*['\"]PermissionResolver['\"]"` over `src/` returns nothing.

## Result (filled by tester)
- **Date:** 2026-04-10
- **Spawn:** p1448
- **Commands run:**
  - `uv run ruff check .`
  - `uv run pyright`
  - `rg "cast\\(\\s*['\"]PermissionResolver['\"]" src/`
  - `rg "resolve_permission_config" src/`
  - `uv run pytest-llm tests/exec/test_permissions.py -v`
  - `uv run pytest-llm tests/harness/test_launch_spec.py -v`
  - `uv run pytest-llm tests/test_app_server.py -v`
  - `uv run pytest-llm tests/harness/ -v`
- **Key excerpts:**
  - `uv run ruff check .` -> `All checks passed!`
  - `uv run pyright` -> `0 errors, 0 warnings, 0 informations`
  - `rg "cast\\(\\s*['\"]PermissionResolver['\"]" src/` -> no output
  - `rg "resolve_permission_config" src/` -> no output
  - `uv run pytest-llm tests/exec/test_permissions.py -v` -> `24 passed`
  - `uv run pytest-llm tests/harness/test_launch_spec.py -v` -> `10 passed`
  - `uv run pytest-llm tests/test_app_server.py -v` -> `3 passed`
  - `uv run pytest-llm tests/harness/ -v` -> `77 passed`
- **Spot-check:**
  - `src/meridian/lib/launch/streaming_runner.py` now passes `UnsafeNoOpPermissionResolver(_suppress_warning=True)` into `adapter.resolve_launch_spec(...)` at the previous cast site.
  - `src/meridian/lib/app/server.py` now constructs either `UnsafeNoOpPermissionResolver()` for the explicit unsafe opt-out or `TieredPermissionResolver(config=permission_config)` before calling `adapter.resolve_launch_spec(...)`.
- **Result:** verified
