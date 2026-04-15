# S027: `python -O` strips nothing meaningful

- **Source:** design/edge-cases.md E27 + p1411 finding L1
- **Added by:** @design-orchestrator (design phase)
- **Tester:** @verifier
- **Status:** verified

## Given
The v2 design replaces every `assert` used for completeness checking with `raise ImportError(...)`. The running environment sets `PYTHONOPTIMIZE=1` (equivalent to `python -O`), which strips assertions.

## When
The full test suite runs under `PYTHONOPTIMIZE=1 uv run pytest-llm`.

## Then
- All completeness guard scenarios (S005, S006, S030) still fire correctly — because they use `ImportError`, not `assert`.
- Total pass/fail counts match a non-optimized run.
- No silent regression where a guard stops working because `-O` stripped the `assert`.
- `rg "assert " src/meridian/lib/harness/launch_spec.py` and `rg "assert " src/meridian/lib/harness/projections/` return only non-guard asserts (e.g., loop invariants that are OK to strip), and ideally zero in guard-related files.

## Verification
- Run the full suite twice: once with normal `uv run pytest-llm`, once with `PYTHONOPTIMIZE=1 uv run pytest-llm`.
- Compare the `pass/fail/skip` counts — must match.
- Specifically check S005, S006, S030 scenarios — they must fail (as expected) under both modes when the guard is intentionally broken.
- Grep `src/meridian/lib/harness/launch_spec.py` for `assert ` — there must be zero uses for completeness checking.
- Grep `src/meridian/lib/harness/projections/` for `assert ` — same.

## Result (filled by tester)
failed 2026-04-11

- Evidence:
  - `uv run ruff check .` -> `All checks passed!`
  - `uv run pyright` -> `0 errors, 0 warnings, 0 informations`
  - `rg -n "assert " src/meridian/lib/harness/launch_spec.py src/meridian/lib/harness/projections src/meridian/lib/harness/bundle.py` -> exit code `1` (no matches)
  - `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/ --ignore=tests/smoke --collect-only -q > /tmp/collect.normal`
  - `UV_CACHE_DIR=/tmp/uv-cache PYTHONOPTIMIZE=1 uv run pytest tests/ --ignore=tests/smoke --collect-only -q > /tmp/collect.opt`
  - `grep '^tests/' /tmp/collect.normal | wc -l` -> `552`
  - `grep '^tests/' /tmp/collect.opt | wc -l` -> `552`
  - `comm -3 <(grep '^tests/' /tmp/collect.normal | sort) <(grep '^tests/' /tmp/collect.opt | sort)` -> no output
  - `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/harness/test_launch_spec_parity.py::test_claude_projection_import_fails_when_new_model_field_is_unaccounted tests/harness/test_spec_field_guards.py::test_enforce_spawn_params_accounting_reports_missing_real_field_name tests/harness/test_launch_spec_parity.py::test_projection_package_exposes_projected_fields_for_each_projection_module -q` -> `3 passed in 0.34s`
  - `UV_CACHE_DIR=/tmp/uv-cache PYTHONOPTIMIZE=1 uv run pytest tests/harness/test_launch_spec_parity.py::test_claude_projection_import_fails_when_new_model_field_is_unaccounted tests/harness/test_spec_field_guards.py::test_enforce_spawn_params_accounting_reports_missing_real_field_name tests/harness/test_launch_spec_parity.py::test_projection_package_exposes_projected_fields_for_each_projection_module -q` -> `3 passed, 1 warning in 0.34s`
  - Full-suite fail-fast parity probe under both modes stops at the same unrelated red test:
    - `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/ --ignore=tests/smoke -x` -> first failure at `tests/exec/test_signals.py .F`
    - `UV_CACHE_DIR=/tmp/uv-cache PYTHONOPTIMIZE=1 uv run pytest tests/ --ignore=tests/smoke -x` -> first failure at `tests/exec/test_signals.py .F`
- Delta between optimized and non-optimized counts:
  - Requested pass/fail/skip parity could not be certified because the non-smoke suite is currently red in both modes on the same signal test, so neither run reaches a stable terminal summary count.
  - Collection delta is `0` after stripping pytest warning lines: both modes collect the same `552` test nodes.
  - Focused S005/S006/S030 guard probes delta is `0`: `3 passed` in normal mode and `3 passed` in optimized mode. Optimized mode adds only pytest's expected warning that non-test `assert` statements are ignored under `-O`.
- Notes:
  - The S027-specific guard behavior looks correct: no completeness guards rely on `assert`, and the import-time guard probes still fire under `PYTHONOPTIMIZE=1`.
  - Verification remains blocked on a separate regression or flake in `tests/exec/test_signals.py::test_streaming_runner_signal_cancel_invokes_send_cancel_once`, which fails in both modes and prevents full-suite count comparison.

### Re-verify 2026-04-11

- Full-suite normal mode (orchestrator direct run): `552 passed`.
- Full-suite optimized mode: `PYTHONOPTIMIZE=1` also reports `552 passed`, plus one pytest-internal warning about `-O` stripping asserts (expected; not a failure).
- Fix-coder p1504 collect-only parity sidecheck: normal=`559`, optimized=`559`, diff=`0`.
- Grep evidence:
  - `rg 'assert ' src/meridian/lib/harness/launch_spec.py` -> no completeness-guard asserts.
  - `rg 'assert ' src/meridian/lib/harness/projections/` -> no completeness-guard asserts.
  - `rg 'assert ' src/meridian/lib/harness/bundle.py` -> no completeness-guard asserts.
- Conclusion: S027 contract is satisfied. Prior `failed` status came from verifier p1489 observing a transient concurrent-edit state while unit tester p1490 was updating `tests/exec/test_signals.py`; the suite is now stable.
