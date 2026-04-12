# Phase 4: Reaper Simplification

## Round

3 (parallel with Phase 3)

## Scope

Replace the existing state-machine reaper with the new trivial liveness guard that branches only on whether `exited` exists. This phase owns orphan classification, startup grace retention, and the removal of PID-file and heartbeat-based reconciliation logic.

## Boundaries

- Modify only reconciliation code and its direct tests.
- Assume the new-style event stream from Phases 1 and 2 is authoritative; do not add legacy fallback paths for old spawn records.
- Do not change CLI display or spawn-store schema here unless a reaper test exposes a strict contract mismatch owned by this phase.

## Touched Files and Modules

- `src/meridian/lib/state/reaper.py`
- `tests/test_state/test_reaper.py`
- `tests/ops/test_spawn_read_reconcile.py`
- `tests/smoke/state-integrity.md`

## Claimed EARS Statement IDs

- SLR-6
- SLR-7
- SLR-8
- SLR-9
- SLR-10
- SLR-20
- SLR-23
- SLR-31
- SLR-34

## Touched Refactor IDs

- RF-6

## Dependencies

- Phase 1
- Phase 2

## Tester Lanes

- `@verifier`: run focused lint/type checks and read-path reconciliation tests.
- `@unit-tester`: replace state-machine-oriented tests with direct pre-exit/post-exit liveness cases, including `orphan_run` vs `orphan_finalization`.
- `@smoke-tester`: exercise reconciliation through real read paths so `spawn show`, `spawn list`, and `doctor` all trigger the simplified reaper against live state.

## Exit Criteria

- `reconcile_active_spawn()` uses only event-stream PID fields and `psutil` liveness checks; it no longer reads PID files, heartbeat mtimes, or launch-mode-derived filesystem markers.
- Pre-exit active spawns retain startup grace and fail as `orphan_run` only when the responsible process is dead after grace.
- Post-exit active spawns check `runner_pid` or background wrapper liveness, stay `running` while that process is alive, and resolve to durable-report success or `orphan_finalization` when it dies.
- No heartbeat staleness thresholds or stale-harness error paths remain.
- The reaper logic body stays under the intended trivial size constraint instead of recreating the old state machine under new names.

## Verification Commands

- `uv run ruff check src/meridian/lib/state/reaper.py tests/test_state/test_reaper.py tests/ops/test_spawn_read_reconcile.py`
- `uv run pyright`
- `uv run pytest-llm tests/test_state/test_reaper.py tests/ops/test_spawn_read_reconcile.py`
- Follow `tests/smoke/state-integrity.md`

## Risks to Watch

- Leaving one hidden PID-file or heartbeat fallback behind and silently preserving the old state machine.
- Using `worker_pid` after `exited` instead of `runner_pid` or `wrapper_pid`.
- Reintroducing timing heuristics in the post-exit branch instead of treating `exited` as definitive.
