# Decisions

## D-1 — Ship both Fix A and Fix B (no substitution)

**Decided:** Fix A (heartbeat + depth gate) and Fix B (`finalizing` state)
both ship; neither makes the other redundant.

**Reasoning:**

- They protect different windows.
  - Fix A protects the `running` state against psutil false-negatives. The
    triggering case for this reopen — parent reparented to init, psutil
    returned False for alive PIDs — is exactly this window.
  - Fix B protects the post-exit drain/report-persistence window. Once the
    runner enters `finalizing`, it has declared itself in controlled
    cleanup and is no longer subject to psutil-driven reclassification at
    all.
- There is a real overlap zone (runner exited but heartbeat still touched)
  where either defence suffices. Redundancy is intended — this bug has
  reopened once already, and overlapping defences are cheap.

**Alternatives considered:**

- **Fix B only.** Cleanest structurally but leaves the `running` state
  exposed to psutil false-negatives. A heartbeat-free runner in a
  sandboxed namespace could still be stamped during normal execution.
- **Fix A only.** Restores the pre-rewrite defence but leaves the
  post-exit window structurally ambiguous. `orphan_run` vs
  `orphan_finalization` remains a heuristic on `exited_at`, not a
  lifecycle fact.

## D-2 — Prevent bogus terminal writes; add a narrow projection override

**Decided:** Primary defence is prevention (Fix A + Fix B). Supplementary
defence is a projection rule that permits a runner-origin finalize to
supersede a reconciler-origin terminal for the same spawn. First-wins
semantics are preserved for every other combination.

**Reasoning:**

- The append-only / idempotent invariant in `spawns.jsonl` is too valuable
  to perforate with general "later event wins" logic. Reconcilers racing
  each other should keep first-wins.
- The runner is authoritative. It has full evidence: report contents,
  exit code, usage data. A reconciler is making a best-effort probe.
  When both land, the runner's conclusion is strictly more informed.
- A single directed rule — *reconciler-origin can be overridden only by
  runner-origin* — is narrow, auditable, and asymmetric. It does not
  open the door to general event revisioning.

**Alternatives considered:**

- **Pure prevention.** Elegant, but leaves no recovery path for the
  existing poisoned rows or for any future prevention gap.
- **General later-wins.** Would let every reconciler race last-write-wins,
  destabilizing behaviour across the seven call sites.
- **One-shot migration writing repair events.** Reversible, but requires
  rewriting `spawns.jsonl` in-place and adds a migration hazard that
  self-repair-on-read avoids entirely.

## D-3 — `orphan_finalization` is a hard terminal failure with distinct semantics

**Decided:** `orphan_finalization` remains a terminal `failed` status with
`exit_code = 1`. It is not a soft warning. What differs from `orphan_run`
is diagnostic content and `spawn show` rendering.

**Reasoning:**

- Downstream callers (`spawn wait`, dashboards, CI gates) need a clear
  terminal state. Introducing a third "soft failure" class would
  complicate every consumer.
- The real value of the distinction is observability: an
  `orphan_finalization` spawn is much more likely to have a usable
  `report.md` and meaningful work product than an `orphan_run` spawn.
  `spawn show` should surface that explicitly.

**Alternatives considered:**

- **Soft-warning status** that doesn't count as failed — rejected,
  complicates every `is_active_spawn_status` / `TERMINAL_SPAWN_STATUSES`
  consumer for minimal gain.
- **Auto-project `orphan_finalization` with a durable report as
  succeeded.** Already handled by S-RP-004; this is the right path for
  the obvious-success case.

## D-4 — Keep read-path sweeps; add a single fan-in depth gate

**Decided:** `reconcile_spawns` continues to run on read paths. The
`MERIDIAN_DEPTH > 0` skip moves into `reconcile_spawns` itself, covering
all seven call sites with one guard.

**Reasoning:**

- Read-path sweeps are useful: dashboards and `spawn list` surface
  current reality, not a stale snapshot.
- Nested invocations (`MERIDIAN_DEPTH > 0`) never need to perform the
  sweep — they're always running under a parent that has already
  reconciled. Gating them out eliminates the exact class of false
  positives that arise from sandboxed-child perspective.
- One gate at the fan-in is greppable and unambiguous. Seven per-site
  gates would drift.

**Alternatives considered:**

- **Move sweeps to `meridian doctor` only.** Invasive; breaks dashboard
  auto-repair; would regress user experience where stale rows go
  unreconciled for long periods.
- **Per-site gates.** Rejected for the drift reason above.

## D-5 — Self-repair historical rows via projection; no migration

