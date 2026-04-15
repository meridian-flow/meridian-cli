# Pre-Planning Notes — Execution Impl-Orch

Captured before spawning @planner. Reflects runtime context the design package alone doesn't carry.

## Design freshness

Approved R2 design package signed off by confirmation reviewer p1747 (`approve`, no findings). Feasibility probes P1–P7 are fresh from this week. No re-probing required.

## Sequencing guidance (non-binding on planner)

User + dev-orch surfaced a preferred two-PR split:

- **PR1** — R-05 (depth gate into `reconcile_active_spawn`) + R-06 (runner heartbeat) + minimal R-04 split enabling these + R-09 portions that don't require schema. Defensive, ships visible fix, self-repairs nothing by itself but prevents new incidents.
- **PR2** — R-01 (status widening + consumer audit), R-02 (mandatory `origin`), R-03 (CAS helper + reconciler guard), R-04 remainder, R-07 (legacy shim), R-09 remainder.

The planner should honor this split **unless** it identifies a coupling that forces sequential execution. Refactors.md §Sequencing confirms PR1 is zero-schema-change and PR2 carries the schema + consumer surface.

**Observation**: the R-01 active-set widening (`ACTIVE_SPAWN_STATUSES += finalizing`) is physically independent from R-05/R-06 — PR1 can ship without it. But R-03's `mark_finalizing` helper requires `finalizing` in the status literal (R-01 partial). So PR1 must not introduce `mark_finalizing`. PR1 runner heartbeat starts the tick at `mark_spawn_running` entry, unbracketed by `mark_finalizing` — that's fine per design (S-RN-004: heartbeat spans `running` **and** `finalizing`, entering the latter is additive).

## Parallelism within PR2

Within PR2:

- **R-01 (status widening + consumer audit)** is structurally the foundation — everything else consumes `finalizing` as a valid status. Ship first inside PR2.
- **R-02 (origin on finalize_spawn)** touches 11 writer sites but the sites are independent — mechanical mapping per site. Parallelizable with R-01 if the schema change lands first.
- **R-03 (CAS helper + reconciler guard)** depends on R-01 (needs `finalizing` literal) and R-02 (needs `origin` param). Sequential after those two.
- **R-04 remainder (decide/write split)** can start once R-01 lands; independent of R-02/R-03 mechanics.
- **R-07 (legacy shim)** is a small standalone helper + unit test. Schedule alongside R-03.
- **R-09 remainder (delete `exited_at`-driven semantics at 3 sites)** depends on R-01 stats/formatter work since the "awaiting finalization" heuristic is replaced with literal `finalizing`.

Planner decides exact phase grain — these are parallelism hypotheses, not prescriptions.

## Concurrency-sensitive work → mandatory @smoke-tester + @unit-tester

Two refactors touch filesystem locking and async concurrency. Design compliance alone is insufficient; only running against real flock + real runner proves correctness:

- **R-03 `mark_finalizing` CAS** — contention race between runner and reconciler under `spawns.jsonl.flock`. Unit-level: parallel threads driving `mark_finalizing` + reconciler `finalize_spawn` with origin="reconciler". Smoke-level: sibling `meridian spawn list` (reader) firing while runner is mid-transition.
- **R-06 heartbeat lifecycle** — task must survive `finalize_spawn` raising, must stop after terminal write, must tick during both `running` and `finalizing`. Smoke-level: SIGKILL the runner mid-execution and confirm reaper stamps `orphan_run` only after 120s elapses past last heartbeat touch; separately, force a runner-crash mid-`finalizing` and confirm `orphan_finalization`.

## Backfill self-repair — hard requirement

`.meridian/spawns.jsonl` holds pre-field-tag incidents `p1711`, `p1712`, `p1731`, `p1732` that projection+shim must classify correctly on read. Unit test must assert these four rows project to `succeeded` after the R-02+R-07 landing. Non-negotiable: the user and reviewers treat this as the proof-of-fix.

Additionally, this session alone has produced further incident rows (p1736, p1740..p1746 range). Planner should pass through live-repo `spawns.jsonl` inspection to enumerate all poisoned rows to assert on.

## Sandbox discipline (repeat from impl-orch brief)

Every @coder / @verifier / @smoke-tester / @unit-tester / @reviewer spawn must use `--approval yolo`. The read-only sandbox policy has repeatedly blocked `.meridian/*.flock` writes; see confirmation reviewer p1747 verification notes ("could not run in this read-only sandbox because it attempted to create `.meridian/work-items.flock`"). `yolo` is necessary for tests that touch `spawns.jsonl`.

## Architecture re-interpretation

Design §"What is deliberately not changed" explicitly scopes out:

- Probe-layer rewrite of `is_process_alive` (heartbeat makes it non-load-bearing).
- Collapsing the 9 `reconcile_spawns` batch call sites (gate lives deeper).
- Projection-as-state-machine refactor.
- Other terminal writers (streaming/app-server/launch-failure/cancel) gaining the `finalizing` step — they keep direct `running → terminal` with explicit `origin`.

Planner must respect these fences. Any phase that tries to extend the `finalizing` lifecycle to non-runner paths violates the scope fence.

## Final review composition

Per impl-orch brief: final review loop fan-out across **gpt-5.4, opus, and one more on a different model family** (gpt-5.3-codex, haiku, or sonnet), with design-alignment focus mandatory. Include @refactor-reviewer. Intermediate phases use tester lanes only; @reviewer escalation is exception-only.
