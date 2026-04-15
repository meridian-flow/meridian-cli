# Phase 5: Git Cache Locking (F14)

## Scope

Add per-entry file locking for the git clone cache to prevent cross-repo races on the same cache entry.

## Files to Modify

### `src/source/git.rs` — `fetch_git_clone()`

Add flock acquisition at the top of the function, before any git operations:

```rust
fn fetch_git_clone(
    url: &str,
    tag: Option<&str>,
    sha: Option<&str>,
    cache: &GlobalCache,
) -> Result<PathBuf, MarsError> {
    let cache_path = cache.git_dir().join(url_to_dirname(url));

    // Acquire per-entry lock to prevent cross-repo races
    let lock_path = cache_path.with_extension("lock");
    let _lock = crate::fs::FileLock::acquire(&lock_path)?;

    let cache_path_display = cache_path.to_string_lossy().to_string();
    let was_cached = cache_path.exists();

    // ... rest of existing logic unchanged ...

    Ok(cache_path)
}
```

The lock is held for the duration of fetch + checkout, then released when `_lock` drops at function return.

**No changes needed for archive cache** — archive entries are content-addressed and the existing rename-race handling is sufficient.

## Dependencies

- Independent of all other phases
- Can run in parallel with any phase

## Interface Contract

`crate::fs::FileLock::acquire(path)` — blocks until lock acquired. Creates parent dirs. Lock released on drop. Already used by sync pipeline.

## Verification Criteria

- [ ] `cargo test` passes
- [ ] `cargo clippy --all-targets --all-features` clean
- [ ] Lock file created at `{cache_dir}/git/{url_dirname}.lock` during git fetch
- [ ] Lock file doesn't interfere with normal single-process operation