**Decided:** Existing poisoned rows in `spawns.jsonl` are not rewritten. The
projection rule from D-2 includes a legacy-event inference (S-PR-003) that
treats a prior finalize with `error ∈ {"orphan_run", "orphan_finalization",
"missing_worker_pid", "harness_completed"}` as reconciler-origin, so the
later runner finalize supersedes it on read.

**Reasoning:**

- No `spawns.jsonl` rewrite preserves crash-only semantics perfectly.
- The affected rows (`p1711`, `p1712`) project correctly on next read
  after the projection rule lands — no user action required.
- The error-code inference is bounded to a known finite set of
  reconciler-origin errors. New additions must be added to
  `_RECONCILER_ERRORS`; this invariant is cheap to assert in a unit
  test.

**Alternatives considered:**

- **One-shot migration writing repair events.** Adds a deploy-time
  hazard; provides no benefit over read-path self-repair for this
  data shape.
- **Leave rows as-is.** Would ship with the user's known real spawns
  showing `failed` even though they succeeded, which undermines trust
  in the fix landing.

## D-6 — Heartbeat window = 120s

**Decided:** `_HEARTBEAT_WINDOW_SECS = 120`.

**Reasoning:**

- Pre-rewrite code used 300s as a belt-and-suspenders ceiling alongside
  `is_process_alive`. Without the probe as primary, 300s is too loose.
- Post-exit bounded work is tiny: `POST_EXIT_PIPE_DRAIN_TIMEOUT_SECONDS`
  is 10s; report redaction and extraction are sub-second; guardrails
  have their own timeout.
- 120s gives roughly a 10× margin over realistic worst-case activity
  gaps while still catching a genuinely dead runner within a couple of
  minutes — an acceptable SLA for a read-path reconciler.
- Easy to tune later if operational data shows false-negatives or
  false-positives at the threshold.

## Round 2 — F1–F8 addressed/rejected mapping

Round 1 was rejected by three reviewers (`p1728`, `p1731`, `p1732`) with
findings F1–F8. Each is addressed below with explicit mechanism; nothing is
deferred to "implementation discretion". The Round 1 decisions D-1..D-6
above stay in force where the mechanism survived; revisions are noted
inline.

### D-7 — F1 addressed: origin is a first-class field (blocker)

**Decided:** A closed `SpawnOrigin` enum `{"runner", "launcher",
"launch_failure", "cancel", "reconciler"}` is persisted on
`SpawnFinalizeEvent.origin` and derived onto `SpawnRecord.terminal_origin`.
The projection authority rule (S-PR-001) keys off `origin` /
`terminal_origin`, never off `error` content. Legacy rows that lack
`origin` flow through a single read-only shim `resolve_finalize_origin`
with `LEGACY_RECONCILER_ERRORS = {"orphan_run", "orphan_finalization",
"missing_worker_pid", "harness_completed"}`; new code must always pass
`origin=...` explicitly (R-02, R-07). D-2's "runner-origin supersedes
reconciler-origin" is generalized to
`AUTHORITATIVE_ORIGINS = {"runner", "launcher", "launch_failure",
"cancel"}` — every authoritative-origin writer can supersede a prior
reconciler-origin terminal, which matches the epistemic position of
launcher and cancel paths.

**Reasoning:** heuristic origin inference was the Round 1 blocker.
Reviewers pointed out that any reconciler landing a terminal error not
in the inferred set would be misclassified; expanding the set is a
code-change blocker every time a new error appears. Mechanism must be a
field, not a lookup table.

**Revises D-2** only in the authority source: "runner-origin" is widened
to "authoritative-origin" so launcher/cancel/launch_failure retain their
existing authority without needing case-by-case projection rules.

### D-8 — F2 addressed: `running → finalizing` is atomic CAS (blocker)

**Decided:** New helper `mark_finalizing(state_root, spawn_id) -> bool`
acquires `spawns.jsonl.flock`, projects current state under the lock,
appends `SpawnUpdateEvent(status="finalizing")` only when status is
exactly `running`, and returns whether the event was appended. On CAS
miss (S-LC-006) the runner still runs post-exit work and its final
`finalize_spawn` call — authority wins via projection, not via re-try.
Reconciler-origin calls into `finalize_spawn` re-validate projected
state under the flock and drop their event when status has moved to
`finalizing` or terminal (S-RP-008). Authoritative origins retain
append semantics; ordering races between authoritative and reconciler
are adjudicated by the projection. The projection invariant S-PR-006
("late `SpawnUpdateEvent.status` never downgrades a terminal row")
makes the design safe against racing late updates.

