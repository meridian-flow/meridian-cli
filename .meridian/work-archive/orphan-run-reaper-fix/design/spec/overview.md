# Behavioral Specification — Round 2

EARS statements are the contract that implementation verifies against. IDs that
survive materially unchanged from Round 1 are preserved. IDs whose mechanism
changed materially are retained (with the letter-code kept) and restated; new
statements carry fresh numbers. The cross-links to architecture live in
`../architecture/overview.md`.

## Lifecycle

- **S-LC-001** — The system shall define `finalizing` as a non-terminal spawn
  status distinct from `queued`, `running`, `succeeded`, `failed`, and
  `cancelled`.
- **S-LC-002** — The system shall include `finalizing` in
  `ACTIVE_SPAWN_STATUSES` (single source of truth in
  `src/meridian/lib/core/spawn_lifecycle.py`) and treat it as active for every
  call site that branches on `is_active_spawn_status` or iterates an
  "active" view.
- **S-LC-003** — The allowed transitions shall be:
  `queued → running | succeeded | failed | cancelled`,
  `running → finalizing | succeeded | failed | cancelled`,
  `finalizing → succeeded | failed | cancelled`. `queued → finalizing` is
  **not** legal. Terminal states have no outgoing transitions.
- **S-LC-004** *(mechanism revised)* — The transition `running → finalizing`
  shall be performed by a locked compare-and-swap helper,
  `spawn_store.mark_finalizing(state_root, spawn_id) -> bool`, that:
  1. Acquires `spawns.jsonl.flock`.
  2. Projects the current state from `spawns.jsonl` under that lock.
  3. Appends a `SpawnUpdateEvent(status="finalizing")` **only when** the
     projected status is exactly `running`.
  4. Returns `True` if the event was appended, `False` on CAS miss (row
     missing, status already `finalizing` or terminal, or not in `running`).
  The lock scope is shared with every other writer of `spawns.jsonl`.
- **S-LC-005** — `finalizing` shall never appear in `spawns.jsonl` as the
  projected terminal state. It is produced only by `mark_finalizing` and
  consumed only by terminal `finalize_spawn` writes.
- **S-LC-006** *(new)* — The runner shall tolerate a `mark_finalizing` CAS
  miss without converting it into an infrastructure failure: if the CAS
  returns `False`, the runner still runs its post-exit work and its final
  `finalize_spawn` call, which may later supersede a prior reconciler-origin
  terminal via the projection authority rule (S-PR-001).

## Runner behaviour

- **S-RN-001** *(mechanism clarified)* — Upon entering the `finalizing`
  lifecycle (the instant `mark_finalizing` returns `True`), the runner shall
  touch the spawn's `heartbeat` artifact so the reaper's activity window
  (S-RP-001) resets at the moment the runner declares controlled cleanup.
- **S-RN-002** *(mechanism revised)* — `spawn_store.finalize_spawn` shall
  require a mandatory `origin: SpawnOrigin` keyword argument. `SpawnOrigin`
  is a closed enum `{"runner", "launcher", "launch_failure", "cancel",
  "reconciler"}`. New writes shall not pass `None`. `origin` is persisted
  on the emitted `SpawnFinalizeEvent`.
- **S-RN-003** — Every runner-origin terminal write shall tag
  `origin="runner"`. Primary runner (`runner.py`) and streaming runner
  (`streaming_runner.py`) share this label (same epistemic position).
- **S-RN-004** *(new — F4 evidence)* — The runner shall emit a periodic
  heartbeat tick (touch `heartbeat` every ≤30s) for the full duration of
  `running` and `finalizing`, independent of harness output cadence. The
  heartbeat task shall start no later than the moment the runner records
  `status=running` and shall stop only after the terminal `finalize_spawn`
  write returns. Evidence for why harness-output cadence is insufficient
  lives in `../feasibility.md`.
- **S-RN-005** *(new)* — The writer-to-origin mapping for all eleven
  `finalize_spawn` sites is defined in `../architecture/overview.md` and is
  part of the contract: no terminal row shall reach `spawns.jsonl` without
  an explicit origin label in new code.
- **S-RN-006** *(new)* — In both `src/meridian/lib/launch/runner.py` and
  `src/meridian/lib/launch/streaming_runner.py`, the heartbeat task shall be
  cancelled from an outer `finally` block that wraps both harness execution
  and the terminal `finalize_spawn` call. If `mark_finalizing` returns
  `False` or `finalize_spawn` raises, the heartbeat task shall still be
  cancelled and awaited before the runner frame exits.

