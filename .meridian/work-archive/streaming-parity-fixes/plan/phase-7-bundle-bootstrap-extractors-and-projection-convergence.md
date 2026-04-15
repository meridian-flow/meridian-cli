# Phase 7: Bundle Bootstrap, Extractors, and Projection Convergence

## Scope

Wire the concrete harnesses into the typed bundle registry, eager-import every projection so drift checks always run, and replace the current streaming extractor shortcut with harness-owned extractors that work for both subprocess and streaming. This is the package-load convergence phase.

## Files to Modify

- `src/meridian/lib/harness/bundle.py` — add `HarnessBundle`, registry helpers, duplicate-registration and unsupported-transport failures
- `src/meridian/lib/harness/__init__.py` — add the canonical eager-import bootstrap order and tail call to `_enforce_spawn_params_accounting()`
- `src/meridian/lib/harness/launch_spec.py` — expose `_enforce_spawn_params_accounting(registry=None)` for bootstrap-time use
- `src/meridian/lib/harness/registry.py` — bridge or retire the old adapter registry so bundle lookup becomes authoritative
- `src/meridian/lib/harness/connections/__init__.py` — retire the flat harness-only connection registry
- `src/meridian/lib/harness/projections/_guards.py` — shared projection drift helper
- `src/meridian/lib/harness/extractors/base.py`, `src/meridian/lib/harness/extractors/__init__.py`, `src/meridian/lib/harness/extractors/claude.py`, `src/meridian/lib/harness/extractors/codex.py`, `src/meridian/lib/harness/extractors/opencode.py` — new extractor surface and harness implementations
- `src/meridian/lib/harness/extractor.py` and `src/meridian/lib/harness/session_detection.py` — replace or shrink legacy extractor/session-detection shortcuts
- `src/meridian/lib/streaming/spawn_manager.py` — dispatch through bundle lookup + runtime type guard, not flat connection registry
- `tests/test_spawn_manager.py`, `tests/harness/test_extraction.py`, `tests/harness/test_adapter_ownership.py`, `tests/harness/test_launch_spec_parity.py` — bootstrap, extraction, and import-order coverage

## Dependencies

- Requires: Phases 1-6
- Produces: authoritative package bootstrap and extractor parity for Phase 8
- Independent of: final lifecycle/error-path convergence

## Constraints

- `harness/__init__.py` import order is load-bearing and must be documented inline.
- Projection drift checks must execute at package load, not after the first spawn.
- Retired `S037` remains owned here and must stay `retired`; do not reintroduce reserved-flag stripping under a new name.

## Verification Criteria

- `uv run pytest-llm tests/test_spawn_manager.py`
- `uv run pytest-llm tests/harness/test_extraction.py`
- `uv run pytest-llm tests/harness/test_launch_spec_parity.py`
- Fresh-interpreter import test for `meridian.lib.harness`

## Scenarios to Verify

- `S002`
- `S030`
- `S031`
- `S033`
- `S037` (`retired`; keep status as `retired`)
- `S039`
- `S043`
- `S044`
- `S045`
- `S047`
- `S049`
- `S050`

Phase cannot close until every non-retired scenario above is marked `verified` in `scenarios/`, and `S037` remains `retired`.

## Agent Staffing

- `@coder` on `gpt-5.3-codex`
- `@verifier` on `gpt-5.4-mini`
- `@unit-tester` on `gpt-5.4`
- `@smoke-tester` on `claude-opus-4-6`
- Escalate to `@reviewer` on `gpt-5.4` for import-topology, dispatch, or extractor-bootstrap regressions
