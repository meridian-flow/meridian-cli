# Architect: atomic CAS protocol for `running → finalizing` + reconciler re-validation

## Context

Round 1 of the orphan-run reaper fix was rejected. One of the three blockers (F2, p1731 finding 1) is that the proposed `running → finalizing` transition is **not atomic** against a concurrent reconciler finalize:

- `update_spawn(status="finalizing")` blindly appends the event without validating the current state under the flock.
- `_record_from_events` applies the update even after a terminal finalize, so a late update event can stamp `finalizing` onto an already-terminal row.
- `finalize_spawn` does not re-check whether the reconciler's earlier classification is still valid under the lock before writing its own terminal event — a runner could still be about to mark `finalizing` at the same instant a reconciler is about to mark `orphan_run`.

Fix direction from the review: **make `mark_finalizing` a locked compare-and-swap, and make reconciler finalization re-validate under the same lock.**

## What to design

Produce a design memo (1-2 pages, dense, no code yet — pseudocode OK) that covers:

1. **`mark_finalizing` CAS semantics.** Pre-state required (`running` only; not `queued`, not `finalizing`, not terminal). Lock scope (must share the same `spawns.jsonl` flock used by `finalize_spawn` / `append_event`). Behavior on CAS miss: silent no-op? return bool? raise? Justify. Think about what happens when the runner is racing a reconciler that is about to stamp `orphan_run` — which wins and why.

2. **Reconciler re-validation on the write path.** Spec out the guard semantics for `finalize_spawn` when called from a reconciler origin: must re-read state under the same lock; must refuse (return False, drop the event entirely) when the current projected status is `finalizing` or terminal. Authoritative writers (runner, launcher, launch_failure, cancel) retain their current "always writes" semantics for metadata preservation — but projection authority (out of scope for this architect, covered separately) handles resulting races.

3. **Where does the guard live?** Two candidates:
   - `finalize_spawn(..., guard_origin=SpawnOrigin)` — one function, one flock, one CAS, branch on origin. Simple.
   - `reconciler_finalize_spawn(...)` — separate function with narrower semantics, shares lock code. More explicit.
   Pick one, argue why, including maintainability and the "one write path per axis" principle.

4. **Event-schema implications.** `SpawnUpdateEvent` already has `status: SpawnStatus | None` — it is the mechanism that would write `finalizing` today. After CAS, is `status=...` on `SpawnUpdateEvent` still allowed from other call sites? Audit what else uses it (grep `update_spawn(...status=`). Propose whether the `status` kwarg stays general or becomes `mark_finalizing`-only. Dead-code-call-out is mandatory.

5. **Lifecycle transition table.** The authoritative `_ALLOWED_TRANSITIONS` in `src/meridian/lib/core/spawn_lifecycle.py` will gain `finalizing`. Produce the full revised table and say whether `queued → finalizing` is legal (Round 1 spec said no; architecture snippet said yes; be explicit here and justify the chosen side).

6. **Projection interaction.** What does the projection do with a late update event that tries to set status on an already-terminal row? Be explicit. The projection is covered by the parallel architect, but the transition protocol must name the invariants it expects from projection (e.g. "status in `_TERMINAL_SPAWN_STATUSES` is never downgraded by a subsequent `SpawnUpdateEvent`").

## Evidence to consult

- `src/meridian/lib/state/spawn_store.py` — `finalize_spawn` (line 317), `update_spawn` (line 253), `_record_from_events` (line 427), projection terminal handling (line 534).
- `src/meridian/lib/state/event_store.py` — `lock_file`, `append_event`, flock semantics.
- `src/meridian/lib/state/reaper.py` — `_finalize_and_log`, how it currently calls `finalize_spawn`.
- `src/meridian/lib/launch/runner.py:815-867` — the point where `running → finalizing → terminal` must happen.
- Round 1 feedback: `.meridian/spawns/p1731/report.md` finding 1 (the blocker).
- Round 1 rejected architecture: `.meridian/work/orphan-run-reaper-fix/design/architecture/overview.md`.
- Preservation hint: `.meridian/work/orphan-run-reaper-fix/plan/preservation-hint.md` (guiding document).

## Deliverable

Write the memo to:

`$MERIDIAN_WORK_DIR/arch-cas-memo.md`

Keep it tight. No implementation code. Pseudocode for the CAS block is fine and expected. Call out any dead code / deletion candidates and open questions explicitly.
