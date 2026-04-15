# S020: `continue_fork=True` with no `continue_session_id`

- **Source:** design/edge-cases.md E20
- **Added by:** @design-orchestrator (design phase)
- **Tester:** @unit-tester
- **Status:** verified

## Given
Any launch-spec subclass is constructed with `continue_fork=True` and missing session id.

## When
Model validation runs.

## Then
- Construction raises `ValueError("continue_fork=True requires continue_session_id")`.
- Rule applies uniformly to Claude, Codex, and OpenCode via base-spec validator.

## Verification
- Parametrize over all three subclasses and assert same failure.
- Positive controls verify valid combinations still pass.

## Result (filled by tester)
- **Date:** 2026-04-10
- **Status:** verified
- **Tests:** `tests/harness/test_launch_spec.py::test_continue_fork_requires_continue_session_id`, `tests/harness/test_launch_spec.py::test_continue_fork_valid_combinations_pass`
- **Commands:**
  - `uv run pytest-llm tests/harness/test_launch_spec.py -v` -> `16 passed in 0.10s`
  - `uv run pytest-llm tests/harness/ -v` -> `85 passed in 0.90s`
- **Evidence:**
  - Negative coverage is parameterized across `ClaudeLaunchSpec`, `CodexLaunchSpec`, and `OpenCodeLaunchSpec`.
  - The strengthened test now checks the exact underlying validator error: Pydantic raises a `ValidationError`, whose single error entry contains `ctx.error == ValueError("continue_fork=True requires continue_session_id")`.
  - Positive controls cover the allowed combinations: `continue_fork=False` without a session id, and `continue_fork=True` with a session id, on all three subclasses.