**Reasoning:** reviewers flagged that `update_spawn` appends blindly —
two writers could both observe `running` and both append. A helper
that branches on read is not enough; the check and the append must be
inside the same flock acquisition.

### D-9 — F3 addressed: depth gate inside `reconcile_active_spawn` (blocker)

**Decided:** The `MERIDIAN_DEPTH > 0` short-circuit lives at the top of
`reconcile_active_spawn`. The batch `reconcile_spawns` wrapper inherits
coverage; the single-row `read_spawn_row` path in
`ops/spawn/query.py:70` inherits coverage; every future reconciler
entrypoint inherits coverage. The batch wrapper does not carry an
independent gate. `ops/diag.py:145`'s existing `MERIDIAN_DEPTH` skip
stays — it guards a separate code path that never enters
`reconcile_active_spawn`.

**Reasoning:** Round 1 placed the gate at the batch wrapper, which left
the single-row read path ungated. Reviewers noted that the triggering
sweep could originate from any depth>0 nested read, and one missed
surface was enough to keep the bug live.

**Revises D-4:** from "single fan-in depth gate" to "single-point
coverage inside `reconcile_active_spawn`", which is a stronger
invariant and reduces the gated call-site inventory from seven to one.

### D-10 — F4 addressed: runner-owned periodic heartbeat

**Decided:** Runner writes a 30s heartbeat tick for the full duration
of `running` and `finalizing`. The reaper consults the `heartbeat`
artifact as the primary liveness signal, with `output.jsonl`,
`stderr.log`, `report.md` as defense in depth. The 30s tick is 4× the
120s window, enough to tolerate scheduling jitter and short GC pauses.

**Reasoning:** probe P1 measured max harness-silence gaps of 153.9s
(Claude) and 86.8s (Codex). Both exceed the 120s window. Without a
runner heartbeat, a reaper could stamp a healthy long-silence Claude
run, which regresses the same failure class the fix is meant to
prevent. Evidence is in `design/feasibility.md` §P1 and
`probe-heartbeat.md`.

### D-11 — F5 addressed: full writer surface enumerated

**Decided:** The eleven `finalize_spawn` writer sites are enumerated
in `design/feasibility.md` §P5 and mapped to origins in
`design/architecture/overview.md`. Every site passes `origin=...`
explicitly (R-02 scope).

**Reasoning:** reviewers pointed out Round 1 referred to "runner" and
"reconciler" without enumerating the other nine sites. The writer
inventory is now a contract surface (S-RN-005), not a narrative.

### D-12 — F6 addressed: consumer audit is implementation scope, not prep

**Decided:** `cli/spawn.py`'s `view_map["active"]`, the `--status`
validator, and `api.get_spawn_stats` all update in lockstep when
`finalizing` lands. The active set derives from `ACTIVE_SPAWN_STATUSES`;
`--status` derives from `SpawnStatus`; stats count `finalizing`
alongside `running`. Refactor R-01 is not complete until every
status-literal consumer has been updated and tested for `finalizing`
(S-CF-001..003).

**Reasoning:** reviewers noted that adding a new status without
updating consumers produces silent miscounts and user-visible rejection
of valid values. Treating consumers as implementation scope (not
follow-up) prevents the status from shipping half-plumbed.

### D-13 — F7 addressed: decide/write split in reconciler

**Decided:** `reconcile_active_spawn` splits into a pure
`decide_reconciliation(record, snapshot, now) -> ReconciliationDecision`
and an I/O shell that collects the `ArtifactSnapshot` and dispatches.
`snapshot` carries timestamps such as `started_epoch`; `MERIDIAN_DEPTH`
stays in the shell. Heartbeat gating and
finalizing-specific branches live in the decider (S-RP-009, R-04).

**Reasoning:** reviewers flagged the mixed concerns in a function that
was about to receive two new branches (heartbeat gating + finalizing
policy). Splitting now keeps the decider testable without I/O mocking
and confines the next feature addition to one branch of the decision
ADT.

### D-14 — F8 addressed: heartbeat helper stays isolable

**Decided:** The reaper's heartbeat-stat helper is kept local to one
site so a future switch to `scandir` or to a single consolidated
heartbeat artifact is call-site-local (R-06 nit-scope).

**Reasoning:** reviewers flagged avoiding multiple stat calls scattered
across the reaper. The helper kept isolated is a preventive refactor
in the right direction without over-engineering the current pass.

### D-15 — Rejections none

No F-findings were rejected or partially addressed. Every finding has a
concrete mechanism in the Round 2 package. Residual risks
(heartbeat-task starvation, CAS contention, legacy shim correctness)
are documented in `design/feasibility.md` "Residual risks" and are not
blockers.

