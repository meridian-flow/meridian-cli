# orphan_run false-failure investigation

> **Archived investigation context.** This document traces the root-cause analysis for issue #14. The "Current reaper logic" and "Resolution" sections reflect intermediate rearchitecture, not the final shipped state. For current reaper logic, lifecycle states, and projection rules see `state/spawns.md`.

## Summary

Tracked issue: `meridian-flow/meridian-cli#14` ("Bug: reaper can stamp orphan_run during post-exit pipe drain")

`p1579` was marked `failed / orphan_run` by read-path reconciliation before its normal runner path finished finalization. The persisted event stream shows:

- `start` at `2026-04-12T13:32:11Z`
- `finalize failed / orphan_run` at `2026-04-12T13:34:06Z`
- `finalize succeeded` at `2026-04-12T13:48:42Z`

The later success did not repair the earlier failure because spawn projection is **first-terminal-event-wins**.

The durable report predicate is not the bug. `p1579/report.md` is plain markdown and matches `has_durable_report_completion()` immediately once it exists. The failure is the reaper deciding the spawn was orphaned during the runner's post-exit drain/finalization window, before `report.md` had been written.

## Reaper logic at time of investigation (pre-issue-#14 fix)

> Describes the intermediate state at investigation time. Issue #14 PR1+PR2 changed this further — see `state/spawns.md` for current logic.

The old 500-line state machine was replaced by a single `reconcile_active_spawn()` function (~60 lines) in `src/meridian/lib/state/reaper.py`. That rearchitecture eliminated PID files, launch-mode dispatch, and staleness heuristics — but the heartbeat and `finalizing` state were not yet present.

`reconcile_active_spawn(state_root, record)` checks one active spawn:

1. **No runner_pid or invalid**: if within startup grace (15s of `started_at`) → wait; otherwise → `missing_worker_pid`.

2. **`is_process_alive(runner_pid, created_after_epoch=started_epoch)` returns true**: runner is still up — keep running.

3. **runner_pid dead, `exited_at` is None** (no exited event recorded): runner died before harness even exited.
   - If startup grace active → wait.
   - If durable report present → finalize succeeded.
   - Otherwise → `orphan_run`.

4. **runner_pid dead, `exited_at` is set**: harness exited (exited event recorded), runner died during post-exit finalization (pipe drain, report extraction, artifact persistence).
   - If durable report present → finalize succeeded.
   - Otherwise → `orphan_finalization`.

`liveness.py:is_process_alive(pid, created_after_epoch)` uses psutil for cross-platform liveness with PID-reuse detection via `proc.create_time()`.

### Error codes

| Error code | Meaning |
|---|---|
| `orphan_run` | Runner and harness both dead, no exited event, no report — crash before any exit processing |
| `orphan_finalization` | Runner dead after exited event, no report — crash during post-exit finalization |
| `missing_worker_pid` | No runner_pid recorded, startup grace elapsed — launch failure |

`orphan_stale_harness` no longer exists as of this rearchitecture. Note: at the time of writing this section, heartbeat files were not yet present. Issue #14 PR1 later re-introduced runner-owned heartbeats as a first-class liveness mechanism (see "Resolution" section and `state/spawns.md`).

## Why `p1579` matched the report predicate

`has_durable_report_completion()` returns true for any non-empty report text that is not a terminal control frame.

It rejects only JSON payloads whose event name is `cancelled` or `error`:

- `src/meridian/lib/core/spawn_lifecycle.py:32-64`

`p1579/report.md` is:

```md
# Auto-extracted Report

Implementation complete. Both phases executed in parallel, all 11 EARS statements verified, 475 tests passing, committed as `a063ae8`.
```

That is plain markdown, so the predicate returns `true`.

The file timestamp also matches the final success event:

- `report.md` mtime: `2026-04-12 08:48:42 -0500`
- `output.jsonl` mtime: `2026-04-12 08:48:42 -0500`

That is consistent with the report being written only at the end of the real run, not at the time of the false failure.

## What actually caused the false failure

The root cause is a race between read-path reconciliation and the runner's post-exit finalization work.

The runner finalizes only after:

1. the subprocess exits,
2. stdout/stderr are drained,
3. report extraction runs,
4. `report.md` is persisted,
5. the terminal spawn record is appended.

Relevant code:

- `src/meridian/lib/launch/runner.py:288-380`
- `src/meridian/lib/launch/runner.py:823-850`
- `src/meridian/lib/launch/process.py:399-430`

The key detail is that Meridian deliberately separates "the tracked child PID exited" from "all inherited pipes are drained". `wait_for_process_returncode()` explicitly polls `process.returncode` instead of awaiting `process.wait()` because descendants may inherit stdout/stderr and keep those pipes open after the tracked PID exits:

- `src/meridian/lib/launch/timeout.py:21-46`
- `src/meridian/lib/launch/runner.py:346-399`

That means this state is expected and supported:

