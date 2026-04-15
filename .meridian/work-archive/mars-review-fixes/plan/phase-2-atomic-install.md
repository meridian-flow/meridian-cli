# Phase 2: Atomic Install Dir Fix (F13)

## Scope

Rewrite `atomic_install_dir` in `src/fs/mod.rs` to use the rename-old-then-rename-new pattern, eliminating the gap where the destination doesn't exist.

## Files to Modify

### `src/fs/mod.rs` — `atomic_install_dir()`

Replace the current implementation:

```rust
pub fn atomic_install_dir(src: &Path, dest: &Path) -> Result<(), MarsError> {
    let parent = dest.parent().unwrap_or(Path::new("."));
    fs::create_dir_all(parent)?;

    let tmp_dir = tempfile::TempDir::new_in(parent)?;
    copy_dir_recursive(src, tmp_dir.path())?;
    let tmp_path = tmp_dir.keep();

    if dest.exists() {
        // Step 1: Rename old to .old (old content still accessible)
        let old_path = parent.join(format!(
            ".{}.old",
            dest.file_name().unwrap_or_default().to_string_lossy()
        ));
        // Clean up stale .old from a prior crash
        if old_path.exists() {
            fs::remove_dir_all(&old_path)?;
        }
        // Atomic: old content moves to .old, dest slot is free
        fs::rename(dest, &old_path)?;
        // Atomic: new content takes dest slot
        if let Err(e) = fs::rename(&tmp_path, dest) {
            // Rollback: move old content back
            let _ = fs::rename(&old_path, dest);
            let _ = fs::remove_dir_all(&tmp_path);
            return Err(e.into());
        }
        // Cleanup: remove old content (non-critical)
        let _ = fs::remove_dir_all(&old_path);
    } else {
        fs::rename(&tmp_path, dest)?;
    }

    Ok(())
}
```

**Key differences from current:**
- No `remove_dir_all(dest)` — replaced with `rename(dest, old_path)`
- Rollback on rename failure
- Stale `.old` cleanup at the start handles prior crashes
- `.old` naming uses a hidden prefix to avoid polluting the directory listing

## Dependencies

None — independent of other phases.

## Patterns to Follow

Look at the existing `atomic_write` function in the same file for the temp-file-then-rename pattern. The new code extends this to directories with the old-rename safety net.

## Verification Criteria

- [ ] `cargo test` passes (existing `atomic_install_dir_*` tests)
- [ ] `cargo clippy --all-targets --all-features` clean
- [ ] Add test: `atomic_install_dir` with pre-existing `.old` stale dir gets cleaned up
- [ ] Add test: dest is never absent between old removal and new placement (verify by checking dest exists before and after in a single-threaded test)
