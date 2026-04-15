# Technical Architecture — Round 2

Realization of the spec contract. Round 2 replaces Round 1's heuristic-driven
origin inference, non-atomic `running → finalizing` transition, half-covered
depth gate, and unprobed heartbeat threshold with explicit mechanism at each
layer. Two architect memos ground the decisions below:

- `../../arch-cas-memo.md` — CAS protocol and write-path guard semantics.
- `../../arch-origin-memo.md` — origin enum, writer mapping, projection authority.
- `../../probe-heartbeat.md` — per-harness silence-gap evidence.

## Modules touched

| Layer | Module | Purpose |
|---|---|---|
| Core lifecycle | `src/meridian/lib/core/spawn_lifecycle.py` | Add `finalizing` to `ACTIVE_SPAWN_STATUSES` and `_ALLOWED_TRANSITIONS`. Wire `validate_transition` into the new helpers (currently unused — dead code). |
| Core domain | `src/meridian/lib/core/domain.py` | Widen `SpawnStatus` literal to include `"finalizing"`. |
| State / event store | `src/meridian/lib/state/spawn_store.py` | Event schema (`origin`), `mark_finalizing` CAS helper, `finalize_spawn(origin=...)` guard, projection authority rule + `terminal_origin`, legacy backfill shim. |
| State / reaper | `src/meridian/lib/state/reaper.py` | Heartbeat window (primary = `heartbeat` artifact), depth gate moved into `reconcile_active_spawn`, decide/write split, reconciler-origin tagging, CAS-miss logging. |
| Runner (primary) | `src/meridian/lib/launch/runner.py` | Periodic heartbeat task (30s tick), `mark_finalizing` call on `finally:` entry, `origin="runner"` on finalize. |
| Runner (streaming) | `src/meridian/lib/launch/streaming_runner.py` | Same three changes as primary runner. |
| Other terminal writers | `src/meridian/lib/launch/process.py`, `src/meridian/cli/streaming_serve.py`, `src/meridian/lib/app/server.py`, `src/meridian/lib/ops/spawn/execute.py` (×3), `src/meridian/lib/ops/spawn/api.py` (cancel) | Pass explicit `origin` on every `finalize_spawn` call. |
| CLI / ops | `src/meridian/cli/spawn.py`, `src/meridian/lib/ops/spawn/api.py`, `src/meridian/lib/ops/spawn/models.py` | Derive active/terminal sets from `spawn_lifecycle` constants; accept `finalizing` in filters; count and render `finalizing` as first-class state. |
| Observability | `src/meridian/lib/ops/spawn/models.py`, `src/meridian/cli/spawn.py` | Branch on `error == "orphan_finalization"` for the distinct rendering and treat `finalizing` as the source-of-truth post-exit state. |

No new modules. No new files.

## Origin tagging — single axis, five labels (F1, F5)

### Enum and authority set

```python
# spawn_store.py (co-located with SpawnFinalizeEvent)
SpawnOrigin = Literal["runner", "launcher", "launch_failure", "cancel", "reconciler"]

AUTHORITATIVE_ORIGINS: frozenset[SpawnOrigin] = frozenset({
    "runner", "launcher", "launch_failure", "cancel",
})
```

`origin` is persisted on `SpawnFinalizeEvent`. The axis that matters for
projection is **authoritative vs. reconciler**; the finer labels exist for
observability and debuggability. `runner`/`launcher` are distinguished by
epistemic position (inner runner loop vs. outer control surface); `launch_failure`
captures the pre-execution boundary; `cancel` preserves user-driven
cancellation as its own category.

### Event schema deltas

```python
class SpawnFinalizeEvent(BaseModel):
    # ... existing fields ...
    origin: SpawnOrigin | None = None    # None only for legacy pre-field rows

class SpawnRecord(BaseModel):
    # ... existing fields ...
    terminal_origin: SpawnOrigin | None = None   # derived by projection at terminalization
```

New writes shall not pass `None`. `finalize_spawn` requires `origin` as a
mandatory keyword argument (no default).

### Complete writer map

