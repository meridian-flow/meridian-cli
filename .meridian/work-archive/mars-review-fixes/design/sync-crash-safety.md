# F12 + F13: Sync Crash Safety

## F12: Sync Pipeline Not Retry-Safe

### Problem

The sync pipeline in `src/sync/mod.rs` saves config at step 15 (before apply) and lock at step 17 (after apply). If mars crashes during step 16 (apply), the state is:

- **Config**: updated (new source added/removed)
- **Lock**: stale (still reflects old state)
- **Disk**: partially installed (some files from the new source, not all)

On the next `mars sync`, the resolver reads the updated config and builds a target state. The stale lock says the old items exist. The diff between them may not correctly identify the partially-installed files, leading to:
- Unmanaged file collision errors (new files on disk not in lock)
- Missing file reports (lock says files exist but apply was interrupted)

### Current Pipeline Order

```
Step 15: Save config (if mutation)       ← crash here = config updated, disk/lock stale
Step 16: Apply plan (install/remove)     ← crash here = disk partial, lock stale
Step 17: Write lock                      ← only reached on success
```

### Design: Keep Current Order, But Handle Partial State on Recovery

**The original proposal (move config save after apply) was rejected by review.** The reviewer correctly identified that `mars sync` runs with `mutation: None` — it doesn't replay the original mutation. After a crash where lock was updated but config wasn't, `mars sync` would see lock items not in config and treat them as orphans.

The current order (config first, then apply, then lock) is actually the safer of the two:
- Config saved → crash during apply → `mars sync` re-resolves from new config, re-applies. **This converges** because the new config is the source of truth, and sync re-derives the full plan.
- The only issue is that partially-installed files (on disk but not in lock) may trigger unmanaged-collision detection.

**Fix: Make unmanaged-collision detection tolerant of partially-installed state.**

In `src/sync/target.rs`, the `check_unmanaged_collisions` function blocks sync when a planned install would overwrite a file that exists on disk but isn't in the lock. After a crash, this is exactly the state: files from the interrupted apply are on disk, not in lock.

The fix: when the file on disk matches the content we're about to install (same hash), skip the collision error — it's a partially-completed prior install, not an unmanaged user file.

```rust
// In check_unmanaged_collisions, when file exists on disk but not in lock:
// Check if disk content matches what we'd install
if disk_hash == planned_hash {
    // Partial prior install — safe to overwrite
    continue;
}
// Otherwise: genuine unmanaged collision, error as before
```

This is the minimal change that makes the existing pipeline crash-safe without reordering.

### Alternative Considered: Reorder Config Save to After Apply

Moving config save to after apply+lock was the initial design. **Rejected** because:
- `mars sync` (the recovery path) runs with `mutation: None` — it reads config as-is
- If lock was written but config wasn't, lock contains items that config doesn't request → sync computes removal of those items, undoing the successful apply
- This creates a *worse* recovery model than the current order

### Alternative Considered: Journal File

Write a `sync.intent` file before apply, delete it after config+lock are written. On startup, detect the intent file and replay. **Rejected** because:
- Adds new infrastructure (intent file format, replay logic, cleanup)
- The partial-install tolerance fix achieves the same result with ~10 lines of code
- Mars already has the idempotency property — we just need to stop blocking the re-sync

## F13: atomic_install_dir Gap

### Problem

In `src/fs/mod.rs`, `atomic_install_dir` does:

```rust
if dest.exists() {
    fs::remove_dir_all(dest)?;   // ← dest gone
}
// crash here = dest missing entirely
fs::rename(&tmp_path, dest)?;    // ← dest restored
```

If mars crashes between the remove and the rename, the installed skill directory is simply gone. The next `mars sync` would need to reinstall it.

### Design: Rename-Old-Then-Rename-New

```rust
pub fn atomic_install_dir(src: &Path, dest: &Path) -> Result<(), MarsError> {
    let parent = dest.parent().unwrap_or(Path::new("."));
    fs::create_dir_all(parent)?;

    let tmp_dir = tempfile::TempDir::new_in(parent)?;
    copy_dir_recursive(src, tmp_dir.path())?;
    let tmp_path = tmp_dir.keep();

    if dest.exists() {
        // Rename old to .old (atomic — old is still accessible)
        let old_path = parent.join(format!(
            ".{}.old",
            dest.file_name().unwrap_or_default().to_string_lossy()
        ));
        // Clean up stale .old from a prior crash
        if old_path.exists() {
            fs::remove_dir_all(&old_path)?;
        }
        fs::rename(dest, &old_path)?;
        // Rename new into place (atomic)
        if let Err(e) = fs::rename(&tmp_path, dest) {
            // Rollback: restore old
            let _ = fs::rename(&old_path, dest);
            let _ = fs::remove_dir_all(&tmp_path);
            return Err(e.into());
        }
        // Clean up old (non-critical — stale .old is harmless)
        let _ = fs::remove_dir_all(&old_path);
    } else {
        fs::rename(&tmp_path, dest)?;
    }

    Ok(())
}
```

**Crash analysis:**

| Crash point | State | Recovery |
|---|---|---|
| Before rename-to-old | `dest` intact, `tmp` exists | `tmp` is orphaned; cleaned on next install or by OS |
| After rename-to-old, before rename-new | `dest.old` exists, `dest` gone, `tmp` exists | `mars sync` detects missing dest, reinstalls. `.old` cleaned on next install of same dest. |
| After rename-new, before cleanup | `dest` new, `dest.old` stale | `.old` cleaned on next install |

**Note on the remaining gap:** A crash between rename-to-old and rename-new still leaves `dest` absent. This window is ~microseconds (two renames) compared to the old window of recursive-delete-then-rename. The `.old` sentinel makes the state diagnosable, and `mars sync` recovers by reinstalling. The design does NOT claim to eliminate the gap entirely — it shrinks it from a potentially long `remove_dir_all` to a single `rename` syscall.

## Files to Modify

- `src/sync/target.rs` — partial-install tolerance in `check_unmanaged_collisions`, ~10 lines
- `src/fs/mod.rs` — rewrite `atomic_install_dir` with rename-old pattern, ~25 lines

## Verification

- `cargo test` passes (including existing `atomic_install_dir` tests)
- Add test: verify `.old` cleanup when stale `.old` exists
- Add test: unmanaged collision skipped when disk content matches planned install
- `mars add` followed by kill during apply, then `mars sync` → recovers cleanly
