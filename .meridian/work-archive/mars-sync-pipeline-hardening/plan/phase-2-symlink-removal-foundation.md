# Phase 2: Symlink-Removal Foundation

## Round

Round 1, parallel with Phase 1.

## Scope and Boundaries

Execute REF-01 and R3 as one atomic refactor across the sync pipeline. Remove symlink creation, symlink-specific action variants, and installed-item symlink tracking from non-test code. This phase establishes the copy-only pipeline that later conflict-handling and checksum work build on. It does not add the skill-conflict overwrite policy; that narrower behavior lands in Phase 4.

## Touched Files and Modules

- `/home/jimyao/gitrepos/mars-agents/src/types.rs`
- `/home/jimyao/gitrepos/mars-agents/src/sync/plan.rs`
- `/home/jimyao/gitrepos/mars-agents/src/sync/apply.rs`
- `/home/jimyao/gitrepos/mars-agents/src/sync/mod.rs`
- `/home/jimyao/gitrepos/mars-agents/src/sync/target.rs`
- `/home/jimyao/gitrepos/mars-agents/src/reconcile/fs_ops.rs`
- `/home/jimyao/gitrepos/mars-agents/src/reconcile/mod.rs`
- `/home/jimyao/gitrepos/mars-agents/src/discover/mod.rs`
- `/home/jimyao/gitrepos/mars-agents/src/cli/doctor.rs`
- `/home/jimyao/gitrepos/mars-agents/src/cli/output.rs`
- `/home/jimyao/gitrepos/mars-agents/src/lock/mod.rs`
- `/home/jimyao/gitrepos/mars-agents/src/target_sync/mod.rs`

## Claimed EARS Statement IDs

- `SYM-01`
- `SYM-02`
- `SYM-03`
- `SYM-04`
- `SYM-05`
- `SYM-06`
- `SYM-07`
- `SYM-08`
- `SYM-09`

## Touched Refactor IDs

- `REF-01`

## Dependencies

- None.
- Must land as a compile-complete pass because enum exhaustiveness will break partial removals.

## Tester Lanes

- `@verifier`: confirm all non-test symlink-creation paths are gone and the planner/apply/discover/output/lock exhaustiveness is complete.
- `@smoke-tester`: run `cargo build`, `cargo test`, `cargo clippy`, and `cargo check --target x86_64-pc-windows-msvc` from `/home/jimyao/gitrepos/mars-agents/`; exercise a local-package sync and doctor pass.
- `@unit-tester`: add or adjust focused tests around reconcile scanning, target item construction, and legacy symlink anomaly reporting.

## Edge Cases and Constraints

- Remove `DesiredState::Symlink` and `DestinationState::Symlink` from `reconcile/mod.rs`; do not stop at `atomic_symlink()`.
- Remove `InstalledItem.is_symlink`, but make `mars doctor` report legacy symlinks as anomalies instead of silently ignoring them.
- Update `cli/output.rs` and `lock/mod.rs` in the same phase so removed enum variants do not leave dead branches.
- Do not remove `libc` from `Cargo.toml`; Phase 1 still owns Unix locking.

## Exit Criteria

- No non-test code path creates symlinks.
- `_self` items materialize through the same copy path as dependency items.
- `Materialization`, `PlannedAction::Symlink`, `ActionTaken::Symlinked`, `atomic_symlink()`, and `InstalledItem.is_symlink` are removed.
- `mars sync` still requires an explicit rerun to propagate local source edits.
- `cargo build`, `cargo test`, `cargo clippy`, and `cargo check --target x86_64-pc-windows-msvc` pass from `/home/jimyao/gitrepos/mars-agents/`.
