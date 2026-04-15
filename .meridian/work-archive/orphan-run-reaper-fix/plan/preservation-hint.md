# Preservation Hint — Round 2

Round 1 design (commit present on disk under `design/`) was rejected by a 3-reviewer fan-out (p1728 refactor-reviewer, p1731 gpt-5.4 primary, p1732 gpt-5.4 structural). Three blockers and three serious findings, all load-bearing. Redesign is required; a patch is not acceptable.

Meta-evidence: p1731 and p1732 themselves fired the exact bug during their review runs (stamped `failed/orphan_run` at 13:00:55Z, then `succeeded` at 13:05:07Z / 13:06:18Z). `spawns.jsonl` now contains **4 live incidents** — p1711, p1712, p1731, p1732 — that the redesign must self-repair on read.

## Scope mandate

**Refactor properly. No patch-on-patch, no heuristics covering for missing mechanism, no dead code.**

The bug lives in the state layer. Fix it as a state-layer cleanup that happens to eliminate `orphan_run` false-positives, not the other way around. If a clean fix requires widening the refactor agenda beyond R-01..R-03, widen it. Call out deletions explicitly.

Guiding principles (CLAUDE.md, dev-principles):
- Knowledge in data, not heuristics. Origin tagging is data. Inferring from `error` strings is a heuristic.
- Crash-only design. Every write atomic; every read tolerates truncation; recovery is startup. A non-atomic lifecycle transition violates this.
- Simplest orchestration that works. Don't build more than needed — but don't underbuild either. A trusted subsystem that deletes complexity is a simplification.

## Preserved from Round 1

Carry forward (do not redesign from scratch):
- The overall two-fix framing — Fix A (heartbeat + depth gate) + Fix B (explicit post-exit lifecycle state).
- Decision D-1 (ship both, they protect different windows).
- Decision D-4 (keep read-path sweeps, gate at fan-in).
- Decision D-5 (no migration, self-repair on read).
- The EARS ID namespace (S-LC-*, S-RN-*, S-RP-*, S-PR-*, S-OB-*, S-BF-*). Keep IDs stable where the mechanism survives; renumber only where the mechanism materially changes.

## Revised or invalidated from Round 1

- **S-RP-004** (reaper projecting `succeeded` from a durable report): mechanism invalid, see F1. Either delete this responsibility from the reaper entirely, or make it emit with an explicit reconciler-origin tag so the later runner finalize can still override.
- **S-PR-003** (legacy-event origin inference from `error`): acceptable only as a backfill shim for pre-origin-tag events already in `spawns.jsonl`. Not acceptable as the primary mechanism. Origin must be first-class.
- **S-LC-004** (`running → finalizing` transition): mechanism invalid, see F2. Transition must be atomic under the spawns.jsonl flock with compare-and-swap semantics, and the reaper's finalize path must re-read under the same lock.
- **S-RP-006** (depth gate at `reconcile_spawns` fan-in): coverage invalid, see F3. Gate must also land at the single-row `reconcile_active_spawn` path.
- **R-01** (`SpawnStatus` literal widening): claim "no caller should break" is false. Consumer audit of `cli/spawn.py` filter/count logic, `cli/work.py`, `spawn_dashboard.py`, `api.list_active_spawns`, and every hardcoded status-string comparison is implementation scope, not prep.
- **R-02** (origin kwarg on `finalize_spawn`): claim "two-caller change" is false. 11 terminal writers enumerated in F5. Enum must be wide enough to describe them honestly (runner, app-server, streaming-serve, streaming-runner, process-launch, reconciler, cancel, background-launch-failure, execute-failure, or a cleaner grouping) OR the scope must be restructured so the axis that matters (authoritative vs best-effort) is what's tagged.

## Findings to address (F-level)

### Blockers

- **F1 — Explicit origin tagging.** Origin must be a first-class field on `SpawnFinalizeEvent`. Projection rule uses the field, never `error` content (except as a read-only legacy-shim for pre-field events). Reaper-authored `succeeded` must still be overridable by later runner finalize.
  Evidence: `.meridian/spawns/p1728/report.md` finding 1; `.meridian/spawns/p1732/report.md` finding 1.