## Round 2 delta — reviewer convergence

### D-16 — Reconciler guard stays narrow: terminal-only drop, `finalizing` writes through

**Decided:** S-RP-008 drops reconciler-origin `finalize_spawn` writes only
for missing rows and `TERMINAL_SPAWN_STATUSES`. A projected `finalizing`
row remains writable by the reconciler so stale cleanup rows can be stamped
`orphan_finalization`.

**Reasoning:** the Round 2 reviewers correctly pointed out that dropping
`finalizing` contradicts S-RP-002/S-RP-003 and would strand a crashed
mid-drain runner in a state the reaper could never close.

### D-17 — `finalizing` becomes first-class in `ops/spawn/models.py`; `exited_at` semantics are deleted now

**Decided:** R-01 explicitly covers `src/meridian/lib/ops/spawn/models.py`
alongside `cli/spawn.py` and `ops/spawn/api.py`. Stats model fields carry a
`finalizing` bucket, the formatter renders literal `finalizing`, and the
"awaiting finalization" heuristic is deleted. R-09 removes all
`exited_at`-driven lifecycle classification this cycle; the field remains
telemetry/audit only.

**Reasoning:** once `finalizing` is the lifecycle authority, any renderer or
stats surface still inferring lifecycle from `exited_at` becomes a source of
contradiction, not compatibility.

**Revises:** D-3's earlier wording that described `orphan_finalization` as a
heuristic on `exited_at`. After the Round 2 delta, status is authoritative and
`exited_at` is observational only.

### D-18 — Heartbeat shutdown discipline is enforced by outer `finally`

**Decided:** Both runners cancel and await the heartbeat task from an outer
`finally` block that wraps harness execution and the terminal
`finalize_spawn` call. No new `launch/heartbeat.py` file is introduced in
this cycle; the helper stays inline in `runner.py` / `streaming_runner.py`.

**Reasoning:** reviewer S1 was right that "stops after finalize returns" is
insufficient on its own. If `finalize_spawn` raises, the heartbeat task must
still terminate. Choosing inline helpers also resolves the architecture
contradiction about whether a new module is added.

### D-19 — Post-launch CLI treats `finalizing` as non-error

**Decided:** `cli/spawn.py:54` includes `finalizing` in the post-launch
success surface. A launch command that returns while the spawn is in
`finalizing` still succeeds; callers use `spawn show` / `spawn wait` to
observe the later terminal outcome.

**Reasoning:** the race window is legitimate and expected once `finalizing`
is explicit. Treating it as an immediate failure would misclassify a healthy
spawn that has exited the harness but is still draining and persisting.

### D-20 — Medium-severity commitments are explicit, not deferred

**Decided:** The remaining reviewer deltas are committed as concrete design
choices now:

- Authoritative-over-authoritative remains first-wins.
- The public `update_spawn(status=...)` status-transition entrypoint is
  removed; only `mark_spawn_running` / `mark_finalizing` move lifecycle.
- `decide_reconciliation(record, snapshot, now)` is the stable decider
  signature; `snapshot` carries timestamps such as `started_epoch`, while
  `MERIDIAN_DEPTH` stays in the shell because it is an I/O-time gate.
- R-07's legacy-shim removal trigger is data-driven: delete the
  `origin is None` branch in the first release after `meridian doctor`
  confirms no supported state root still carries such events.

**Reasoning:** each item closed an ambiguity the next implementer would
otherwise have to "figure out," which is just deferral wearing different
clothes.

## Planning decisions

### D-21 — Keep the preferred two-PR split, but only one coder-parallel round

**Decided:** Execution stays on the preferred split from
`plan/pre-planning-notes.md`: PR1 is the preventive heartbeat / depth-gate
path, PR2 carries the schema and lifecycle repair. Inside PR2, only one
parallel coder round is safe: Phase 3 (`cli/spawn.py` + `ops/spawn/models.py`)
and Phase 4 (`spawn_store.py` + writer sites + `ops/spawn/api.py`) run in
parallel after the core status foundation lands.

**Reasoning:**

- The shared state-layer files (`spawn_store.py`, `reaper.py`, `runner.py`,
  `streaming_runner.py`) make the final lifecycle work inherently serial.
- The PR1 prevention path is still valuable even though it does not repair
  historical rows; it stops new poison while PR2 is built.
- Splitting the user-facing surface (Phase 3) away from origin / projection
  mechanics (Phase 4) is the only write-set split that stays independent
  without weakening the design.

**Alternatives considered:**

