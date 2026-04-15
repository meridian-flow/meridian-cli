# Phase 4: A4 — Shared Reconciliation Layer

**Round:** 2 (parallel with Phase 3 and Phase 5)
**Depends on:** Phase 1 (A1 — typed pipeline phases)
**Risk:** Medium — extracting shared code, must not regress atomicity
**Estimated delta:** ~+250 LOC (new module), ~-100 LOC (deduplication from apply.rs and link.rs)
**Codebase:** `/home/jimyao/gitrepos/mars-agents/`

## Scope

Extract shared filesystem operations and item-level reconciliation into a `reconcile` module (D11 — two layers). Layer 1: atomic fs primitives used by sync apply, link, and future target sync. Layer 2: item-level reconciliation (scan destination state → compute desired state → apply atomically).

## Why This Matters

Phase 7 (B3) needs reconciliation for copying content from `.mars/` to managed targets. Without a shared layer, B3 would either duplicate apply.rs logic or awkwardly call into sync internals. Extracting now means B3 imports clean primitives.

## Files to Create

| File | Contents |
|------|----------|
| `src/reconcile/mod.rs` | Re-exports. Layer 2 types and `reconcile_one()` function. |
| `src/reconcile/fs_ops.rs` | Layer 1: `atomic_write_file`, `atomic_install_dir`, `atomic_copy_file`, `atomic_copy_dir`, `atomic_symlink`, `safe_remove`, `content_hash`. |

## Files to Modify

| File | Changes |
|------|---------|
| `src/lib.rs` (or `src/main.rs`) | Add `mod reconcile;` |
| `src/sync/apply.rs` | Replace inline atomic operations with calls to `reconcile::fs_ops::*`. Replace inline destination scanning with `reconcile::scan_destination()` and `reconcile::reconcile_one()` where appropriate. Keep apply-specific logic (merge base caching, checksum computation, action outcome building). |
| `src/link.rs` | Replace inline atomic operations with calls to `reconcile::fs_ops::*`. Keep link-specific merge-unique-files algorithm. |
| `src/fs/mod.rs` | Move atomic write/lock operations to `reconcile::fs_ops` (or keep fs/mod.rs for lock-only operations and have reconcile import from it — decide based on what's cleaner). |

## Interface Contract — Layer 1 (Atomic FS Operations)

```rust
// src/reconcile/fs_ops.rs

/// Atomic file write via tmp+rename in the same directory.
pub fn atomic_write_file(dest: &Path, content: &[u8]) -> Result<(), MarsError>;

/// Atomic directory install: copy tree to tmp dir in same parent, then rename.
pub fn atomic_install_dir(source: &Path, dest: &Path) -> Result<(), MarsError>;

/// Atomic file copy: read source (following symlinks), write to tmp, rename to dest.
pub fn atomic_copy_file(source: &Path, dest: &Path) -> Result<(), MarsError>;

/// Atomic directory copy: deep copy source tree (following symlinks) to tmp, rename to dest.
pub fn atomic_copy_dir(source: &Path, dest: &Path) -> Result<(), MarsError>;

/// Create a symlink atomically (remove existing + create).
pub fn atomic_symlink(link_path: &Path, target: &Path) -> Result<(), MarsError>;

/// Remove a file or directory tree safely.
pub fn safe_remove(path: &Path) -> Result<(), MarsError>;
```

## Interface Contract — Layer 2 (Item-Level Reconciliation)

```rust
// src/reconcile/mod.rs

/// What exists at a destination path.
pub enum DestinationState {
    Empty,
    File { hash: ContentHash },
    Directory { hash: ContentHash },
    Symlink { target: PathBuf },
}

/// What we want at a destination path.
pub enum DesiredState {
    CopyFile { source: PathBuf, hash: ContentHash },
    CopyDir { source: PathBuf, hash: ContentHash },
    Symlink { target: PathBuf },
    Absent,
}

/// Result of reconciling one destination.
pub enum ReconcileOutcome {
    Created,
    Updated,
    Removed,
    Skipped { reason: &'static str },
    Conflict { existing: DestinationState, desired: DesiredState },
}

/// Scan a destination to determine its current state.
pub fn scan_destination(path: &Path) -> DestinationState;

/// Reconcile a single destination path.
pub fn reconcile_one(
    dest: &Path,
    desired: DesiredState,
    force: bool,
) -> Result<ReconcileOutcome, MarsError>;
```

## What's Shared vs. Module-Specific

- **Shared (reconcile/):** atomic fs ops, content hashing, destination scanning, item-level reconciliation
- **apply.rs keeps:** merge base caching, action outcome construction, checksum bookkeeping, the overall apply-plan-actions loop
- **link.rs keeps:** the merge-unique-files-then-adopt algorithm (one-time target directory adoption)

## Constraints

- **Pure refactor.** No behavioral change. The public API of `mars sync` and `mars link` is unchanged.
- **Atomicity guarantees preserved.** Every write path must remain tmp+rename. The extraction must not introduce a non-atomic code path.
- **`atomic_copy_file` and `atomic_copy_dir` are new.** They don't exist yet — they're needed by Phase 7 (B3) for target materialization. Implement them now so B3 can use them. They follow symlinks (reads the symlink target's content, writes a copy to dest).

## Patterns to Follow

Look at `src/fs/mod.rs` (405 LOC) for existing atomic write patterns. Look at `src/sync/apply.rs` (999 LOC) for how content is currently installed — find the inline tmp+rename patterns and extract them.

## Verification Criteria

- [ ] `cargo build` compiles cleanly
- [ ] `cargo test` — all existing tests pass
- [ ] `cargo clippy` — no new warnings
- [ ] `src/reconcile/mod.rs` and `src/reconcile/fs_ops.rs` exist
- [ ] `sync/apply.rs` uses `reconcile::fs_ops::*` for atomic operations (no inline tmp+rename)
- [ ] `link.rs` uses `reconcile::fs_ops::*` for atomic operations
- [ ] `atomic_copy_file` and `atomic_copy_dir` have unit tests (these are new functions)
- [ ] No behavior change in `mars sync` or `mars link` output

## Agent Staffing

- **Coder:** 1x gpt-5.3-codex
- **Reviewers:** 2x — correctness (atomicity guarantees, no race conditions in new copy functions), security (tmp file naming, no symlink attacks in copy operations)
- **Tester:** 1x unit-tester — write tests for `atomic_copy_file` and `atomic_copy_dir` following symlinks