## Reaper — liveness gating

- **S-RP-001** *(broadened)* — `reconcile_active_spawn` shall not stamp any
  terminal state on a spawn whose heartbeat artifact `heartbeat`, or any of
  the supporting artifacts `output.jsonl`, `stderr.log`, `report.md`, was
  modified within the last `_HEARTBEAT_WINDOW_SECS` (default `120`) seconds,
  regardless of `psutil.pid_exists(runner_pid)`. The heartbeat artifact is
  the primary signal (S-RN-004); the others are fallback for pre-heartbeat
  rows and for defense in depth.
- **S-RP-002** — When `record.status == "finalizing"`, the reaper shall not
  consult `psutil.pid_exists` at all. Only elapsed inactivity past
  `_HEARTBEAT_WINDOW_SECS` permits a terminal stamp on a `finalizing` row.
- **S-RP-003** — A reaper-origin terminal stamp on a `finalizing` row shall
  use `error="orphan_finalization"`. `error="orphan_run"` shall only apply
  to rows whose status at the moment of classification is `running` (or
  `queued` beyond the startup grace window).
- **S-RP-004** *(mechanism revised)* — When the reaper detects a durable
  completion report on an active row, it shall project the spawn as
  `succeeded` with `exit_code=0`, `error=None`, **tagged
  `origin="reconciler"`**. Because the authority rule (S-PR-001) keys off
  `origin`, not `error`, a later runner-origin finalize can still supersede
  this reconciler-origin success. This is the mechanism fix for the F1
  blocker.
- **S-RP-005** — Every terminal write from `reaper.py` shall tag
  `origin="reconciler"`. This is the only `reconciler` writer in the
  codebase (single source).
- **S-RP-006** *(coverage revised — F3)* — The `MERIDIAN_DEPTH > 0`
  short-circuit shall live inside `reconcile_active_spawn` itself. Every
  call path — the batch `reconcile_spawns` wrapper, the single-row
  `read_spawn_row` path in `ops/spawn/query.py:70`, and any future
  reconciler entrypoint — inherits the gate automatically. The batch
  wrapper shall not carry its own independent gate.
- **S-RP-007** — `doctor`'s orphan-run sweep shall continue to honour its
  existing `MERIDIAN_DEPTH > 0` skip at `ops/diag.py:145`. S-RP-006 does
  not regress that behaviour.
- **S-RP-008** *(new — F2)* — Every reconciler-origin call into
  `finalize_spawn` shall re-validate the projected lifecycle state under
  the `spawns.jsonl` flock immediately before appending the event. If the
  re-read shows a missing row or `status ∈ TERMINAL_SPAWN_STATUSES`, the
  event shall **not** be appended; `finalize_spawn` returns `False`. If the
  projected status is `finalizing`, the reconciler shall still append so a
  stale `finalizing` row can be stamped `orphan_finalization` per
  S-RP-002/S-RP-003. Authoritative origins retain their current
  "always append so metadata never drops" semantics — the authority rule
  in the projection (S-PR-001) adjudicates ordering races between them and
  any prior reconciler-origin terminal.

## Reaper — structural split (F7)

- **S-RP-009** *(new)* — `reconcile_active_spawn` shall be split into two
  halves:
  - A pure function `decide_reconciliation(record, snapshot, now)`
    that returns a `ReconciliationDecision` algebraic type covering
    `Skip`, `FinalizeFailed(error)`, `FinalizeSucceeded`.
  - An I/O shell that performs the `MERIDIAN_DEPTH` gate, collects the
    `ArtifactSnapshot` (including any timestamps the decider needs, such as
    `started_epoch`) and liveness probe results, calls the decider, then
    writes via `finalize_spawn` with `origin="reconciler"`.
  Heartbeat gating and finalizing-specific branches live in the pure
  decider.

## Projection — authority rule

- **S-PR-001** *(mechanism revised)* — The `spawns.jsonl` projection shall
  permit an **authoritative-origin** terminal finalize (origin ∈
  `AUTHORITATIVE_ORIGINS = {"runner", "launcher", "launch_failure",
  "cancel"}`) to supersede a prior **reconciler-origin** terminal finalize
  for the same spawn. The replacement shall overwrite `status`,
  `exit_code`, and `error`. Authority is keyed off the `origin` field on
  the event and the derived `terminal_origin` on the record — never off
  `error` content, except via the read-only legacy shim (S-PR-003).