- the harness PID (recorded in spawn events) is dead
- the runner is still alive
- stdout/stderr drain tasks are still in progress
- `report.md` does not exist yet
- final `finalize_spawn(...)` has not happened yet

The reaper has no notion of "finalization in progress". Once it sees:

- no durable report yet, and
- dead harness / wrapper, and
- grace elapsed,

it stamps `orphan_run` immediately.

That is exactly the hole that hit `p1579`: the tracked foreground PID was already dead, but the authoritative runner path was still draining output and had not yet persisted the report.

### Why the later success could not repair it

`spawn_store._record_from_events()` is explicitly first-terminal-event-wins:

- once a record is terminal, later finalize events cannot change `status`, `exit_code`, or `error`

Relevant code:

- `src/meridian/lib/state/spawn_store.py:468-518`

So the later `succeeded` event from the runner was appended, but the projection kept the earlier `failed / orphan_run` terminal state.

That is why `meridian spawn show` kept reporting the failure even though the successful finalize event exists in `spawns.jsonl`.

## p1579 timeline

The persisted events for `p1579` show:

- `start` at `7802`
- `running` update at `7805`
- `failed / orphan_run` at `7812`
- `harness_session_id` update at `7843`
- `succeeded` finalize at `7844`

Relevant file:

- `.meridian/spawns.jsonl:7802-7844`

Important detail: the stored launch mode on the start event is `foreground`, even though the task prompt described the run as background-oriented. So the foreground reconcile path is the one that actually misclassified this spawn record.

## Is issue #10 the same root cause?

Issue #10 says: "`meridian --json spawn wait <id>` returns `succeeded`, but a subsequent `meridian spawn show <id>` still reports `running` even though `finished_at` is populated."

Current code paths:

- `spawn_wait_sync()` polls `read_spawn_row()` until it sees a terminal row
- `spawn_show_sync()` also reads the row through `read_spawn_row()`
- `read_spawn_row()` runs the same read-path reconciliation for active rows

Relevant code:

- `src/meridian/lib/ops/spawn/api.py:615-682`
- `src/meridian/lib/ops/spawn/query.py:67-73`

So in the current tree, `wait` and `show` are supposed to converge on the same persisted row state.

My conclusion:

- Same family: yes. Both are state-reporting inconsistencies around terminalization/reconciliation timing.
- Same exact root cause: not proven, and probably not. `p1579` is specifically a premature `orphan_run` finalize during post-exit pipe drain. Issue #10 describes the opposite polarity: a row that stayed active after a terminal result had already been observed.

In other words, both bugs point at lifecycle ambiguity around finalization, but `p1579` gives a concrete root cause that is narrower than the symptom reported in #10.

## Resolution (issue #14 PR1 + PR2 + final-review)

The shipped fix has two complementary layers. See `state/spawns.md` for full current spec.

**Fix A — Heartbeat + depth gate (PR1)**

`runner.py` writes a `heartbeat` artifact every 30s starting when the worker process/connection starts (inside the `running` transition) and continuing through `finalizing`. It does not cover the `queued` interval before the worker starts. The reaper uses this as its primary liveness signal — any artifact in `{heartbeat, output.jsonl, stderr.log, report.md}` touched within 120s suppresses reconciliation. The reaper also short-circuits when `MERIDIAN_DEPTH > 0` so nested spawns never reap their siblings. Fix A protects the `running` state against psutil false-negatives (the direct trigger for p1579).

**Fix B — `finalizing` lifecycle state (PR2)**

A new `finalizing` status is inserted between `running` and terminal. `mark_finalizing(state_root, spawn_id)` is a CAS helper that transitions `running → finalizing` under the spawns flock after harness exit. Spawns in `finalizing` are heartbeat-gated only (psutil liveness not consulted). The reaper classifies stale `finalizing` rows as `orphan_finalization` — a lifecycle fact, not an `exited_at` heuristic. Fix B protects the post-exit drain window structurally.

**Projection authority rule**

The projection model changed from first-terminal-event-wins to authority-based: `AUTHORITATIVE_ORIGINS = {“runner”, “launcher”, “launch_failure”, “cancel”}` can overwrite a prior `reconciler`-origin terminal. This is the recovery path for existing poisoned rows — if the runner reports after a reaper stamp, the runner wins. Authoritative-vs-authoritative races remain first-wins.

**Legacy row shim**

Existing rows without an `origin` field are classified via `resolve_finalize_origin()` using `LEGACY_RECONCILER_ERRORS`. This allows the authority rule to self-repair historical poisoned rows without a migration.

The fix prevents premature reaps (Fix A + Fix B) and provides a recovery path when prevention fails (authority rule).

## Bottom line

`p1579` was not a bad report parse. It was a lifecycle race.

The reaper finalized `orphan_run` while the runner was still finishing post-exit work, and the later success could not override the first terminal event in the event log.

The real fix is to model finalization explicitly instead of inferring failure from a dead child plus a missing report.
