# Phase 5: Checksum Integrity and Target Divergence

## Task

Implement R5 (checksum discipline) and R6 (Windows permission handling) in /home/jimyao/gitrepos/mars-agents/. This is the final phase — build, test, clippy, and fmt must all pass.

## Changes Needed

### 1. Mandatory checksums for write actions (CKSUM-01, CKSUM-02)

In `src/lock/mod.rs` — when building a new lock file from apply outcomes, validate that every write-producing outcome has a non-None checksum:

```rust
// In lock building (the build() function), add validation:
for outcome in &applied.outcomes {
    match outcome.action {
        ActionTaken::Installed | ActionTaken::Updated | ActionTaken::Merged | ActionTaken::Conflicted => {
            if outcome.installed_checksum.is_none() {
                return Err(MarsError::Lock {
                    message: format!("missing checksum for write-producing action on {}", outcome.dest_path),
                });
            }
        }
        _ => {} // Skip, Kept, Removed — no checksum expected
    }
}
```

Also ensure empty-string checksums are rejected. Check if `installed_checksum` or `source_checksum` could be empty strings and add validation.

### 2. Post-write verification (CKSUM-03)

In `src/sync/apply.rs` — after writing a file during Install or Overwrite, re-read and verify the hash:

For agents (single files), after `atomic_write_file`:
- Read back the written file
- Hash the read-back content
- Compare against expected hash
- Error if mismatch

For skills (directories), the existing `install_skill_dir` already hashes the installed directory. Verify the pattern is correct.

### 3. Merge checksum (CKSUM-04)

In `src/sync/apply.rs` — ensure merge outcomes carry the merged content's checksum as `installed_checksum`. Check current merge path and add hash computation if missing.

### 4. Disk-lock divergence detection (CKSUM-05, CKSUM-06, CKSUM-07)

This is about detecting when managed items in `.mars/` have been modified outside of mars. 

In `src/sync/diff.rs` or at the start of sync in `src/sync/mod.rs`:
- For items the lock says are unchanged (same source hash), verify the disk hash matches `installed_checksum`
- If divergent, warn but preserve the local content
- User must run `--force` or `mars repair` to reset

### 5. Target divergence detection (CKSUM-08, CKSUM-09)

In `src/target_sync/mod.rs`:
- For items that were skipped in the sync (unchanged in .mars/), verify targets match canonical .mars/ content
- Missing targets: re-copy from .mars/
- Divergent targets (different hash): warn and preserve, don't overwrite
- To do this, carry expected checksums into skip outcomes in apply.rs

In `src/sync/apply.rs`, for Skip actions:
- Look up the lock's installed_checksum and populate it on the skip outcome
- This lets target_sync know what hash to expect without re-hashing .mars/

### 6. Windows read-only handling (PERM-01, PERM-02)

In `src/fs/mod.rs`, add a defensive helper:

```rust
#[cfg(windows)]
pub fn clear_readonly(path: &Path) -> std::io::Result<()> {
    if let Ok(metadata) = std::fs::metadata(path) {
        let mut perms = metadata.permissions();
        if perms.readonly() {
            perms.set_readonly(false);
            std::fs::set_permissions(path, perms)?;
        }
    }
    Ok(())
}
```

Call this before overwrite operations in reconcile/fs_ops.rs (before rename/delete of existing destination).

PERM-01: Verify existing #[cfg(unix)] PermissionsExt is preserved. Don't change it.

## Files to Touch

- /home/jimyao/gitrepos/mars-agents/src/sync/apply.rs
- /home/jimyao/gitrepos/mars-agents/src/sync/mod.rs
- /home/jimyao/gitrepos/mars-agents/src/sync/diff.rs
- /home/jimyao/gitrepos/mars-agents/src/lock/mod.rs
- /home/jimyao/gitrepos/mars-agents/src/target_sync/mod.rs
- /home/jimyao/gitrepos/mars-agents/src/fs/mod.rs

## Verification

```bash
cargo build && cargo test && cargo clippy && cargo fmt --check
```

## EARS Claims

CKSUM-01, CKSUM-02, CKSUM-03, CKSUM-04, CKSUM-05, CKSUM-06, CKSUM-07, CKSUM-08, CKSUM-09, PERM-01, PERM-02

## Key Constraints

- Lock advancement tracks .mars/ state, NOT target state. Target failures don't block lock writes.
- Divergent items are PRESERVED (warned, not overwritten). User opts in via --force or repair.
- Missing targets are re-copied (self-healing).
- Post-write verify doubles I/O for agents — acceptable per architecture decision.
- Keep existing #[cfg(unix)] permission gating unchanged.
