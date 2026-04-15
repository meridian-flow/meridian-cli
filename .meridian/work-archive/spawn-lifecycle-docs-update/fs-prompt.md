# Task: Update fs/ Domain Docs for Spawn-Lifecycle / Reaper Refactor

Update the agent-facing codebase mirror (`$MERIDIAN_FS_DIR`) to reflect commits f6d9f20..27d5237 on main (issue #14 PR1+PR2 + final-review). The refactor introduced a `finalizing` lifecycle state, decide/IO split in the reaper, projection authority via `SpawnOrigin`, and runner-owned heartbeat.

## Scope

Update (read first, revise in place — do not wholesale rewrite what's still accurate):

- `$MERIDIAN_FS_DIR/state/spawns.md` — lifecycle states, transitions, projection authority rule, `update_spawn`/`finalize_spawn`/`mark_finalizing` API shape
- `$MERIDIAN_FS_DIR/state/overview.md` — if it enumerates statuses or reconciler behavior
- `$MERIDIAN_FS_DIR/launch/process.md` — runner heartbeat ownership (30s tick, outer-finally cancel), `mark_finalizing` CAS call after harness exit and before drain
- `$MERIDIAN_FS_DIR/launch/overview.md` — touch if it describes lifecycle/drain
- `$MERIDIAN_FS_DIR/ops/` — if any reconciler/reaper doc exists there, otherwise consider adding a focused reaper section where it fits best (check existing structure first; do not invent new domains)
- `$MERIDIAN_FS_DIR/overview.md` — if it enumerates statuses or mentions orphan classification

Do NOT touch `docs/` — a separate @tech-writer spawn handles that. Do NOT touch CHANGELOG.

## Key architectural facts to capture

1. **`finalizing` state**: new intermediate state between `running` and terminal. `ACTIVE_SPAWN_STATUSES = {queued, running, finalizing}` in `src/meridian/lib/core/spawn_lifecycle.py`. `_ALLOWED_TRANSITIONS` permits `running → finalizing → {succeeded|failed|cancelled}`. `queued → finalizing` NOT allowed — cancellations from queued go direct to `cancelled`.
2. **Runner owns heartbeat**: 30s periodic task started in runner, cancelled in outer `finally`. Covers queued + running + finalizing. Replaces previous ad-hoc heartbeat writes.
3. **Runner calls `mark_finalizing`**: after harness exit, before drain/report emission. CAS transition; failure logged and swallowed (drain still runs).
4. **Reaper decide/IO split**: `_collect_artifact_snapshot` (pure read) + `decide_reconciliation` (pure function over snapshot + clock) + IO shell applies the decision. Easier to test, deterministic.
5. **Reaper gates**: depth-gated on entry (only depth-0 reconciles). Heartbeat staleness window 120s. Startup grace 15s (recent spawn records not reaped). PID-reuse margin 30s (PID must be stale longer than reuse margin before trusted as dead).
6. **New orphan classifications**: `orphan_finalization` (reaped from `finalizing` state — harness crashed during drain/report) vs `orphan_run` (reaped from `running` state). Distinguishable for triage.
7. **Projection authority rule**: `SpawnOrigin` enum with `AUTHORITATIVE_ORIGINS = {runner, launcher, launch_failure, cancel}`. `finalize_spawn(..., origin=SpawnOrigin.X)` — `origin` kwarg is mandatory. Reconciler writes use a non-authoritative origin (e.g. `reconciler`). In `_record_from_events`, a later authoritative finalize event overwrites an earlier non-authoritative finalize — so if the runner reports after the reaper stamped an orphan, the runner's terminal state wins. This is the mechanism that lets reconciler be aggressive without losing ground-truth.
8. **`update_spawn` lifecycle-lock**: no longer accepts `status=`. Lifecycle transitions go only through `mark_finalizing` and `finalize_spawn`. Callers that previously wrote status via `update_spawn` must be updated (this is already done in-tree — just document the API contract).
9. Fixes issue #14, which covered the orphan-run reaper race where a premature reap raced a slow harness exit and overwrote the real terminal state.

## Context & reference files

Canonical source:
- `src/meridian/lib/core/spawn_lifecycle.py` — states, transitions, SpawnOrigin
- `src/meridian/lib/state/spawn_store.py` — `update_spawn`, `mark_finalizing`, `finalize_spawn`, `_record_from_events`
- `src/meridian/lib/state/reaper.py` — decide/IO split, classifications, gates
- `src/meridian/lib/launch/runner.py` — heartbeat task, `mark_finalizing` call
- `src/meridian/lib/launch/streaming_runner.py` — parallel streaming path

Design package (archived, authoritative on *why*):
- `.meridian/work-archive/orphan-run-reaper-fix/decisions.md`
- `.meridian/work-archive/orphan-run-reaper-fix/design/` (spec + architecture)
- `.meridian/work-archive/orphan-run-reaper-fix/requirements.md`

Read decisions.md carefully — it captures the authority-model rationale, why heartbeat moved to the runner, why decide/IO split, and the PID-reuse margin choice.

## Output requirements

- Keep docs concise, agent-facing, observational. Don't paste code verbatim — describe contracts and invariants. Cross-link between `state/spawns.md` and `launch/process.md` where authority handoff happens.
- Preserve existing structure/headings unless the structure no longer fits. Caveman-style is fine but not required; match surrounding tone.
- When describing the authority rule, be explicit that a late runner finalize *can and should* overwrite a reconciler finalize. This is a feature, not a bug — document it as such.
- Do NOT create brand-new top-level domains. Fit revisions into existing files.
- Commit is handled by the orchestrator — do not run git.
