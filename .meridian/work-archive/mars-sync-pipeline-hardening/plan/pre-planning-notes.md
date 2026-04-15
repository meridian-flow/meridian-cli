# Pre-Planning Notes

## Codebase State (verified at planning time)

- 523 tests pass (483 unit + 30 integration + 10 doc)
- All source at /home/jimyao/gitrepos/mars-agents/
- CWD is meridian-cli, not mars-agents — coders must cd or use absolute paths for cargo commands
- Windows cross-compile target installed: x86_64-pc-windows-msvc
- Current deps: libc = "0.2.183" (Unix-only, used only in fs/mod.rs for flock)
- No existing windows-sys dependency

## Key File Sizes (lines)

- fs/mod.rs: 411 (locking lives here)
- sync/plan.rs: 547 (planner)
- sync/apply.rs: 1000 (apply phase)
- sync/mod.rs: 2007 (pipeline orchestration)
- types.rs: 425 (Materialization enum)
- reconcile/fs_ops.rs: 316 (atomic_symlink)
- reconcile/mod.rs: 168 (DesiredState/DestinationState)
- discover/mod.rs: 653 (InstalledItem.is_symlink)
- target_sync/mod.rs: 579 (target sync)
- cli/resolve_cmd.rs: 96 (resolve command)
- cli/doctor.rs: 203
- cli/output.rs: 454
- lock/mod.rs: 596
- cli/list.rs: 203
- merge/mod.rs: 359

## Parallelism Hypothesis

Round 1 (parallel):
- Phase A: R1 + REF-03 (cross-platform locking in fs/mod.rs, Cargo.toml)
- Phase B: REF-01 (symlink removal — types.rs, sync/*, reconcile/*, discover/*, cli/output.rs, cli/doctor.rs, lock/mod.rs, target_sync/mod.rs)

These are disjoint: Phase A touches fs/mod.rs + Cargo.toml. Phase B touches everything else.

Round 2 (parallel):
- Phase C: R2 + REF-02 (resolve_cmd lock + has_conflict_markers consolidation — cli/resolve_cmd.rs, cli/list.rs, merge/mod.rs)
- Phase D: R4 (skill conflicts — sync/plan.rs, sync/mod.rs)

Phase C depends on R1 (uses FileLock API). Phase D depends on REF-01 (simplified planner).
C and D are disjoint file-wise.

Round 3:
- Phase E: R5 + R6 (checksum integrity — sync/apply.rs, lock/mod.rs, target_sync/mod.rs, fs/mod.rs)

Depends on REF-01 (simplified apply.rs) and R4 (planner changes settled). Touches lock/mod.rs which Phase C reads but doesn't modify structurally.

## Feasibility Re-Check

Design says hand-roll locking. decisions.md D1 says use fs2. Architecture doc says hand-roll. **Contradiction.** D1 was written early, then the architecture doc revised to hand-roll. Architecture doc is more recent and more detailed. Decision: follow architecture (hand-roll with platform modules), record in decisions.md.

Note: libc stays as Unix dep, windows-sys added as Windows dep. Architecture doc confirms libc only used in fs/mod.rs for flock — verified via grep.

## Architecture doc says remove Cargo.toml libc

symlink-removal.md says "Remove libc (confirmed: only used for flock in fs/mod.rs)." But locking architecture keeps libc for Unix flock. **Conflict.** Resolution: keep libc (Unix-only dep) — the locking code still uses it. The symlink-removal architecture note was wrong; it assumed fs2 would replace libc.

## Edge Cases to Watch

1. reconcile/mod.rs DesiredState::Symlink removal — architecture doc explicitly calls this out (review finding B1)
2. cli/output.rs ActionTaken::Symlinked — review finding B2
3. cli/doctor.rs is_symlink dependency — review finding B3
4. Cargo.toml: libc stays (locking), windows-sys added (Windows locking target dep)
5. sync/target.rs TargetItem.materialization field removal — construction sites scattered
6. Post-write verification in apply.rs doubles I/O — acceptable per architecture decision
