# S006: New field on `SpawnParams`, factory doesn't map it

- **Source:** design/edge-cases.md E6 + p1411 finding L1 (assert under -O)
- **Added by:** @design-orchestrator (design phase)
- **Tester:** @unit-tester
- **Status:** verified

## Given
A developer adds `bar: str | None = None` to `SpawnParams` (the transport-neutral run parameter bundle) but does not update `_SPEC_HANDLED_FIELDS` / `_SPEC_DELEGATED_FIELDS` in `launch_spec.py` and does not update any adapter's `resolve_launch_spec`.

## When
`launch_spec.py` is imported at application startup.

## Then
- `ImportError` is raised naming `bar` as an unmapped field and listing the adapter implementations that must be updated.
- Error fires whether running under `python` or `python -O` (uses `ImportError`, not `assert`).
- No field silently disappears between `SpawnParams` and the resolved spec.

## Verification
- Fixture that temporarily adds a field to `SpawnParams.model_fields` and re-imports `launch_spec`.
- Assert `ImportError` with the expected message.
- Run `PYTHONOPTIMIZE=1 .venv/bin/python -m pytest tests/harness/test_spec_field_guards.py -v` to confirm `-O` safety.
- Grep `src/meridian/lib/harness/launch_spec.py` for `assert ` — zero results (the v1 assert on L1 must be removed).

## Result (filled by tester)
- **Date:** 2026-04-10
- **Status:** verified
- **Tests:** `tests/harness/test_spec_field_guards.py::test_enforce_spawn_params_accounting_reports_missing_field`, `tests/harness/test_spec_field_guards.py::test_launch_spec_guard_uses_no_runtime_asserts`, `tests/harness/test_spec_field_guards.py::test_launch_spec_import_is_clean_in_unmodified_tree`
- **Commands:**
  - `uv run pytest-llm tests/harness/test_spec_field_guards.py -v` -> `4 passed in 0.28s`
  - `PYTHONOPTIMIZE=1 .venv/bin/python -m pytest tests/harness/test_spec_field_guards.py -v` -> `4 passed, 1 warning in 0.28s`
  - `PYTHONPATH=src .venv/bin/python - <<'PY' ... importlib.reload(launch_spec) ... PY` -> `IMPORT_ERROR ... Missing (no adapter claims these): ['bogus_phase2_field']`
  - `rg "assert " src/meridian/lib/harness/launch_spec.py` -> exit code `1`
- **Evidence:**
  - `_enforce_spawn_params_accounting()` now runs at module import time in `launch_spec.py`, so drift is fail-loud at import instead of deferred to manual helper calls.
  - After injecting `bogus_phase2_field` into `SpawnParams.model_fields`, reloading `meridian.lib.harness.launch_spec` now raises `ImportError` naming that field (no `RELOAD_OK` path remains).
  - The guard remains `-O` safe (`PYTHONOPTIMIZE=1` test pass) and the module contains no runtime `assert`.