- **F2 — Atomic `running → finalizing`.** `mark_finalizing` must be a compare-and-swap under the `spawns.jsonl` flock that refuses the update if the current projected status is already terminal. The reaper's finalize path must re-read under the same flock immediately before writing the terminal event and must refuse to finalize if the current status is `finalizing`.
  Evidence: `.meridian/spawns/p1731/report.md` finding 1.

- **F3 — Depth gate on single-row reconciler.** The `MERIDIAN_DEPTH>0` short-circuit must land at `reconcile_active_spawn` too, not only at `reconcile_spawns`. Every call site in `query.read_spawn_row` and `api` query paths inherits the gate automatically.
  Evidence: `.meridian/spawns/p1731/report.md` finding 2.

### Serious

- **F4 — Runner heartbeat in `running`.** The 120s heartbeat window is sound for `finalizing` (bounded post-exit work) but wrong for `running`. Either introduce a runner-owned periodic heartbeat during `running` (touch a heartbeat artifact on a tick, independent of harness output), or use state-dependent thresholds with evidence that every supported harness emits output within the chosen `running` threshold. "Longest realistic model-thinking gap" must be probed per harness, not assumed.
  Evidence: `.meridian/spawns/p1731/report.md` finding 3.

- **F5 — Full finalize-spawn surface audit.** 11 terminal writers identified (`lib/app/server.py:141`, `cli/streaming_serve.py:113`, `lib/launch/streaming_runner.py:1184`, `lib/launch/process.py:426`, `lib/launch/runner.py:851`, `lib/ops/spawn/api.py:493`, `lib/ops/spawn/execute.py:578`, plus reaper + cancel paths). Design must enumerate every writer, specify the origin tag each emits, and confirm no path writes a terminal record without going through `finalize_spawn`.
  Evidence: `.meridian/spawns/p1728/report.md` finding 4; `.meridian/spawns/p1732/report.md` finding 3.

- **F6 — Status-consumer audit in implementation scope.** `cli/spawn.py:446`, `api.py:284`, `spawn_lifecycle.py:13` all hard-code `{queued, running}` as the active set or gate valid `--status` arguments against a fixed literal. This is not a prep refactor; it is part of shipping `finalizing`.
  Evidence: `.meridian/spawns/p1728/report.md` finding 2; `.meridian/spawns/p1732/report.md` finding 2.

### Medium

- **F7 — Split `reconcile_active_spawn` decide/write.** The function currently mixes classification, artifact reads, liveness probing, event emission, and logging. Adding heartbeat gating and finalizing-specific policy to this branchy function compounds the problem. Prep refactor: extract a pure "decide next state given current state + artifacts" function returning a decision value; keep I/O at the boundary.
  Evidence: `.meridian/spawns/p1728/report.md` finding 3.

### Nits

- **F8 — Heartbeat stat() cost.** 80-200 stats per sweep at 20-50 active spawns. Acceptable with the depth gate but keep the heartbeat helper isolable so it can switch to `scandir` or a single consolidated heartbeat file later without reworking callers.
  Evidence: `.meridian/spawns/p1732/report.md` finding 4.

## Dead code / deletion prompts

While redesigning, audit for code that becomes vestigial:

- If origin is first-class, S-PR-003 shrinks to a backfill shim. Name the shim explicitly and plan its removal window.
- `exited_at` may be partially subsumed by `finalizing` transitions. Do not delete prematurely — it still carries legacy-row meaning — but note it in `refactors.md` as a removal candidate after the projection repair cycle completes.
- If `reconcile_active_spawn` splits per F7, at least one branch of the old monolith is likely dead. Call it out.

## Sequencing preference

p1732 recommended **PR1 = Fix A + depth gate** (small, defensive) and **PR2 = Fix B + projection + consumer audit** (structural). Prefer this split unless the redesign surfaces a reason the two fixes are actually coupled. If they are coupled, say why explicitly in `decisions.md`.

## Review posture for Round 2

Do not ship a solo one-shot design. Spawn architects for the state-layer mechanism work (at minimum one on atomic CAS semantics and one on origin tagging), then fan out at least two reviewers on diverse models against the final package before handing back.
