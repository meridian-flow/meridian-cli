# Refactor Agenda — Round 2

Widened from Round 1. The user was explicit: "if we need to refactor, we should
refactor. I don't want dead code or patchy stuff that is not good code." The
fix lives in the state layer; the refactor agenda supports landing it cleanly.

Every entry either unlocks the mechanism or removes dead surface that the
mechanism would otherwise preserve by accident.

## R-01 — Widen `SpawnStatus` + centralize active/terminal membership

Scope:

- `src/meridian/lib/core/domain.py`: `SpawnStatus` literal gains `"finalizing"`.
- `src/meridian/lib/core/spawn_lifecycle.py`:
  - `ACTIVE_SPAWN_STATUSES` gains `"finalizing"`.
  - `_ALLOWED_TRANSITIONS` gains the `finalizing` row (transitions from
    `finalizing` to each terminal; `running` gains `finalizing` target).
  - `validate_transition` (currently dead) gets wired into `mark_finalizing`,
    `mark_spawn_running`, and the `finalize_spawn` admissibility check.
- Every status-aware consumer updates in lockstep:
  - `cli/spawn.py:453` — `view_map["active"]` derived from
    `ACTIVE_SPAWN_STATUSES`, not a duplicated tuple.
  - `cli/spawn.py:468` — `--status` validator uses `get_args(SpawnStatus)`
    (or equivalent), not a hard-coded set.
  - `cli/spawn.py:54` — post-launch status check treats `finalizing` as a
    valid non-error state returned from the immediate launch path.
  - `lib/ops/spawn/api.py:284-316` — `get_spawn_stats` counts `finalizing`
    alongside `running` under the active umbrella; exposes it on the
    returned stats row.
  - `lib/ops/spawn/models.py:189,196,206,391` — stats model fields carry a
    `finalizing` bucket and the formatter renders `finalizing` directly
    instead of deriving a lifecycle label from other fields.

This is **implementation scope** for shipping `finalizing`, not prep. R-01 is
not complete until every active-set or status-literal consumer has been
updated and the tests cover `finalizing` in each.

## R-02 — Mandatory `origin` on `finalize_spawn`; retire `update_spawn(status=...)`

Scope:

- `src/meridian/lib/state/spawn_store.py`:
  - `SpawnFinalizeEvent.origin: SpawnOrigin | None` (schema field; `None` only
    for legacy pre-field rows).
  - `SpawnRecord.terminal_origin: SpawnOrigin | None` (derived by projection).
  - `finalize_spawn(..., origin: SpawnOrigin)` — mandatory keyword arg, no
    default.
  - `AUTHORITATIVE_ORIGINS` and `LEGACY_RECONCILER_ERRORS` frozensets.
  - `resolve_finalize_origin(event)` — the sole legacy backfill shim.
- Eleven writer sites updated (see architecture writer map).
- `update_spawn(status=...)` is demoted: the `status` kwarg stays on the
  `SpawnUpdateEvent` schema (needed for `queued → running` and
  `running → finalizing`) but the public `update_spawn(status=...)` entrypoint
  is removed from the status-transition surface. Only explicit helpers
  transition status:
  - `mark_spawn_running(...)` (exists)
  - `mark_finalizing(...)` (new — R-03)
  This prevents future call sites from bypassing CAS.

## R-03 — `mark_finalizing` CAS helper + reconciler guard in `finalize_spawn`

Scope:

- New `spawn_store.mark_finalizing(state_root, spawn_id) -> bool` that does the
  locked CAS under `spawns.jsonl.flock`: projects current state, appends
  `SpawnUpdateEvent(status="finalizing")` only if status is exactly `running`.
- `finalize_spawn` branches on `origin`: reconciler-origin calls re-read
  projection under the same flock and drop-and-return-`False` only when the
  row is missing or already terminal. `finalizing` writes through so stale
  cleanup rows can be stamped `orphan_finalization`. Authoritative origins
  retain "always append" semantics; authority is resolved by the projection
  rule.
- Projection (`_record_from_events`) enforces "late `SpawnUpdateEvent.status`
  never downgrades a terminal row" (S-PR-006 invariant).

## R-04 — Split `reconcile_active_spawn` into pure decider + I/O shell

Scope:

- Extract pure function `decide_reconciliation(record, snapshot, now) ->
  ReconciliationDecision` returning an algebraic decision type
  (`Skip` | `FinalizeFailed(error)` | `FinalizeSucceededFromReport`).
- Extract `_collect_artifact_snapshot(state_root, record, now)` that does all
  stat + read I/O upfront and packages timestamps such as `started_epoch`
  into `snapshot`.
- I/O shell (`reconcile_active_spawn`) becomes: depth gate, snapshot, decide,
  dispatch to `_finalize_failed` / `_finalize_completed_report` / return
  `record`.