| Writer (path:line) | `origin` | Authoritative | Notes |
|---|---|:---:|---|
| `lib/launch/runner.py:851` | `runner` | yes | Primary runner finalize from direct exit/report/usage evidence. |
| `lib/launch/streaming_runner.py:1184` | `runner` | yes | Streaming runner finalize; same epistemic position as primary. |
| `lib/launch/process.py:426` | `launcher` | yes | Outer process wrapper finalizing primary spawn from observed harness exit. |
| `cli/streaming_serve.py:115` | `launcher` | yes | CLI streaming controller finalize on observed outcome. |
| `lib/app/server.py:145` | `launcher` | yes | App server background finalize awaiting `spawn_manager.wait_for_completion`. |
| `lib/app/server.py:256` | `launch_failure` | yes | API launch failed before the run started normally. |
| `lib/ops/spawn/execute.py:578` | `launch_failure` | yes | Background launch failed while persisting worker params. |
| `lib/ops/spawn/execute.py:637` | `launch_failure` | yes | Background launch failed on `subprocess.Popen`. |
| `lib/ops/spawn/execute.py:881` | `launch_failure` | yes | Background worker failed to load params. |
| `lib/ops/spawn/api.py:493` | `cancel` | yes | User-requested cancel. |
| `lib/state/reaper.py:_finalize_and_log` | `reconciler` | no | Read-path probe — only non-authoritative writer. |

No writer remains on `origin=None` in new code. The projection's legacy shim
(below) handles existing pre-field rows read from disk.

## Atomic `running → finalizing` — CAS protocol (F2)

### `mark_finalizing(state_root, spawn_id) -> bool`

A new helper in `spawn_store.py`:

```python
def mark_finalizing(state_root: Path, spawn_id: SpawnId | str) -> bool:
    paths = StateRootPaths.from_root_dir(state_root)
    with lock_file(paths.spawns_flock):
        records = _record_from_events(read_events(paths.spawns_jsonl, _parse_event))
        record = records.get(str(spawn_id))
        if record is None or record.status != "running":
            return False
        event = SpawnUpdateEvent(id=str(spawn_id), status="finalizing")
        append_event(paths.spawns_jsonl, paths.spawns_flock, event,
                     store_name="spawn", exclude_none=True)
        return True
```

Key properties:

- **Lock scope identical to every other writer** — shares `spawns.jsonl.flock`
  with `finalize_spawn`, `start_spawn`, `update_spawn`.
- **Pre-state strictly `running`** — `queued`, `finalizing`, terminal, or
  missing all return `False`. S-LC-003 forbids `queued → finalizing`.
- **Return `bool`, never raise** — a CAS miss is an expected race, not an
  infrastructure failure. Runner treats `False` as "reconciler got there first;
  projection authority will adjudicate later" (S-LC-006).

### Reconciler re-validation guard on `finalize_spawn` (S-RP-008)

`finalize_spawn` gains the mandatory `origin` parameter. Under the flock, after
the existing projection, if `origin == "reconciler"` and the current record is
missing or already terminal, the event is dropped. A projected `finalizing`
row is **not** dropped: that path is how a stale cleanup window becomes
`orphan_finalization`.

```python
def finalize_spawn(state_root, spawn_id, status, exit_code, *,
                   origin: SpawnOrigin, ...) -> bool:
    paths = StateRootPaths.from_root_dir(state_root)
    with lock_file(paths.spawns_flock):
        records = _record_from_events(read_events(paths.spawns_jsonl, _parse_event))
        record = records.get(str(spawn_id))
        if origin == "reconciler":
            if record is None or record.status in TERMINAL_SPAWN_STATUSES:
                logger.info("Reconciler finalize dropped under CAS",
                            spawn_id=str(spawn_id), current_status=record.status if record else None)
                return False
        was_active = record is not None and is_active_spawn_status(record.status)
        event = SpawnFinalizeEvent(..., origin=origin)
        append_event(...)
        return was_active
```

Authoritative origins retain their current "always append so metadata never
drops" semantics. Authority resolution between a prior reconciler-origin
terminal and a later authoritative-origin terminal is handled by the projection
rule, not by dropping writes. This deliberately leaves `finalizing` inside the
reconciler write-through set so S-RP-002/S-RP-003 can stamp
`orphan_finalization` on genuinely stale cleanup rows.

