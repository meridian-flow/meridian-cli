# Spec: Symlink Elimination (R3)

## Materialization

### SYM-01: No symlink creation in non-test code
The system shall not create symlinks in any non-test code path.
The `PlannedAction::Symlink` variant shall be removed from the codebase.

### SYM-02: Local package items use copy materialization
When a local package (`_self` source) declares items,
the system shall materialize them via copy (not symlink) into `.mars/`.

### SYM-03: Materialization enum simplification
The `Materialization` enum shall have only the `Copy` variant.
The `Symlink { source_abs }` variant shall be removed.

### SYM-04: atomic_symlink function removal
The `atomic_symlink` function in `reconcile/fs_ops.rs` shall be removed entirely.

## Sync Pipeline Cleanup

### SYM-05: Planner has no symlink branch
The sync planner (`sync/plan.rs`) shall not contain any symlink-specific branching logic.
All items, including `_self` source items, shall follow the copy planning path.

### SYM-06: Apply has no symlink handler
The sync apply phase (`sync/apply.rs`) shall not contain a `PlannedAction::Symlink` match arm.
The `ActionTaken::Symlinked` variant shall be removed.

### SYM-07: Target sync has no symlink-following special case
The target sync layer (`target_sync/mod.rs`) shall copy from `.mars/` to targets without any symlink-specific branching. The existing `copy_item_to_target` already follows symlinks via `fs::metadata`; after R3 the source side will never be a symlink, but the code should remain robust (no crash on unexpected symlinks).

### SYM-08: Discover installed removes symlink field
The `InstalledItem.is_symlink` field in `discover/mod.rs` shall be removed,
since no installed items will be symlinks after this change.

## Propagation Semantics

### SYM-09: Self-source edit propagation requires sync
When a user edits a local package source file,
the system shall not propagate the change to `.mars/` or `.agents/` automatically.
The user must run `mars sync` to propagate changes.
