# Architecture: File Locking (R1, R2)

## R1: Cross-Platform FileLock

### Current Implementation
```rust
// src/fs/mod.rs — Unix-only
use std::os::unix::io::AsRawFd;
pub struct FileLock { _fd: fs::File }
impl FileLock {
    pub fn acquire(lock_path: &Path) -> Result<Self, MarsError> {
        let file = Self::open_lock_file(lock_path)?;
        let fd = file.as_raw_fd();
        unsafe { libc::flock(fd, libc::LOCK_EX) }; // Unix-only
        Ok(FileLock { _fd: file })
    }
}
```

### Target Implementation

Replace `libc::flock()` with `fd-lock` crate's `RwLock` guard-based API. The `fd-lock` crate provides:
- `RwLock::write()` → blocking exclusive lock (maps to `flock(LOCK_EX)` on Unix, `LockFileEx` on Windows)
- `RwLock::try_write()` → non-blocking try-acquire
- RAII unlock via guard Drop

**Changed file:** `src/fs/mod.rs`

```rust
// After: cross-platform via fs2
use fs2::FileExt;

pub struct FileLock { _fd: fs::File }

impl FileLock {
    pub fn acquire(lock_path: &Path) -> Result<Self, MarsError> {
        let file = Self::open_lock_file(lock_path)?;
        file.lock_exclusive()?;
        Ok(FileLock { _fd: file })
    }

    pub fn try_acquire(lock_path: &Path) -> Result<Option<Self>, MarsError> {
        let file = Self::open_lock_file(lock_path)?;
        match file.try_lock_exclusive() {
            Ok(()) => Ok(Some(FileLock { _fd: file })),
            Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => Ok(None),
            Err(e) => Err(e.into()),
        }
    }
    // open_lock_file unchanged — already cross-platform
}
// Lock released when File is dropped (fs2 releases on fd close)
```

**Dependency changes in `Cargo.toml`:**
- Add: `fs2 = "0.4"`
- Remove: `libc = "0.2.183"` (confirmed: only libc usages are the two flock calls in fs/mod.rs)

### Why fs2 over fd-lock

The feasibility probe evaluated three crates: `fs2`, `fd-lock`, and `file-lock`.

`fd-lock` (probe's initial recommendation) has a guard-based API (`RwLock::write()` returns `RwLockWriteGuard<'_, File>`) that borrows the `RwLock`. This creates a self-referential struct problem: `FileLock` would need to hold both the `RwLock` and the guard that borrows it. Workarounds exist (ouroboros, ManuallyDrop, Box + unsafe) but add complexity for no benefit.

`fs2` avoids this entirely: `lock_exclusive()` locks the file handle in place, and the lock is released when the `File` is dropped. This maps 1:1 to the existing `FileLock` pattern with zero structural change.

| Factor | fs2 | fd-lock |
|---|---|---|
| API fit | Perfect 1:1 mapping | Guard model requires restructuring |
| Downloads | 57M total | 41M total |
| Maintenance | 2018 (stable, no bugs) | 2025 (active) |
| Windows | LockFileEx, no elevation | LockFileEx, no elevation |
| Code change | 3 lines | 20+ lines + self-ref pattern |

**Decision:** Use `fs2`. The API fit is decisive — identical behavior with minimal code change.

### Removed Code
- `use std::os::unix::io::AsRawFd;`
- `unsafe { libc::flock(...) }` blocks
- All `libc`-related imports in `fs/mod.rs`

### Public API
Unchanged. `FileLock::acquire`, `FileLock::try_acquire`, `open_lock_file` retain their signatures.

---

## R2: Resolve Command Lock Acquisition

### Current Implementation
```rust
// src/cli/resolve_cmd.rs
pub fn run(args: &ResolveArgs, ctx: &super::MarsContext, json: bool) -> Result<i32, MarsError> {
    let mut lock = crate::lock::load(&ctx.project_root)?;
    // ... reads and writes lock without holding sync.lock ...
    crate::lock::write(&ctx.project_root, &lock)?;
}
```

### Target Implementation

Acquire the sync lock at the top of `run()`, matching the pattern in `sync/mod.rs::load_config()`.

```rust
pub fn run(args: &ResolveArgs, ctx: &super::MarsContext, json: bool) -> Result<i32, MarsError> {
    let mars_dir = ctx.project_root.join(".mars");
    let lock_path = mars_dir.join("sync.lock");
    let _sync_lock = crate::fs::FileLock::acquire(&lock_path)?;

    let mut lock = crate::lock::load(&ctx.project_root)?;
    // ... existing logic unchanged ...
}
```

**Changed file:** `src/cli/resolve_cmd.rs`

### has_conflict_markers Consolidation

While modifying `resolve_cmd.rs`, consolidate the three `has_conflict_markers` implementations:

1. **Keep:** `merge/mod.rs::has_conflict_markers(content: &[u8])` — correct line-start-aware implementation
2. **Replace:** `cli/resolve_cmd.rs::has_conflict_markers(path: &Path)` → read file, delegate to `merge::has_conflict_markers`
3. **Replace:** `cli/list.rs::has_conflict_markers(path: &Path)` → same delegation

Create a thin wrapper in a shared location (e.g., `merge/mod.rs` re-exported, or a new helper):
```rust
pub fn file_has_conflict_markers(path: &Path) -> bool {
    std::fs::read(path)
        .map(|content| crate::merge::has_conflict_markers(&content))
        .unwrap_or(false)
}
```
