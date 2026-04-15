# Phase 1 — Defensive Reconciler Hardening

Implement per `$MERIDIAN_WORK_DIR/plan/phase-1-defensive-reconciler-hardening.md`. Authoritative contracts: `design/spec/overview.md` (S-RN-004, S-RN-006, S-RP-001, S-RP-006, S-RP-007, S-RP-009, S-OB-002), `design/architecture/overview.md` §§"Depth gating", "Runner periodic heartbeat", "Decide / write split".

## What you ship

1. **R-05 depth gate inside `reconcile_active_spawn`**
   - Move `MERIDIAN_DEPTH > 0` short-circuit to the top of `reconcile_active_spawn(state_root, record)` in `src/meridian/lib/state/reaper.py`.
   - Remove any existing independent gate at the batch `reconcile_spawns` wrapper so coverage comes from one place.
   - `ops/diag.py:145`'s existing gate STAYS (S-RP-007 — separate code path).

2. **R-06 runner-owned heartbeat**
   - In `src/meridian/lib/launch/runner.py` and `src/meridian/lib/launch/streaming_runner.py`: start a periodic task that touches `<spawn_dir>/heartbeat` every 30s. Initial touch at `mark_spawn_running` entry (not after first tick). Cancel + await from an outer `finally` that wraps harness execution and the terminal `finalize_spawn` call. If `finalize_spawn` raises, heartbeat still terminates.
   - Inline helper in each runner module — NO new `launch/heartbeat.py` (D-18).
   - In `src/meridian/lib/state/reaper.py`, add `_recent_runner_activity(state_root, spawn_id, now)` checking `heartbeat` (primary) + `output.jsonl`/`stderr.log`/`report.md` (fallback) mtimes within `_HEARTBEAT_WINDOW_SECS = 120`. `reconcile_active_spawn` short-circuits to Skip when recent activity is detected, regardless of `psutil.pid_exists`.
   - Keep the helper isolable (F8).

3. **R-04 partial — decide/write split scaffolding**
   - Extract `decide_reconciliation(record, snapshot, now)` returning `Skip | FinalizeFailed(error) | FinalizeSucceededFromReport` (algebraic type via dataclasses or Union).
   - Extract `_collect_artifact_snapshot(state_root, record, now)` populating `ArtifactSnapshot(started_epoch, last_activity_epoch, durable_report_completion, runner_pid_alive)`.
   - I/O shell (`reconcile_active_spawn`) becomes: depth gate → is_active short-circuit → snapshot → decider → dispatch. Heartbeat gating + any finalizing-specific branches live in the decider.
   - This phase lands ONLY the `running`-side branches; Phase 5 adds `finalizing` branches.

4. **Observability (S-OB-002)** — `_finalize_and_log` logs `heartbeat_window_secs`, `last_activity_epoch`, and which artifact (if any) satisfied the recent-activity check.

## Do NOT ship in this phase

- `finalizing` status literal, `mark_finalizing`, `origin`/`terminal_origin` schema fields, `SpawnOrigin` enum, projection authority rule, reconciler admissibility guard, consumer audit — these all belong to Phases 2–5.

## Tests to land

- `tests/test_state/test_reaper.py` — unit tests for `decide_reconciliation` covering: recent heartbeat = Skip; stale heartbeat + runner_pid_alive=False = FinalizeFailed(orphan_run); durable report = FinalizeSucceededFromReport; MERIDIAN_DEPTH gating at shell; helper isolation.
- `tests/exec/test_streaming_runner.py` + `tests/exec/test_lifecycle.py` — heartbeat task starts on `running`, ticks at ≤30s, cancels on finalize path including when finalize raises.
- `tests/smoke/spawn/lifecycle.md`, `tests/smoke/state-integrity.md` — manual guides: nested-read test (child spawn does `meridian spawn list` at depth>0 — NO orphan stamped); SIGKILL-runner test (after 120s past last heartbeat, reaper stamps orphan_run).

## Constraints

- Edits confined to `src/meridian/lib/state/reaper.py`, `src/meridian/lib/launch/runner.py`, `src/meridian/lib/launch/streaming_runner.py`, and the test/smoke paths above.
- `uv run ruff check .` and `uv run pyright` must be clean.
- `uv run pytest-llm tests/test_state/ tests/exec/` must pass.
- Use `uv run meridian` for any local smoke verification; `--approval yolo` on any spawn tests you run.

## Deliverables

List: files changed, tests added, verification commands run, and any judgement calls logged to `$MERIDIAN_WORK_DIR/decisions.md`.
