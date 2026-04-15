# Architecture: Checksum Validation Discipline (R5, R6)

## R5: Mandatory Checksums

### Problem 1: Optional checksums silently decay

`ActionOutcome.installed_checksum` is `Option<ContentHash>`. For Skip, KeepLocal, and Remove actions, None is correct — no write occurred. But for Install, Overwrite, and Merge, None means a checksum computation failed silently, and the lock file gets built with empty/missing data.

### Solution: Enforce at lock-building time

In `lock/mod.rs::build()` (or wherever `LockFile` is constructed from outcomes), validate that every write-producing outcome (`Installed`, `Updated`, `Merged`) has a `Some` installed_checksum. If any is None, return an error rather than persisting corrupt lock state.

```rust
// In lock building:
for outcome in &applied.outcomes {
    match outcome.action {
        ActionTaken::Installed | ActionTaken::Updated | ActionTaken::Merged | ActionTaken::Conflicted => {
            if outcome.installed_checksum.is_none() {
                return Err(MarsError::Lock {
                    message: format!("missing checksum for {}", outcome.dest_path),
                });
            }
        }
        _ => {} // Skip, Kept, Removed — no checksum expected
    }
}
```

### Problem 2: Post-write verification gap

Currently `install_item()` computes the hash of the written content but doesn't verify the write succeeded correctly. For agents, the hash is computed from the in-memory bytes that were written. For skills, the hash is computed by re-reading the installed directory — this IS a post-write verification implicitly, but only for skills.

### Solution: Explicit post-write verify for agents

After `atomic_write_file` for agents, re-read the file and verify the hash matches:

```rust
// In install_item for Agent:
let content = content_to_install(target)?;
fs_ops::atomic_write_file(dest, &content)?;
let expected_hash = ContentHash::from(crate::hash::hash_bytes(&content));
// Verify what was written
let written = std::fs::read(dest)?;
let actual_hash = ContentHash::from(crate::hash::hash_bytes(&written));
if expected_hash != actual_hash {
    return Err(MarsError::Sync {
        message: format!("post-write verification failed for {}", dest.display()),
    });
}
Ok(expected_hash)
```

**Performance note:** This doubles the I/O for agent installs (read-back after write). For a package manager writing tens of files, not hundreds of thousands, this is acceptable. Skills already re-hash the directory after install.

## R5: Disk-Lock Divergence Detection

### Problem

When sync starts, the diff phase compares `target.source_hash` against `lock.source_checksum` to detect source changes, and compares `disk_hash` against `lock.installed_checksum` to detect local changes. But if `lock.installed_checksum` is wrong (because a prior sync wrote it incorrectly, or the file was modified outside mars), the diff can produce false `Unchanged` entries.

The "read-only `.agents/`" bug: target sync fails silently, lock is already advanced. Next sync sees lock = disk (both wrong) and skips.

### Solution: Two-layer verification

**Layer 1: Emit divergence warnings in diff phase (informational)**

In `sync/diff.rs::compute()`, when an item is found to be `Unchanged` (neither source nor local changed), add an optional verification step: if the disk path exists, re-check the hash. This is already done — the disk hash IS checked against `installed_checksum`. The issue isn't in diff itself but in the target sync layer.

**Layer 2: Target sync must report failures that prevent lock advancement**

The real bug is in `sync/mod.rs::finalize()`: the lock is written after apply succeeds, regardless of whether target sync succeeded. If target sync fails for an item, the lock still records the new `installed_checksum` — but the target directory has stale content.

Fix: `finalize()` should check target sync outcomes. If any target reported errors for an item, that's a warning but not a lock-advancement blocker (the `.mars/` canonical store has the correct content; it's the target copy that failed). However, the sync should exit with a non-zero code so the caller knows something went wrong.

The permanent drift bug specifically happens because:
1. `.mars/` gets the correct content (lock advances)
2. `.agents/` (target) fails to receive the copy
3. Next sync sees `.mars/` matches lock → Unchanged → skips target sync for that item

**Fix in target sync:** When `ActionTaken::Skipped` items exist in the target sync phase, verify the target actually has the content. The current code already does this — for `Skipped` items, it copies if `!dest.exists()`. But it doesn't check if the content is correct (file exists but has wrong content).