**Why the guard lives inside `finalize_spawn` and not a separate function**:
one append path per event axis; one flock scope; one place where origin and
admissibility are reconciled; `grep finalize_spawn(` still finds every terminal
writer. A `reconciler_finalize_spawn()` wrapper would duplicate locking and
event construction and invite call-site drift.

## Projection authority rule (F1)

`_record_from_events` in `spawn_store.py` replaces its first-wins branch
(line 534) with an authority-aware variant. The derived record gains
`terminal_origin`, which is the authority key for subsequent decisions:

```python
def _apply_finalize(current, event):
    incoming_origin = resolve_finalize_origin(event)
    incoming_authoritative = incoming_origin in AUTHORITATIVE_ORIGINS
    already_terminal = current.status in _TERMINAL_SPAWN_STATUSES

    if not already_terminal:
        replace = True
    elif current.terminal_origin == "reconciler" and incoming_authoritative:
        replace = True
    else:
        replace = False

    if replace:
        resolved_status = event.status or current.status
        resolved_exit_code = event.exit_code if event.exit_code is not None else current.exit_code
        resolved_error = None if resolved_status == "succeeded" else (
            event.error if event.error is not None else current.error
        )
        resolved_terminal_origin = incoming_origin
    else:
        resolved_status = current.status
        resolved_exit_code = current.exit_code
        resolved_error = current.error
        resolved_terminal_origin = current.terminal_origin

    # metadata (duration, cost, tokens, finished_at) always merges
    return current.model_copy(update={
        "status": resolved_status,
        "exit_code": resolved_exit_code,
        "error": resolved_error,
        "terminal_origin": resolved_terminal_origin,
        "finished_at": event.finished_at if event.finished_at is not None else current.finished_at,
        "duration_secs": event.duration_secs if event.duration_secs is not None else current.duration_secs,
        "total_cost_usd": event.total_cost_usd if event.total_cost_usd is not None else current.total_cost_usd,
        "input_tokens": event.input_tokens if event.input_tokens is not None else current.input_tokens,
        "output_tokens": event.output_tokens if event.output_tokens is not None else current.output_tokens,
    })
```

### Legacy backfill shim (S-PR-003 demoted)

Single isolated helper; only path where `error` may participate in origin
inference:

```python
LEGACY_RECONCILER_ERRORS: frozenset[str] = frozenset({
    "orphan_run", "orphan_finalization", "missing_worker_pid", "harness_completed",
})

def resolve_finalize_origin(event: SpawnFinalizeEvent) -> SpawnOrigin:
    if event.origin is not None:
        return event.origin
    return "reconciler" if event.error in LEGACY_RECONCILER_ERRORS else "runner"
```

The four currently-live incidents (`p1711`, `p1712`, `p1731`, `p1732`) all
have pre-field event streams of the shape `finalize(error=orphan_run, origin=None)
→ finalize(succeeded, error=None, origin=None)`. The shim classifies the first
as `reconciler` (error in set) and the second as `runner` (error None ∉ set), so
the authority rule replaces the terminal tuple correctly on next read.

### Invariant: `SpawnUpdateEvent.status` never downgrades a terminal row
(S-PR-006)

The existing `SpawnUpdateEvent` handler applies `status` unconditionally. New
rule: if `current.status in _TERMINAL_SPAWN_STATUSES`, drop the incoming
status field on the projection but still merge other fields (`work_id`,
`desc`, pid updates, etc.). This closes the last hole where a late
`mark_finalizing` that lost the CAS but somehow appeared in the stream could
visually "downgrade" a terminal.

Authoritative-over-authoritative is intentionally still first-wins. If a
runner finalize lands before a later cancel or launch-failure finalize (or the
reverse), the first authoritative terminal tuple stands; only metadata keeps
merging.

## Depth gating — single-point fan-in (F3)

The gate lives inside `reconcile_active_spawn`, not the batch wrapper:

```python
def reconcile_active_spawn(state_root: Path, record: SpawnRecord) -> SpawnRecord:
    if int(os.getenv("MERIDIAN_DEPTH", "0")) > 0:
        return record
    if not is_active_spawn_status(record.status):
        return record
    # ... rest of reconciliation ...

def reconcile_spawns(state_root, spawns):
    return [reconcile_active_spawn(state_root, s) if is_active_spawn_status(s.status) else s
            for s in spawns]
```

Coverage:

