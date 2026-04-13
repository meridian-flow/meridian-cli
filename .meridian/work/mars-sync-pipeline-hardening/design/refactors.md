# Refactor Agenda

Structural rearrangements that must be sequenced before feature work. Each refactor unlocks simpler implementations for the feature requirements.

## REF-01: Remove Materialization enum and PlannedAction::Symlink

**Unlocks:** R4 (skill conflicts), R5 (checksum discipline)
**Sequence:** First — this is the foundational refactor.

Remove `Materialization` enum from `types.rs`. Remove `PlannedAction::Symlink` variant. Remove `ActionTaken::Symlinked` variant. Remove `atomic_symlink()` from `reconcile/fs_ops.rs`. Remove `is_symlink` from `InstalledItem`.

This collapses every match on `Materialization` in `sync/plan.rs` from two arms to one. The planner code becomes ~50% shorter and R4's conflict-handling change operates on a simpler structure.

**Files touched:** `types.rs`, `sync/plan.rs`, `sync/apply.rs`, `sync/mod.rs`, `sync/target.rs`, `reconcile/fs_ops.rs`, `reconcile/mod.rs`, `discover/mod.rs`, `target_sync/mod.rs`

## REF-02: Consolidate has_conflict_markers implementations

**Unlocks:** R2 (cleaner resolve_cmd.rs)
**Sequence:** During R2 implementation (resolve_cmd.rs is being modified anyway).

Move the correct implementation from `merge/mod.rs` to a shared location or make `merge::has_conflict_markers` pub and add a file-level wrapper. Remove duplicate implementations from `cli/resolve_cmd.rs` and `cli/list.rs`.

**Files touched:** `merge/mod.rs`, `cli/resolve_cmd.rs`, `cli/list.rs`

## REF-03: Remove libc dependency

**Unlocks:** Cleaner dependency tree, Windows compilation
**Sequence:** After R1 (cross-platform locking replaces the only libc usage). Depends on feasibility probe confirming no other `libc::` usages.

**Files touched:** `Cargo.toml`, `src/fs/mod.rs`
