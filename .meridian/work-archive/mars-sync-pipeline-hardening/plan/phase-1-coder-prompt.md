# Phase 1: Cross-Platform Locking Foundation

## Task

Implement cross-platform file locking in /home/jimyao/gitrepos/mars-agents/. Replace the Unix-only `libc::flock` implementation with platform-specific modules behind `#[cfg]` blocks.

## What to Do

### 1. Update Cargo.toml

Add windows-sys as a Windows-only dependency:

```toml
[target.'cfg(windows)'.dependencies]
windows-sys = { version = "0.59", features = ["Win32_Storage_FileSystem", "Win32_Foundation"] }
```

Keep `libc = "0.2.183"` — it's still used for Unix flock.

### 2. Refactor src/fs/mod.rs

Current state: `FileLock::acquire` and `FileLock::try_acquire` directly call `libc::flock` with `AsRawFd`. Move platform code into `#[cfg]` modules.

Target structure:

```rust
// Remove top-level:
// use std::os::unix::io::AsRawFd;
// (keep other imports)

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
    // open_lock_file() stays unchanged
}

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

### 3. Handle existing #[cfg(unix)] permission code

The file already has `#[cfg(unix)]` blocks for PermissionsExt. Keep those as-is. Just move the locking-specific Unix APIs into the platform module.

## Verification

Run from /home/jimyao/gitrepos/mars-agents/:
```bash
cargo build
cargo test
cargo clippy
cargo check --target x86_64-pc-windows-msvc
```

All must pass.

## EARS Claims

This phase satisfies: LOCK-01 through LOCK-06.

## Key Constraints

- Public API unchanged: `FileLock::acquire`, `FileLock::try_acquire`, `open_lock_file`
- `try_acquire` must return `Ok(None)` on contention (WouldBlock on Unix, ERROR_LOCK_VIOLATION=33 on Windows)
- Lock released when File dropped (OS behavior, no explicit unlock needed)
- Parent directory creation in `open_lock_file` stays unchanged
- Do NOT touch any sync pipeline files — Phase 2 owns those
