# Phase 3: Read-Path Visibility and Cleanup

## Round

3 (parallel with Phase 4)

## Scope

Remove the remaining runtime-artifact cleanup abstraction from read paths and expose the exited-but-not-finalized lifecycle state through `spawn show`, `spawn list`, and `spawn wait` outputs. This phase owns operator-facing visibility and dead cleanup-path deletion.

## Boundaries

- Modify only read-path and formatting code plus `spawn_store.py` cleanup helpers.
- Do not change launch behavior or the reaper’s reconciliation logic; this phase consumes the new lifecycle data, it does not produce or reconcile it.
- Keep `spawn wait` terminal behavior unchanged: it still waits for `finalize`, not `exited`.

## Touched Files and Modules

- `src/meridian/lib/state/spawn_store.py`
- `src/meridian/lib/ops/spawn/query.py`
- `src/meridian/lib/ops/spawn/models.py`
- `src/meridian/lib/ops/spawn/api.py`
- `src/meridian/cli/doctor_cmd.py`
- `tests/ops/test_query.py`
- `tests/ops/test_spawn_read_reconcile.py`
- `tests/test_cli_spawn.py`
- `tests/smoke/spawn/lifecycle.md`

## Claimed EARS Statement IDs

- SLR-18
- SLR-19
- SLR-26
- SLR-27
- SLR-28

## Touched Refactor IDs

- RF-5

## Dependencies

- Phase 1
- Phase 2

## Tester Lanes

- `@verifier`: run focused lint/type/test checks for query, model, and API read paths.
- `@unit-tester`: add or extend output-shaping tests for exited-state annotations and for removal of cleanup-helper assumptions.
- `@smoke-tester`: validate real `spawn show`, `spawn list`, and `spawn wait` output using the lifecycle smoke guide, including the exited-but-not-finalized sub-state.

## Exit Criteria

- `_TERMINAL_RUNTIME_ARTIFACTS` and `cleanup_terminal_spawn_runtime_artifacts()` are removed, and no read path still assumes runtime PID or heartbeat files exist.
- `spawn show` renders `running (exited N, awaiting finalization)` when `exited_at` exists without `finalize`.
- `spawn list` keeps such spawns in `running` status while surfacing a visible exited sub-state indicator.
- `spawn wait` still blocks on `finalize` by default and reports the enriched lifecycle data without introducing an `--on-exit` behavior in this change.
- Doctor/help text no longer describes stale-heartbeat repair as active behavior.

## Verification Commands

- `uv run ruff check src/meridian/lib/ops/spawn src/meridian/lib/state/spawn_store.py src/meridian/cli/doctor_cmd.py tests/ops/test_query.py tests/ops/test_spawn_read_reconcile.py tests/test_cli_spawn.py`
- `uv run pyright`
- `uv run pytest-llm tests/ops/test_query.py tests/ops/test_spawn_read_reconcile.py tests/test_cli_spawn.py`
- Follow `tests/smoke/spawn/lifecycle.md`

## Risks to Watch

- Reintroducing cleanup logic that silently tolerates runtime files instead of deleting the abstraction.
- Exposing exited-state annotations in text mode but not JSON mode, or vice versa.
- Accidentally changing `spawn wait` completion semantics while adjusting display output.
