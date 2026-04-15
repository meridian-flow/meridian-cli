# Round 2 Design Review — Refactor / Dev-Principles Focus

Review the Round 2 design package for the orphan-run reaper fix (GH issue #14). The user was explicit: "if we need to refactor, we should refactor. I don't want dead code or patchy stuff that is not good code." Your job is to make sure the refactor agenda is honest, complete, and doesn't leave dead or patchy code behind.

## Your focus

Apply `dev-principles` to the design package:

1. **Refactor early, refactor continuously.** Does the Round 2 agenda refactor structural problems the mechanism surfaces, rather than patching around them? Are preparatory refactors (decide/write split, consumer audit) sequenced before the feature work they support?
2. **Delete aggressively.** `update_spawn(status=...)` is being demoted — is it actually retired cleanly, or does the signature stay with hollow callers? Is `validate_transition` (currently dead) actually wired into the new helpers, not left orphaned? Is `exited_at` truly deferred correctly (R-08), or should it go now? Any other dead surface the agenda misses?
3. **Abstraction judgment.** Is the origin enum the right abstraction for 5 values? Is the `ReconciliationDecision` ADT warranted, or over-engineered for 3 variants? Is the pure `decide_reconciliation` splitting genuine business logic from I/O, or drawing an artificial line?
4. **Follow existing patterns.** Does the CAS pattern match how other state-layer code does flock + project + append? Does the heartbeat task style match existing asyncio patterns in `runner.py` / `streaming_runner.py`?
5. **Structural health signals.** `spawn_store.py` is already large; is R-02 / R-03 going to push it past the 500-line / 3-responsibility threshold? If so, does the agenda include a split or leave it as debt?
6. **Probe before you build.** Was the integration-boundary work (harness cadence probe P1) done with real evidence, and does the heartbeat design address observed reality?
7. **Keep docs current.** Are decisions.md, spec, architecture, and refactors in sync? Do the F1-F8 mapping entries in decisions.md reference the concrete spec/refactor IDs that implement them?
8. **Chesterton's Fence.** The Round 1 reaper rewrite (`2f5d391`) removed `_STALE_THRESHOLD_SECS = 300` and `_spawn_is_stale` without a replacement. Is the Round 2 replacement actually doing the job the deleted code did, or just covering a subset?

Also look for:

- **Patch-on-patch.** Does any Round 2 decision layer a new check on top of an existing one without replacing the underlying structure?
- **Dead code.** Anything introduced that won't have a caller? Anything preserved that could be deleted?
- **Missed deletions.** Does the agenda call out deletion where it's warranted, or does it err toward preservation?

## Package contents

Everything lives under `$MERIDIAN_WORK_DIR/`:

- `decisions.md` — D-1..D-15
- `design/spec/overview.md` — EARS statements
- `design/architecture/overview.md` — mechanism
- `design/refactors.md` — R-01..R-08 rearrangement agenda (this is the primary artifact for your review)
- `design/feasibility.md` — evidence
- Source files for reference: `src/meridian/lib/state/spawn_store.py`, `reaper.py`, `lib/core/spawn_lifecycle.py`, `lib/core/domain.py`, `lib/launch/runner.py`, `src/meridian/cli/spawn.py`, `src/meridian/lib/ops/spawn/api.py`

## Deliverable

Your review report should:

1. Enumerate findings by severity: **Blocker**, **Serious**, **Nit**.
2. For each finding, cite specific file or agenda item.
3. Call out missed deletions and patch-on-patch explicitly.
4. Confirm whether the refactor agenda is sufficient for the user's "no dead code, no patchy stuff" requirement, or name exactly what else it must include.

Return a terminal report via the standard report mechanism.
