# S051: `PermissionConfig` + `PreflightResult.extra_env` immutability

- **Source:** design/edge-cases.md E43 + decisions.md K7 (revision round 3)
- **Added by:** @design-orchestrator (revision round 3)
- **Tester:** @unit-tester
- **Status:** verified

## Given
A `PermissionConfig(sandbox="read-only", approval="default")` instance held inside a `PermissionResolver` that is in turn held inside a `ResolvedLaunchSpec`.

## When
Downstream code attempts to mutate the config:

- `config.sandbox = "yolo"`
- `setattr(config, "sandbox", "yolo")`
- `object.__setattr__(config, "sandbox", "yolo")` (also should fail on frozen Pydantic)

## Then
- Each mutation attempt raises `ValidationError` / `TypeError` per Pydantic v2 frozen-model semantics.
- The original config value is preserved — no silent mutation.
- `PreflightResult.extra_env` wrapped in `MappingProxyType` rejects mutation attempts with `TypeError`.

## Verification
- Unit test: construct `PermissionConfig`, assert each mutation attempt above raises.
- Unit test: construct `PreflightResult.build(expanded_passthrough_args=(), extra_env={"K":"V"})`, assert `result.extra_env["K2"] = "V2"` raises `TypeError`.
- Positive test: reading the frozen values still works (`config.sandbox == "read-only"`).
- Cross-check: grep for any `config.sandbox =` assignment in the runtime codebase — there should be zero.

## Result (filled by tester)
- **Date:** 2026-04-10
- **Status:** verified
- **Tests:** `tests/exec/test_permissions.py::test_s051_permission_config_is_frozen_after_construction`, `tests/exec/test_permissions.py::test_s051_preflight_result_extra_env_is_immutable`, `tests/exec/test_permissions.py::test_s051_runtime_code_does_not_assign_to_permission_config_sandbox`
- **Commands:**
  - `uv run pytest-llm tests/exec/test_permissions.py -v` -> `28 passed in 1.27s`
  - `rg -n "config\\.sandbox\\s*=" src` -> exit code `1`
  - `rg -n "class LaunchContext" src tests` -> exit code `1`
  - `rg -n "MappingProxyType" src/meridian/lib` -> only `src/meridian/lib/launch/launch_types.py`
- **Evidence:**
  - `PermissionConfig` is genuinely frozen: direct assignment and `setattr(...)` raise `ValidationError`, and `object.__setattr__(...)` raises `TypeError`; the original `sandbox` value remains `read-only`.
  - `PreflightResult.build(...).extra_env` is wrapped in `MappingProxyType` and rejects mutation with `TypeError`.
  - No runtime code assigns `config.sandbox = ...`.
  - LaunchContext immutability checks were split out of S051 to S054 (Phase 6 ownership); S051 now intentionally covers only the Phase 2 clauses above.