- **Single PR / all-sequential phases.** Simpler to reason about, but it
  delays the preventive fix and gives up the only safe parallel round the
  design leaves available.
- **Parallelize Phase 5 with any earlier PR2 work.** Rejected because Phase 5
  depends on Phase 4's `origin=` contract and reuses the same state-layer
  files, which would create avoidable merge pressure and race-condition drift.

### D-22 — Keep R-08 deferred in this cycle

**Decided:** `R-08` remains deferred. This plan removes `exited_at`-driven
classification semantics now, but the `exited_at` field itself stays until a
later release can prove supported state roots no longer depend on legacy rows.

**Reasoning:**

- The approved design already narrows `exited_at` to telemetry / audit.
  Removing semantics now captures the real correctness win without mixing in a
  separate data-shape cleanup.
- The removal trigger is operational evidence, not calendar time: only a later
  release with `meridian doctor` evidence that `origin=None` finalize rows are
  gone should delete the field entirely.

**Alternatives considered:**

- **Delete `exited_at` in this cycle.** Rejected because it expands risk
  beyond the bug fix and would tangle legacy-row audit concerns into the same
  rollout.
- **Leave `exited_at` semantics in place.** Rejected because it would keep two
  conflicting lifecycle authorities alive after `finalizing` lands.

### D-23 — Phase 5 CAS guard and finalizing reconciliation semantics

**Decided:** `spawn_store.mark_finalizing` is the only CAS writer for
`running -> finalizing` and runs under the same `spawns.jsonl.flock` as
`finalize_spawn` / `update_spawn`. The helper returns `False` on CAS miss
(missing row, non-running row, or already-finalizing/terminal row) and does
not raise.

**Reasoning:** this keeps the lifecycle handoff atomic while making misses a
normal race outcome instead of an infrastructure failure.

### D-24 — Reconciler finalize admissibility is guarded under flock

**Decided:** `finalize_spawn(..., origin="reconciler")` now re-reads the
projected row under lock and drops the append when the row is missing or already
terminal, logging INFO for observability. `status="finalizing"` stays
admissible so stale cleanup rows can close as `orphan_finalization`.

**Reasoning:** this closes duplicate terminal-write races without blocking the
stale-finalizing recovery path required by S-RP-002/S-RP-003.

### D-25 — Finalizing rows are heartbeat-gated and PID-agnostic

**Decided:** reaper classification treats `record.status == "finalizing"` as a
heartbeat-only branch: recent heartbeat => skip; stale heartbeat => terminalize
(`orphan_finalization` unless durable-report success). `is_process_alive` is not
consulted for finalizing rows.

**Reasoning:** PID probes are noisy at this boundary; heartbeat recency is the
explicit liveness contract for runner-controlled cleanup.

### D-13 — Revert heartbeat-only recency tightening in reaper (S-RP-001)

**Decided:** Reverted Phase 1 ad-hoc tightening. `_has_recent_activity` now uses one uniform rule: any recent activity across `heartbeat`, `output.jsonl`, `stderr.log`, or `report.md` within the 120s window suppresses reconciliation for every branch.

**Reasoning:** S-RP-001 is explicit that recency suppression is artifact-agnostic and applies regardless of `psutil.pid_exists` outcome. The heartbeat-only asymmetry for dead/missing-runner branches contradicted spec and created avoidable false failures.

**Trade-off:** A last-gasp `stderr.log` write from a dying harness could briefly mask a dead runner, but heartbeat staleness catches it within one tick cycle (~30s) and the spec favors the simpler uniform rule.

### D-14 — Remove `status=` from public `update_spawn` API (R-02 hardening)

**Decided:** Removed `status` from `update_spawn(...)`. Lifecycle transitions must go through `mark_spawn_running(...)`, `mark_finalizing(...)`, or `finalize_spawn(...)`.

**Reasoning:** This closes the public bypass surface and keeps state transitions on explicit CAS/transition-validated helpers. Metadata writes (`execution_cwd`, `runner_pid`, `harness_session_id`, `desc`, etc.) stay on `update_spawn`.

### D-15 — PID reuse guard margin widened to 30s (Option A)

**Decided:** Kept existing schema and widened liveness PID reuse guard from `+2.0s` to `+30.0s` in `is_process_alive(...)`.

**Reasoning:** Background launch setup frequently records PID later than initial spawn start timestamp; `+2s` was too tight and caused false PID-reuse classification. Option A fixes the live issue with minimal late-cycle surface area. Option B (new `runner_pid_recorded_at_epoch`) is cleaner but requires broader schema/event changes than needed for this pass.