- All nine batch entrypoints (`cli/spawn.py:502`, `ops/diag.py:72`,
  `ops/spawn/api.py:157,258`, `ops/spawn/context_ref.py:40`,
  `ops/spawn/query.py:30`, `ops/work_dashboard.py:329,347,394,464`) inherit the
  gate through `reconcile_spawns`.
- The single-row `read_spawn_row` path (`ops/spawn/query.py:70`) calls
  `reconcile_active_spawn` directly — it now also inherits the gate.
- `ops/diag.py:145`'s existing independent `MERIDIAN_DEPTH` skip is preserved
  (separate, non-reconcile code path).

The batch wrapper carries no independent gate. One place to grep for the
policy.

## Runner periodic heartbeat (F4)

Evidence from `../../probe-heartbeat.md`:

- Claude: max observed inter-event gap **153.9s** during a healthy run.
- Codex: max observed inter-event gap **86.8s**.
- OpenCode: no keepalive; SSE yields only on chunk arrival.

A 120s window keyed on harness-output mtime alone is **unsafe** for `running`.
The runner must produce its own heartbeat independent of harness output.

### Design

The runner event loop schedules a periodic task that touches
`<spawn_dir>/heartbeat` every 30 seconds. Tick cadence relative to window:

- Tick interval: 30s
- Reaper window: 120s
- Safety factor: 4× (three missed ticks before a false positive).

Startup / shutdown:

- The heartbeat task starts no later than the moment the runner records
  `status=running` (after `mark_spawn_running`). Initial touch happens at
  startup, not after first tick, so zero-activity startup windows are still
  covered.
- The task continues through `finalizing` (bracketed by the `mark_finalizing`
  call and the terminal `finalize_spawn` write in the same `finally:` block).
- The task is cancelled and awaited from an outer `finally:` that wraps both
  harness execution and the terminal `finalize_spawn` call. If
  `finalize_spawn` raises, the heartbeat task still terminates before control
  leaves the runner frame.
- Both the primary runner (`runner.py`) and streaming runner
  (`streaming_runner.py`) implement the same pattern with an inline helper in
  the existing runner modules. No new heartbeat module is introduced in this
  cycle; the contract is S-RN-004 / S-RN-006.

```python
heartbeat_task = start_heartbeat_task(...)
try:
    try:
        run_harness(...)
    finally:
        mark_finalizing(...)
        finalize_spawn(..., origin="runner")
finally:
    cancel_and_await(heartbeat_task)
```

### Reaper activity check

`_recent_runner_activity(state_root, spawn_id, now)` consults, in order:

1. `heartbeat` mtime (primary signal).
2. `output.jsonl`, `stderr.log`, `report.md` mtimes (defense in depth for
   pre-heartbeat legacy rows and against a hung heartbeat task with a live
   harness still emitting).

Any artifact modified within `_HEARTBEAT_WINDOW_SECS = 120` returns `True`.
The helper is isolated (F8 — keep it easy to switch to `scandir` or a single
consolidated heartbeat artifact without reworking callers).

## Decide / write split (F7)

`reconcile_active_spawn` currently interleaves classification, artifact
reads, liveness probing, event emission, and logging. The new shape is two
halves:

### `ArtifactSnapshot`

```python
@dataclass(frozen=True)
class ArtifactSnapshot:
    started_epoch: float | None
    last_activity_epoch: float | None       # max mtime across heartbeat/output.jsonl/stderr.log/report.md
    durable_report_completion: bool
    runner_pid_alive: bool | None           # None means "not probed" (e.g. finalizing state)
```

### Pure decider

```python
ReconciliationDecision = (
    Skip
    | FinalizeFailed(error: str)
    | FinalizeSucceededFromReport
)

def decide_reconciliation(
    record: SpawnRecord,
    snapshot: ArtifactSnapshot,
    *,
    now: float,
) -> ReconciliationDecision:
    ...
```

The decider encodes:

- Heartbeat-window short-circuit (S-RP-001) as `Skip`.
- Finalizing branch (S-RP-002, S-RP-003) — never consults `runner_pid_alive`.
- Running branch with missing-pid / startup-grace / psutil-dead paths.
- Durable-report precedence (S-RP-004) inside both branches.

### I/O shell