**Architecture decision:** Add a target-divergence check: for `Skipped` items in target sync, verify target matches expected state. Re-copy if divergent.

**Performance concern (review finding):** Hashing every skipped item on every target can be expensive, especially for skill directories that require walking the tree. Mitigations:

1. **Use lock's `installed_checksum` as expected hash** — don't re-hash `.mars/`. The lock already records what was written. Compare target hash against `installed_checksum` from the lock. This requires threading expected checksums into target sync (via the `ActionOutcome` for skipped items, which currently has `installed_checksum: None`).

2. **Populate `installed_checksum` on Skip outcomes** — When building skip outcomes in `sync/apply.rs`, look up the lock's `installed_checksum` and carry it forward. This avoids any new `.mars/` I/O.

3. **Heuristic gate:** Check `exists()` + `metadata().len()` before hashing. For agents (single files), a size mismatch is a fast reject. For skills, fallback to hash only if size matches. This handles the common "file missing" case without hashing.

```rust
// In sync_one_target, for ActionTaken::Skipped:
let source = mars_dir.join(dest_rel);
let dest = target_root.join(dest_rel);
if source.exists() {
    if !dest.exists() {
        // Missing target — re-copy
        copy_item_to_target(&source, &dest)?;
    } else if force {
        // --force: always overwrite
        copy_item_to_target(&source, &dest)?;
    } else if let Some(expected) = &outcome.installed_checksum {
        // Check for divergence (manual edit or stale from failed prior copy)
        let target_hash = crate::hash::compute_hash(&dest, outcome.item_id.kind)
            .map(ContentHash::from)
            .ok();
        if target_hash.as_ref() != Some(expected) {
            // Divergent: warn but preserve local content
            diag.warn("target-divergent", format!(
                "{} has local modifications — run `mars sync --force` or `mars repair` to reset",
                dest_rel
            ));
        }
    }
}
```

This approach:
- Hashes each target item at most once per sync (not per-target — can cache if multiple targets exist)
- Never re-hashes `.mars/` content
- Falls back to "assume OK" when no expected hash is available (graceful degradation)
- **Preserves manual edits** — warns but does not overwrite. User opts in to overwrite via `--force` or `mars repair`
- **Re-copies only missing targets** — handles the "failed prior copy" case without clobbering edits

## R6: Unix Permission Gating

### Verification Result

The existing `#[cfg(unix)]` gating is sufficient:

1. `fs/mod.rs:34-37` — `PermissionsExt::from_mode(0o644)` on temp files → gated
2. `reconcile/fs_ops.rs:176-179` — `PermissionsExt::from_mode(0o644)` on copied files → gated

On Windows, files get default permissions (inheriting from parent directory ACLs). This is correct behavior.

### Read-only file handling

One risk: Windows files can be marked read-only, and `fs::rename` (used in `atomic_write`) may fail if the destination is read-only. Rust's `fs::rename` on Windows calls `MoveFileExW` which can fail on read-only destinations.

**Mitigation:** In `atomic_write` and `atomic_install_dir`, before the rename step, if the destination exists and is read-only on Windows, clear the read-only attribute:

```rust
#[cfg(windows)]
fn clear_readonly(path: &Path) -> std::io::Result<()> {
    let metadata = std::fs::metadata(path)?;
    let mut perms = metadata.permissions();
    if perms.readonly() {
        perms.set_readonly(false);
        std::fs::set_permissions(path, perms)?;
    }
    Ok(())
}
```

This is defensive code — it's unlikely to be hit in practice but prevents a class of mysterious failures on Windows.

## Files Changed (Summary)

| File | Change |
|---|---|
| `src/sync/apply.rs` | Post-write verification for agents |
| `src/sync/mod.rs` (finalize) | Validate checksums before lock write |
| `src/lock/mod.rs` (build) | Reject None checksums on write-producing outcomes |
| `src/target_sync/mod.rs` | Content-hash comparison for skipped items, target divergence detection |
| `src/fs/mod.rs` | Windows read-only file handling (defensive) |