- Delete any monolithic branches made dead by the split. Heartbeat gating and
  finalizing-specific policy live in the decider, not the shell.

This is refactor-as-prep for the new branches landing in R-03 and R-06.
Without the split, those branches compound inside a function already flagged
for mixed concerns.

## R-05 — Depth gate moved into `reconcile_active_spawn`

Scope:

- Move the `MERIDIAN_DEPTH > 0` short-circuit from the proposed `reconcile_spawns`
  wrapper into `reconcile_active_spawn` itself.
- The batch wrapper drops its independent gate; coverage comes "for free"
  through the inner call.
- `read_spawn_row`'s direct `reconcile_active_spawn` call in
  `ops/spawn/query.py:70` inherits the gate automatically (the F3 fix).
- `ops/diag.py:145`'s existing independent gate stays — separate code path.

## R-06 — Runner-owned periodic heartbeat

Scope:

- `src/meridian/lib/launch/runner.py`: start a periodic task on entry to
  `running`, touch `heartbeat` every 30s, and cancel/await the task from an
  outer `finally` that wraps both harness execution and terminal
  `finalize_spawn`.
- `src/meridian/lib/launch/streaming_runner.py`: same change.
- `src/meridian/lib/state/reaper.py::_recent_runner_activity`: consult the
  `heartbeat` artifact as the primary signal; fall back to
  `output.jsonl`/`stderr.log`/`report.md` mtimes for defense in depth.
- Keep the helper isolated (F8) so a later switch to `scandir` or a single
  consolidated heartbeat artifact is call-site-local.
- Inline helper only in `runner.py` / `streaming_runner.py`; no new
  `launch/heartbeat.py` module in this cycle.

## R-07 — Legacy backfill shim with defined removal window

Scope:

- `resolve_finalize_origin(event)` lives in `spawn_store.py` and is the only
  code path where `error` participates in origin classification.
- `LEGACY_RECONCILER_ERRORS` frozenset is immediately adjacent to the shim.
- Unit test asserts the shim never fires on events that carry an explicit
  `origin` field.
- Documented removal trigger: the shim's `event.origin is None` branch is
  deleted in the first release after `meridian doctor` can confirm that no
  supported state root still contains `origin=None` finalize events. Calendar
  time is not the trigger; state-root evidence is.

## R-08 — `exited_at` field removal remains deferred

After R-09, `exited_at` no longer drives lifecycle classification anywhere in
the active code path. The field itself still survives for telemetry, audit, and
other non-classification consumers, including `process.py` bookkeeping.

Not deleted now. Recorded here as a later-cycle removal candidate, dependent on
(a) all active rows having passed through `finalizing` under the new protocol,
and (b) a review of other `exited_at` consumers.

## R-09 — Delete `exited_at`-driven lifecycle semantics now

Scope:

- `src/meridian/lib/ops/spawn/api.py:200` — delete the `running` +
  `exited_at` lifecycle label heuristic.
- `src/meridian/lib/ops/spawn/models.py:391` — delete the "awaiting
  finalization" formatter heuristic and render literal `finalizing`.
- `src/meridian/lib/state/reaper.py:103` — stop consulting `exited_at` for
  `orphan_run` vs `orphan_finalization` classification; use `status` only.
- Raw `exited_at` stays on the record for telemetry/audit. R-09 removes
  semantics, not the field.

## What is explicitly not in scope

- Rewriting `is_process_alive` for sandbox / namespace opacity. The runner
  heartbeat makes this probe non-load-bearing; a probe-layer rewrite is a
  bigger, independent piece of work.
- Collapsing the nine `reconcile_spawns` call sites into a shared helper.
  Gating at `reconcile_active_spawn` obviates that churn.
- Rewriting the projection as an explicit state machine. The event-reduction
  loop is the right abstraction; `_apply_finalize` and the
  `SpawnUpdateEvent.status` invariant fit within it.
- Streaming / app-server / launch-failure / cancel writers opting into the
  `finalizing` lifecycle. Their outcomes are already derived from direct
  observation; no post-exit drain window exists for them to protect.

## Sequencing preference

p1732 recommended PR1 = Fix A + depth gate (small, defensive) and PR2 = Fix B +
projection + consumer audit (structural). Round 2 is compatible with that
split but does not mandate it. Specifically:

- R-05 (depth gate) + the runner-heartbeat mtime-fallback + the basic stat
  helper can ship as PR1 — zero schema changes.
- R-01, R-02, R-03, R-04, R-06's full heartbeat task, R-07, and R-09 ship
  together as PR2 — they cross-reference and would partially work alone.

The planner owns the exact split; the design package is one coherent artifact.
