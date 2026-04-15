# Phase 2: Symlink-Removal Foundation (REF-01 + R3)

## Task

Remove all symlink creation and symlink-specific code from non-test paths in /home/jimyao/gitrepos/mars-agents/. This is a large atomic refactor — all changes must land together because Rust enum exhaustiveness will break partial removals.

## What to Remove/Change

### 1. src/types.rs — Remove Materialization enum

Remove the `Materialization` enum entirely. Remove any `use` of it elsewhere.

### 2. src/sync/target.rs — Remove materialization field from TargetItem

Remove the `materialization` field. Update all construction sites. TargetItem just tracks what to sync, not how.

### 3. src/sync/plan.rs — Remove PlannedAction::Symlink

- Remove `PlannedAction::Symlink { source_abs, dest_rel, kind, name }` variant
- Remove the `symlink_action()` helper function
- Remove all `Materialization::Symlink { source_abs }` match arms
- All DiffEntry variants now follow the single copy path

### 4. src/sync/apply.rs — Remove ActionTaken::Symlinked

- Remove `ActionTaken::Symlinked` variant
- Remove `PlannedAction::Symlink` match arm from `execute_action()` and `dry_run_action()`

### 5. src/sync/mod.rs — Change local package target building

`build_target_for_source()` currently sets `materialization: Materialization::Symlink { source_abs }` for local packages. Change to produce the same TargetItem as dependency items — no materialization field, standard copy behavior.

### 6. src/reconcile/fs_ops.rs — Remove atomic_symlink()

Remove the entire `atomic_symlink` function. Remove its test `atomic_symlink_replaces_existing_directory`. Keep `copy_dir_following_symlinks` — it's general purpose.

### 7. src/reconcile/mod.rs — Remove symlink variants

- Remove `DesiredState::Symlink { target: PathBuf }` variant
- Remove `DestinationState::Symlink { target: PathBuf }` variant
- Remove the `DesiredState::Symlink` match arm in `reconcile_one`
- In `DesiredState::CopyFile` and `DesiredState::CopyDir` match arms, remove `DestinationState::Symlink { .. }` arms
- In `scan_destination_checked`, when encountering a symlink, follow it via `fs::metadata` instead of `symlink_metadata` and report as File or Directory. This makes reconcile work even if legacy symlinks exist.

### 8. src/discover/mod.rs — Remove is_symlink field

- Remove `is_symlink` from `InstalledItem` struct
- Remove the `symlink_metadata()` check in `discover_installed()`
- Remove test `discover_installed_handles_symlinks` (uses unix-only symlink)

### 9. src/cli/doctor.rs — Update symlink handling

- Remove `is_symlink` filters (no items will be symlinks)
- Add on-the-fly `symlink_metadata()` check to detect legacy symlinks as anomalies
- Report them as warnings rather than silently skipping

### 10. src/cli/output.rs — Remove ActionTaken::Symlinked references

- Remove from count logic (~line 137)
- Remove from format logic (~line 196)

### 11. src/lock/mod.rs — Remove ActionTaken::Symlinked arm

- Remove the Symlinked match arm when building lock entries (~line 140)

### 12. src/target_sync/mod.rs — Simplify

- Update module-level doc comment (no more "symlinks in .mars/ are followed")
- Remove test `sync_follows_symlinks_in_mars_dir` (relies on unix-only symlink)

### 13. Test cleanup

- Tests using `make_symlink_target()` in plan.rs → remove or convert to copy targets
- Tests asserting `ActionTaken::Symlinked` → remove
- Tests using `std::os::unix::fs::symlink` in non-`#[cfg(unix)]` test code → remove

## Important: Do NOT touch

- `Cargo.toml` (do not remove libc — Phase 1 still needs it for locking)
- `src/fs/mod.rs` (Phase 1 owns this)
- `src/cli/resolve_cmd.rs` (Phase 3 owns this)

## Verification

Run from /home/jimyao/gitrepos/mars-agents/:
```bash
cargo build
cargo test
cargo clippy
cargo check --target x86_64-pc-windows-msvc
```

All must pass. The cargo check for Windows will likely fail on the current locking code in fs/mod.rs — that's Phase 1's problem. If Phase 1 hasn't landed yet, just verify with `cargo build && cargo test && cargo clippy`.

## EARS Claims

This phase satisfies: SYM-01 through SYM-09.