```python
def reconcile_active_spawn(state_root, record):
    if int(os.getenv("MERIDIAN_DEPTH", "0")) > 0:
        return record
    if not is_active_spawn_status(record.status):
        return record
    now = time.time()
    snapshot = _collect_artifact_snapshot(state_root, record, now)
    decision = decide_reconciliation(record, snapshot, now=now)
    return _apply_decision(state_root, record, decision)
```

`_apply_decision` dispatches to `_finalize_failed(...reconciler...)` or
`_finalize_completed_report(...reconciler...)` or returns `record` unchanged.
All reaper writes tag `origin="reconciler"`. S-RP-008 (guard in
`finalize_spawn`) protects against the race where the snapshot was stale by
the time we tried to write.

## Consumer surface updates (F6)

Single source of truth for the active set:

- `spawn_lifecycle.ACTIVE_SPAWN_STATUSES = frozenset({"queued", "running", "finalizing"})`.
- `cli/spawn.py` `view_map["active"] = tuple(sorted(ACTIVE_SPAWN_STATUSES))`
  — derived, not duplicated.
- `cli/spawn.py` `--status` validator accepts any value in the `SpawnStatus`
  literal (use `get_args(SpawnStatus)` or equivalent).
- `api.get_spawn_stats` adds a `finalizing` counter bucket alongside
  `running`; `active_count = running + queued + finalizing` where relevant.
- `ops/spawn/models.py:189,196,206,391` is part of the same surface: stats
  model fields carry `finalizing`, and the formatter renders the literal
  `finalizing` state rather than any derived "awaiting finalization" label.
- `api.py:200`, `ops/spawn/models.py:391`, and `state/reaper.py:103` stop
  branching on `exited_at` for lifecycle classification in this cycle.
  `exited_at` survives only as audit/telemetry data.
- `cli/spawn.py:54` treats `finalizing` as a non-error post-launch state.
  The launch command still succeeds; callers that need the eventual terminal
  outcome keep using `spawn show` / `spawn wait` afterward.

### Transition table in `spawn_lifecycle.py`

```python
ACTIVE_SPAWN_STATUSES = frozenset({"queued", "running", "finalizing"})
TERMINAL_SPAWN_STATUSES = frozenset({"succeeded", "failed", "cancelled"})

_ALLOWED_TRANSITIONS = {
    "queued":     frozenset({"running", "succeeded", "failed", "cancelled"}),
    "running":    frozenset({"finalizing", "succeeded", "failed", "cancelled"}),
    "finalizing": frozenset({"succeeded", "failed", "cancelled"}),
}
```

`validate_transition` is currently dead code (no in-tree caller). Wire it into
`mark_finalizing`, `mark_spawn_running`, and `finalize_spawn` — dead lifecycle
validators next to an append-only event store are actively misleading.

## Observability

- `spawn show` status renderer branches on `error == "orphan_finalization"`
  to surface the "harness likely completed — inspect report.md" hint. The same
  renderer treats `finalizing` as the authoritative in-progress post-exit
  state rather than inferring it from `exited_at`.
- `_finalize_and_log` extends its log event with `heartbeat_window_secs`,
  `last_activity_epoch`, and `heartbeat_artifact` (which file satisfied the
  check, if any).
- Reconciler CAS-miss drops (S-RP-008) log at INFO with `spawn_id`,
  `attempted_error`, `current_status` so post-mortems can distinguish "guard
  fired" from "reconciler chose not to act".

## What is deliberately not changed

- `is_process_alive` stays best-effort. The probe-layer opacity problem
  (sandboxed / PID-namespace false negatives) is not fixed at the probe;
  the runner heartbeat makes the probe non-load-bearing for liveness.
- `reconcile_spawns` call graph stays intact — nine batch call sites keep
  their current invocation. The gate lives one layer deeper.
- Crash-only semantics preserved. No in-place JSONL rewrites. The projection
  is the only place where "later event can revise earlier state" logic
  lives, bounded to `authoritative-over-reconciler` and to `SpawnUpdateEvent
  never downgrades terminal`.
- Streaming/app-server/launch-failure/cancel writers keep their current
  direct `running → terminal` semantics. Only the two runner paths opt into
  `running → finalizing → terminal`. Other paths gain the explicit origin
  label but no new lifecycle step.
