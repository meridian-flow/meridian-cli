# F14: Global Cache Locking

## Problem

The global cache at `~/.mars/cache/` is shared across all mars invocations on the machine. Two `mars sync` processes in different repos can race on the same cache entry:

- **Archive cache** (`~/.mars/cache/archives/{url}_{sha}`): Two processes fetching the same URL+SHA simultaneously. Both download, both try to rename into the same cache slot.
- **Git clone cache** (`~/.mars/cache/git/{url_dirname}`): Two processes updating the same clone. One runs `git fetch`, the other runs `git checkout` — corrupted working tree.

### Current Mitigations

The archive path already handles the rename race:

```rust
match fs::rename(&temp_path, &cache_path) {
    Ok(()) => Ok(cache_path),
    Err(err) => {
        if cache_path.exists() {
            // Another process won the race
            let _ = fs::remove_dir_all(&temp_path);
            Ok(cache_path)
        } else {
            Err(err.into())
        }
    }
}
```

This works because archive entries are content-addressed (`{url}_{sha}`) — once created, they're immutable. The race is benign: both processes produce identical content, one wins the rename, the other detects it and uses the winner's result.

### What Needs Fixing: Git Clone Cache

Git clone entries are **not** content-addressed — they're mutable working trees (`{url_dirname}`) that get fetched and checked out. Two processes can interleave:

```
Process A: git fetch origin          Process B: git fetch origin
Process A: git checkout v1.0.0      Process B: git checkout v2.0.0
```

Process A thinks it's on v1.0.0 but B's checkout moved it to v2.0.0.

### Design: Per-Entry Flock for Git Clone Cache

Add a file lock per git clone cache entry, acquired before any git operations and held through checkout:

```rust
fn fetch_git_clone(
    url: &str,
    tag: Option<&str>,
    sha: Option<&str>,
    cache: &GlobalCache,
) -> Result<PathBuf, MarsError> {
    let cache_path = cache.git_dir().join(url_to_dirname(url));

    // Acquire per-entry lock
    let lock_path = cache_path.with_extension("lock");
    let _lock = crate::fs::FileLock::acquire(&lock_path)?;

    // ... existing fetch + checkout logic under lock ...

    Ok(cache_path)
}
```

**Why flock over content-addressed immutable entries for git:**

- Content-addressed git entries would require copying the entire repo per commit SHA, which is expensive for large repos
- Flock is the same mechanism already used for `sync.lock` — consistent, well-tested
- The lock is per-entry (not global), so different URLs can be fetched concurrently
- Lock granularity matches the contention unit (one URL = one working tree)

**Alternative considered: convert git cache to content-addressed.**

Each checkout would go to `{url_dirname}_{sha}/`. This wastes disk (full repo copy per version) and breaks the shallow clone optimization (can't incrementally fetch into an existing clone). Flock is cheaper and simpler.

### Archive Cache: No Change Needed

Archive entries are already content-addressed and immutable. The existing rename-race handling is correct. The temp path includes `std::process::id()` which prevents temp collisions between processes. No additional locking needed.

## Files to Modify

- `src/source/git.rs` — add flock in `fetch_git_clone()`, ~5 lines
- Ensure `crate::fs::FileLock` parent-dir creation handles `~/.mars/cache/git/` (already does — `open_lock_file` creates parents)

## Verification

- `cargo test` passes
- Manual: run two `mars sync` in different repos that share a git source — both succeed without corruption
- The lock file appears at `~/.mars/cache/git/{url_dirname}.lock`
