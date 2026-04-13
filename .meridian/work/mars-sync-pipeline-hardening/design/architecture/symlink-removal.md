# Architecture: Symlink Elimination (R3)

## Scope of Removal

Symlinks are used for one purpose: `_self` (local package) items are symlinked into `.mars/` so edits propagate instantly. After this change, local package items are copied like any dependency item. Edits require `mars sync` to propagate.

## Type Changes

### `types.rs` — Remove `Materialization::Symlink`

```rust
// Before:
pub enum Materialization {
    Copy,
    Symlink { source_abs: PathBuf },
}

// After:
// Materialization enum is removed entirely. All items are copy-materialized.
// Any code referencing Materialization::Copy can be simplified to remove the match.
```

**Decision:** Rather than keeping a single-variant enum, remove `Materialization` entirely. Every `TargetItem` that had a `materialization` field loses it. Code that matched on `Materialization::Copy` vs `Materialization::Symlink` collapses to the copy path only.

### `sync/plan.rs` — Remove `PlannedAction::Symlink`

```rust
// Remove this variant entirely:
PlannedAction::Symlink {
    source_abs: PathBuf,
    dest_rel: DestPath,
    kind: ItemKind,
    name: ItemName,
}
```

Remove the `symlink_action()` helper function.

Remove all `Materialization::Symlink { source_abs }` match arms from the `create()` function. Every `DiffEntry` variant now has a single code path (the copy path).

### `sync/apply.rs` — Remove `ActionTaken::Symlinked`

Remove the `PlannedAction::Symlink` match arm from `execute_action()` and `dry_run_action()`.
Remove `ActionTaken::Symlinked` from the enum.

### `sync/target.rs` (TargetItem)

Remove the `materialization` field from `TargetItem`. Update all construction sites.

## Code Path Changes

### `sync/mod.rs` — Local package target building

The `build_target_for_source()` function currently sets `materialization: Materialization::Symlink { source_abs }` for local package items. Change to produce the same `TargetItem` as dependency items — no `materialization` field, standard copy behavior.

The `source_abs` path was used to create the symlink target. After removal, the `source_path` field on `TargetItem` (which already exists and points to the absolute source path) is sufficient for the copy operation.

### `reconcile/fs_ops.rs` — Remove `atomic_symlink()`

Remove the entire `atomic_symlink` function (lines 55-117). Remove its test `atomic_symlink_replaces_existing_directory`.

The `copy_dir_following_symlinks` helper can remain — it's general-purpose and handles broken symlinks gracefully. After R3, it won't encounter symlinks in the `.mars/` tree, but keeping it is defensive.

### `reconcile/mod.rs` — Remove symlink variants from reconcile layer

**Review finding (B1 from structural reviewer):** The `reconcile/mod.rs` module has `DesiredState::Symlink` and `DestinationState::Symlink` variants, plus `reconcile_one` match arms that call `atomic_symlink`. These must be removed alongside `atomic_symlink()`.

Changes:
- Remove `DesiredState::Symlink { target: PathBuf }` variant
- Remove `DestinationState::Symlink { target: PathBuf }` variant
- Remove the `DesiredState::Symlink` match arm in `reconcile_one` (lines 118-139)
- In `DesiredState::CopyFile` and `DesiredState::CopyDir` match arms, remove the `DestinationState::Symlink { .. }` arms that call `safe_remove + copy`. These should fall through to the general "existing_state" branch.
- In `scan_destination_checked`, remove the symlink check. When encountering a symlink, follow it via `fs::metadata` instead of `symlink_metadata` and report as File or Directory based on the resolved type. This makes the reconcile layer work correctly even if legacy symlinks exist on disk.

**Decision on scope:** R3 says "No symlink creation anywhere in non-test code." The `reconcile` module is a general utility, but there are no consumers of `DesiredState::Symlink` outside the sync pipeline. Remove it entirely — if a future use case needs symlinks, it can be re-added.

### `discover/mod.rs` — Remove `is_symlink` field

Remove `is_symlink` from `InstalledItem`. Remove the `symlink_metadata()` check in `discover_installed()`. Remove the test `discover_installed_handles_symlinks` (uses `std::os::unix::fs::symlink`).

**Review finding (B3 from structural reviewer):** `cli/doctor.rs` depends on `InstalledItem.is_symlink` to skip symlinked items from validation (lines 99, 118, 125). After removal:
- The `is_self_symlink` check becomes unnecessary since no items will be symlinks.
- The `filter(|s| !s.is_symlink)` filters can be removed — all items are regular files/dirs.
- If legacy `.agents/` symlinks exist from a pre-R3 install, `mars doctor` should detect and report them as anomalies (using on-the-fly `symlink_metadata()` check) rather than silently skipping. This is an improvement over the current behavior.

### `cli/output.rs` — Remove `ActionTaken::Symlinked` references

**Review finding (B2 from structural reviewer):** `ActionTaken::Symlinked` is referenced in:
- `cli/output.rs:137` — count symlinked as installed
- `cli/output.rs:196` — format symlinked in output

Both references collapse: remove `ActionTaken::Symlinked` from match arms. Since it's removed from the enum, the compiler enforces exhaustiveness — all sites must be updated in the same commit.

### `lock/mod.rs` — Remove `ActionTaken::Symlinked` arm

`lock/mod.rs:140` matches on `ActionTaken::Symlinked` when building lock entries. Remove this arm.

### `target_sync/mod.rs` — Simplify

The comment "Symlinks in .mars/ (from local packages) are followed" at the module top becomes obsolete. The `copy_item_to_target` function uses `fs::metadata()` which follows symlinks — this continues to work correctly but the symlink case is dead. Update the module-level doc comment.

The test `sync_follows_symlinks_in_mars_dir` should be removed since it relies on `std::os::unix::fs::symlink`.

## Test Changes

Tests using `make_symlink_target()` in `sync/plan.rs` tests → remove or convert to copy targets.
Tests using `std::os::unix::fs::symlink` in non-`#[cfg(unix)]` test code → remove.
Tests asserting `ActionTaken::Symlinked` → remove.

## Files Changed (Summary)

| File | Change |
|---|---|
| `src/types.rs` | Remove `Materialization` enum |
| `src/sync/plan.rs` | Remove `PlannedAction::Symlink`, `symlink_action()`, symlink match arms |
| `src/sync/apply.rs` | Remove `ActionTaken::Symlinked`, `PlannedAction::Symlink` handler |
| `src/sync/mod.rs` | Change local-package target building from Symlink to Copy materialization |
| `src/sync/target.rs` | Remove `materialization` field from `TargetItem` |
| `src/reconcile/fs_ops.rs` | Remove `atomic_symlink()` |
| `src/reconcile/mod.rs` | Remove `DesiredState::Symlink`, `DestinationState::Symlink`, symlink match arms |
| `src/discover/mod.rs` | Remove `InstalledItem.is_symlink` |
| `src/cli/doctor.rs` | Remove `is_symlink` filters, add anomaly detection for legacy symlinks |
| `src/cli/output.rs` | Remove `ActionTaken::Symlinked` match arms |
| `src/lock/mod.rs` | Remove `ActionTaken::Symlinked` arm in lock building |
| `src/target_sync/mod.rs` | Update docs, remove symlink test |
| `Cargo.toml` | Remove `libc` (confirmed: only used for flock in fs/mod.rs) |