- **S-PR-002** — The projection shall not permit any origin to supersede a
  prior authoritative-origin terminal finalize. Authoritative-over-
  authoritative and reconciler-over-reconciler and reconciler-over-
  authoritative are all no-ops on the terminal tuple. When two
  authoritative-origin terminal events land for the same spawn (for example
  runner + cancel or runner + launch_failure), first-wins is preserved.
- **S-PR-003** *(demoted to read-only legacy shim)* — For events whose
  persisted `origin` is `None` (pre-field legacy rows), the projection
  shall infer origin via a single isolated helper
  `resolve_finalize_origin(event)` that returns `"reconciler"` when
  `event.error ∈ LEGACY_RECONCILER_ERRORS = {"orphan_run",
  "orphan_finalization", "missing_worker_pid", "harness_completed"}` and
  `"runner"` otherwise. This shim is read-only; no new writer may omit
  `origin`; no other code path may infer origin from `error`. The shim
  has a planned deletion trigger (see `refactors.md` R-07).
- **S-PR-004** — Metadata accumulation (`duration_secs`, `total_cost_usd`,
  `input_tokens`, `output_tokens`, `finished_at`) shall merge from every
  finalize event regardless of origin or ordering.
- **S-PR-005** *(new)* — `SpawnRecord` shall carry a derived
  `terminal_origin: SpawnOrigin | None` field set by the projection at the
  moment the row reaches a terminal state. Subsequent authority decisions
  read this field instead of re-scanning prior events or re-inferring from
  `error`.
- **S-PR-006** *(new — invariant required by S-LC-004)* — Once the
  projected status is terminal, a later `SpawnUpdateEvent.status` shall
  **never** downgrade it. Late `running` or `finalizing` updates are
  dropped on the projection's status dimension. Non-status fields on late
  `SpawnUpdateEvent` rows continue to merge (e.g. `work_id`, `desc`
  updates against an already-terminal row remain idempotent).

## Consumer surface (F6)

- **S-CF-001** *(new)* — `cli/spawn.py`'s `view_map` "active" view shall
  resolve to the full active set (currently `("queued", "running",
  "finalizing")`) derived from `ACTIVE_SPAWN_STATUSES`, not a duplicated
  literal. Any future active state lands in one place.
- **S-CF-002** *(new)* — `cli/spawn.py`'s `--status` argument validator
  shall accept any value in `SpawnStatus` (derived from the literal in
  `domain.py`), not a hard-coded tuple.
- **S-CF-003** *(new)* — `api.get_spawn_stats` shall count `finalizing`
  under the active accumulator and expose it as a field on the stats
  output alongside `running`. Consumers that display an "active" count
  shall sum all active statuses.
- **S-CF-004** *(new)* — `src/meridian/lib/ops/spawn/models.py` shall treat
  `finalizing` as a first-class status in both the stats model and the
  status formatter used by `spawn show`. No consumer may infer lifecycle
  classification from `exited_at`; any prior "awaiting finalization" label
  shall be deleted in favor of the literal `finalizing` status.

## Observability

- **S-OB-001** — The `spawn show` renderer in
  `src/meridian/lib/ops/spawn/models.py` shall render `orphan_finalization`
  distinctly from `orphan_run`, including a note that the harness likely
  completed and that `report.md` may still contain useful content.
- **S-OB-002** — The reaper shall log the reason for every terminal stamp,
  including which activity artifact (if any) satisfied the heartbeat check
  and the elapsed inactivity at the moment of the decision.
- **S-OB-003** *(new)* — The reaper shall also log CAS-miss drops from
  S-RP-008 (reconciler finalize rejected because the row was missing or
  already terminal) at INFO level, so post-mortems can see that the guard
  fired rather than the reconciler silently stopping.

## Backfill

- **S-BF-001** — No migration shall rewrite `spawns.jsonl`. Historical
  poisoned rows shall self-repair via S-PR-001 + S-PR-003 on next read.
  The four currently-live incidents (`p1711`, `p1712`, `p1731`, `p1732`)
  are explicitly covered by this invariant.
- **S-BF-002** — The projection shall produce identical output for event
  streams that never contained a reconciler-origin + authoritative-origin
  finalize pair (i.e. the common case is untouched).
