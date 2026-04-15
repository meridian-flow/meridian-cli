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

Hand-roll cross-platform locking with `#[cfg]` blocks. The syscalls are trivial (~30 lines total) and don't justify an external dependency. Keep `libc` for Unix (already a dependency), add `windows-sys` for Windows (Microsoft's official Rust bindings).

**Changed file:** `src/fs/mod.rs`

```rust
pub struct FileLock { _fd: fs::File }

impl FileLock {
    pub fn acquire(lock_path: &Path) -> Result<Self, MarsError> {
        let file = Self::open_lock_file(lock_path)?;
        platform::lock_exclusive(&file)?;
        Ok(FileLock { _fd: file })
    }

    pub fn try_acquire(lock_path: &Path) -> Result<Option<Self>, MarsError> {
        let file = Self::open_lock_file(lock_path)?;
        match platform::try_lock_exclusive(&file) {
            Ok(true) => Ok(Some(FileLock { _fd: file })),
            Ok(false) => Ok(None),
            Err(e) => Err(e.into()),
        }
    }
    // open_lock_file unchanged — already cross-platform
}
// Lock released when File is dropped (OS releases advisory lock on fd close)

#[cfg(unix)]
mod platform {
    use std::os::unix::io::AsRawFd;
    
    pub fn lock_exclusive(file: &std::fs::File) -> std::io::Result<()> {
        let ret = unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX) };
        if ret != 0 { Err(std::io::Error::last_os_error()) } else { Ok(()) }
    }
    
    pub fn try_lock_exclusive(file: &std::fs::File) -> std::io::Result<bool> {
        let ret = unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) };
        if ret != 0 {
            let err = std::io::Error::last_os_error();
            if err.kind() == std::io::ErrorKind::WouldBlock { Ok(false) }
            else { Err(err) }
        } else { Ok(true) }
    }
}

#[cfg(windows)]
mod platform {
    use std::os::windows::io::AsRawHandle;
    use windows_sys::Win32::Foundation::HANDLE;
    use windows_sys::Win32::Storage::FileSystem::{
        LockFileEx, LOCKFILE_EXCLUSIVE_LOCK, LOCKFILE_FAIL_IMMEDIATELY,
    };
    
    pub fn lock_exclusive(file: &std::fs::File) -> std::io::Result<()> {
        let handle = file.as_raw_handle() as HANDLE;
        let mut overlapped = unsafe { std::mem::zeroed() };
        let ret = unsafe { LockFileEx(handle, LOCKFILE_EXCLUSIVE_LOCK, 0, !0, !0, &mut overlapped) };
        if ret == 0 { Err(std::io::Error::last_os_error()) } else { Ok(()) }
    }
    
    pub fn try_lock_exclusive(file: &std::fs::File) -> std::io::Result<bool> {
        let handle = file.as_raw_handle() as HANDLE;
        let mut overlapped = unsafe { std::mem::zeroed() };
        let ret = unsafe {
            LockFileEx(handle, LOCKFILE_EXCLUSIVE_LOCK | LOCKFILE_FAIL_IMMEDIATELY, 0, !0, !0, &mut overlapped)
        };
        if ret == 0 {
            let err = std::io::Error::last_os_error();
            if err.raw_os_error() == Some(33) /* ERROR_LOCK_VIOLATION */ { Ok(false) }
            else { Err(err) }
        } else { Ok(true) }
    }
}
```

**Dependency changes in `Cargo.toml`:**
- Keep: `libc` (Unix, already present)
- Add: `windows-sys = { version = "0.59", features = ["Win32_Storage_FileSystem", "Win32_Foundation"] }` (Windows only, via `[target.'cfg(windows)'.dependencies]`)
- No external locking crate needed — the syscalls are ~30 lines total

### Why hand-rolled over fs2/fd-lock

The feasibility probe evaluated `fs2`, `fd-lock`, and `file-lock`. All three are thin wrappers around the same two syscalls (`flock` on Unix, `LockFileEx` on Windows). The underlying code is trivial — no reason to take an external dependency for ~30 lines of platform FFI that won't change.

- `fs2`: last updated 2018, wraps exactly these calls
- `fd-lock`: guard-based API creates self-referential struct problem
- `file-lock`: POSIX-focused, poor Windows support

**Decision:** Hand-roll. Keep `libc` (already a dependency), add `windows-sys` (Microsoft's official crate, already standard in the Rust ecosystem for Windows API access).

### Removed Code
- Top-level `use std::os::unix::io::AsRawFd` (moved into `#[cfg(unix)]` platform module)
- Inline `unsafe { libc::flock(...) }` blocks (replaced by platform module calls)

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
