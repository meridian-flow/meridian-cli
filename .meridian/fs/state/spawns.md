# Spawn Store

Source: `src/meridian/lib/state/spawn_store.py`, `src/meridian/lib/state/reaper.py`, `src/meridian/lib/state/liveness.py`

## Event Model

Spawns are tracked as an append-only event sequence in `.meridian/spawns.jsonl`. Four event types:

**`start`** — written when spawn is created. Fields include:
- `id` (e.g. `p1`, `p2`), `chat_id`, `parent_id`
- `model`, `agent`, `agent_path`, `skills`, `skill_paths`, `harness`
- `kind` (`"child"` or `"primary"`), `desc`, `work_id`
- `harness_session_id`, `execution_cwd`, `launch_mode`
- `worker_pid`, `runner_pid`, `status` (initial: `"running"` or `"queued"`), `prompt`, `started_at`

`runner_pid` on the start event identifies the foreground/primary runner — the process responsible for post-exit finalization. For foreground spawns this is `os.getpid()` at launch time.

**`update`** — non-terminal state change. Fields: `id`, `status`, `launch_mode`, `wrapper_pid`, `worker_pid`, `runner_pid`, `harness_session_id`, `execution_cwd`, `error`, `desc`, `work_id`.

`runner_pid` on the update event is used for background spawns: the wrapper process PID is recorded here once the background launch stabilizes. **`status=` is not accepted via `update_spawn()` directly** — lifecycle transitions must go through `mark_spawn_running()`, `mark_finalizing()`, or `finalize_spawn()`.

**`exited`** — written immediately when the harness process exits (before report extraction or any post-exit work). Fields: `id`, `exit_code`, `exited_at` (ISO 8601 UTC).

This event is **informational only** — telemetry/audit. The spawn status stays `running` (or `finalizing`) after an `exited` event. `exited_at` must not be used to infer lifecycle state; `status` is authoritative.

**`finalize`** — terminal event. Fields: `id`, `status`, `exit_code`, `finished_at`, `duration_secs`, `total_cost_usd`, `input_tokens`, `output_tokens`, `error`, `origin` (a `SpawnOrigin` value — mandatory on new writes).

`SpawnRecord` is the projection: derived by replaying all events for a spawn ID.

## ID Generation

`next_spawn_id()` counts `start` events in `spawns.jsonl` and returns `p{count+1}`. IDs are sequential and monotonic. Allocation happens under the spawns flock so concurrent spawners don't collide.

## SpawnRecord

`SpawnRecord` is the projection: assembled from all events for a spawn. Key fields:

- `runner_pid` — PID of the process responsible for finalization (sourced from start or update event)
- `exited_at` — timestamp from the `exited` event (None if harness hasn't exited yet)
- `process_exit_code` — raw exit code from the `exited` event (distinct from the `exit_code` in the finalize event, which is the final outcome code)
- All other fields follow from start/update/finalize events

## Terminal Status Merging — Projection Authority Rule

`finalize_spawn()` writes carry a mandatory `origin: SpawnOrigin` field. Origins are classified:

```python
AUTHORITATIVE_ORIGINS = {"runner", "launcher", "launch_failure", "cancel"}
# Non-authoritative: "reconciler"
```

Projection (`_record_from_events`) applies these rules in order:

1. **First-active-wins for all authoritative-vs-authoritative races.** Once an authoritative origin sets the terminal status, a later authoritative finalize cannot overwrite it.
2. **Authoritative overrides reconciler.** If the projected terminal origin is `reconciler` and a later finalize event carries an authoritative origin, the authoritative event wins — it sets the status, exit_code, and error. This is intentional: a runner reporting after the reaper stamped an orphan is strictly more informed and must win.
3. **Reconciler-vs-reconciler: first wins.** Two reconciler calls racing cannot revise each other.

Metadata (duration, cost, tokens) is merged from every finalize event regardless of authority — no writer loses its cost/token contribution.

`finalize_spawn(origin="reconciler")` re-reads the projected row under the spawns flock and drops the append when the row is missing or already terminal — this prevents duplicate terminal writes from concurrent reaper sweeps. Spawns in `finalizing` remain writable by the reconciler so a crashed mid-drain runner can still be closed as `orphan_finalization`.

`finalize_spawn()` returns `True` if this call found the spawn active before writing, `False` if it was already terminal or missing.

**Legacy row shim:** Older finalize events without an explicit `origin` field are classified by `resolve_finalize_origin()`: errors in `{"orphan_run", "orphan_finalization", "missing_worker_pid", "harness_completed"}` → `"reconciler"`, everything else → `"runner"`. New code must always pass `origin=` explicitly.

## Spawn Statuses

Active: `queued`, `running`, `finalizing`
Terminal: `succeeded`, `failed`, `cancelled`

There is no `timeout` status. Timeouts result in `failed` with a timeout-related failure reason.

**Allowed transitions:**
```
queued    → running | succeeded | failed | cancelled
running   → finalizing | succeeded | failed | cancelled
finalizing → succeeded | failed | cancelled
```

`queued → finalizing` is NOT allowed. A cancellation from `queued` goes directly to `cancelled`.

**`mark_finalizing(state_root, spawn_id) -> bool`** is the only CAS writer for `running → finalizing`. It acquires the spawns flock, projects current status, and appends `SpawnUpdateEvent(status="finalizing")` only when the current status is exactly `running`. Returns `True` on success, `False` on CAS miss (non-running or missing row). Failure is non-fatal — the runner logs and continues to the terminal `finalize_spawn()` call. See `launch/process.md` for when the runner calls this.

Presence of an `exited` event does **not** change the spawn's projected status. The spawn stays `running` or `finalizing` until a `finalize` event arrives. `spawn wait` blocks until finalize.

## Reaper (`reaper.py`)

The reaper runs on every read path (`spawn list`, `spawn show`, `spawn wait`, dashboard). It auto-repairs active spawns that have become orphaned. No separate GC command.

**Entry gate:** `reconcile_active_spawn` short-circuits when `MERIDIAN_DEPTH > 0`. Nested invocations (spawns running under a parent) never reap — the parent's process is doing the reconciliation. The gate lives inside `reconcile_active_spawn` so every call site (batch sweeps, single-row reads) inherits it from one place.

**Decide/IO split:** the reaper separates pure computation from I/O.

1. `_collect_artifact_snapshot(state_root, record, now) → ArtifactSnapshot` — pure read. Gathers:
   - `started_epoch` — parsed from `record.started_at`
   - `last_activity_epoch` and `recent_activity_artifact` — freshest mtime across `{"heartbeat", "output.jsonl", "stderr.log", "report.md"}` in the spawn artifact dir
   - `durable_report_completion` — whether `report.md` contains a valid non-error completion marker
   - `runner_pid_alive` — psutil liveness check on `record.runner_pid` (skipped for `finalizing` rows — PID probes are not consulted for drain-phase liveness)

2. `decide_reconciliation(record, snapshot, now) → ReconciliationDecision` — pure function, no I/O. Returns one of `Skip(reason)`, `FinalizeSucceededFromReport`, or `FinalizeFailed(error)`.

3. IO shell applies the decision: calls `finalize_spawn(..., origin="reconciler")` if terminal.

**Decision logic:**

For `status == "finalizing"` (runner entered controlled drain):
- Recent activity (any artifact within 120s): `Skip`
- Stale + durable report: `FinalizeSucceededFromReport`
- Stale + no report: `FinalizeFailed(error="orphan_finalization")`
- PID probe is **not** consulted for `finalizing` rows — heartbeat recency is the sole liveness signal.

For `status == "running"` (or `queued` with no PID):
- `runner_pid` absent/≤0:
  - Recent activity: `Skip`
  - Within 15s startup grace: `Skip`
  - Durable report: `FinalizeSucceededFromReport`
  - Otherwise: `FinalizeFailed(error="missing_worker_pid")`
- `runner_pid` alive: `Skip` (with recency check as defense in depth)
- `runner_pid` dead:
  - Recent activity: `Skip`
  - Within 15s startup grace: `Skip`
  - Durable report: `FinalizeSucceededFromReport`
  - Otherwise: `FinalizeFailed(error="orphan_run")`

**Recency rule:** uniform across all branches — any artifact among `{heartbeat, output.jsonl, stderr.log, report.md}` touched within 120s suppresses reconciliation. The heartbeat is the primary signal (written every 30s by the runner) but the rule is artifact-agnostic so a last-gasp stderr write also buys a grace tick.

**Error codes:**
- `orphan_run` — runner PID dead, no recent activity, no durable report. Runner died during normal execution. Suggests hard kill or OOM.
- `orphan_finalization` — spawn was in `finalizing` state (runner explicitly declared controlled drain) but heartbeat went stale and no durable report. Runner crashed during post-exit processing.
- `missing_worker_pid` — no `runner_pid` recorded, outside startup grace. Spawn started but PID was never committed to the event stream.
- `harness_completed` — legacy; used when reconciler found a durable report but the runner had not yet finalized. Now `FinalizeSucceededFromReport` handles this path.

**`orphan_finalization` vs `orphan_run`:** `orphan_finalization` is much more likely to have useful work product (`report.md` may be partial but present). `spawn show` should surface the distinction explicitly. Both produce terminal `failed` status with `exit_code=1`.

**Key constants:**
- `_STARTUP_GRACE_SECS = 15` — recent spawns with no PID yet are left alone
- `_HEARTBEAT_WINDOW_SECS = 120` — activity within this window suppresses reap
- PID reuse margin = 30s — `is_process_alive()` considers a process reuse if its create_time is more than 30s after `started_at`

## Liveness (`liveness.py`)

`is_process_alive(pid, created_after_epoch)` — psutil-based, cross-platform process liveness check.

- Uses `psutil.pid_exists()` for fast path.
- Retrieves `psutil.Process(pid).create_time()` to guard against PID reuse: if the process was created more than **30 seconds** after `created_after_epoch` (the spawn's `started_at` epoch), it's a different process that reused the PID. The 30s margin (widened from 2s) accounts for background-launch setup delay between spawn start and PID recording.
- Calls `proc.is_running()` as the final liveness confirmation after the PID-reuse guard passes.
- Returns `True` on `psutil.AccessDenied` (process exists, can't inspect — conservatively assume alive).
- Returns `False` on `psutil.NoSuchProcess` (process vanished between `pid_exists` and `Process(pid)` — treat as dead).

Replaces the prior Linux-only `/proc/stat` boot time + clock tick approach. Decision D10: psutil chosen for cross-platform support and built-in `create_time()` PID-reuse detection with no transitive dependencies.

## Artifact Directory

Each spawn gets `.meridian/spawns/<id>/` containing durable artifacts and the runner heartbeat:

- `prompt.md` — the prompt text
- `report.md` — the agent's run report (explicit or auto-extracted)
- `output.jsonl` — raw harness stdout (JSON stream events)
- `stderr.log` — harness stderr, warnings, and errors
- `params.json` — spawn parameters
- `tokens.json` — token usage record
- `heartbeat` — touched by the runner every 30s while active (`running` + `finalizing`). The reaper reads its mtime as the primary liveness signal. Written by `_touch_heartbeat_file()` in `runner.py`.
- `bg-worker-params.json` — background launch parameters (background spawns only)

`spawn files` returns the list of files a spawn created/modified, for use with `xargs git add`.
