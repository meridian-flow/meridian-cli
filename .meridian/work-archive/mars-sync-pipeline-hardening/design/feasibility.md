# Cross-Platform File Lock Crate Feasibility (mars-agents)

## Probe Summary

- `cargo add --dry-run` in `/home/jimyao/gitrepos/mars-agents` succeeded for all:
  - `fs2 v0.4.3`
  - `fd-lock v4.0.4`
  - `file-lock v2.1.11`
- Current codebase `libc::` usage search:
  - `src/fs/mod.rs:165`
  - `src/fs/mod.rs:180`
  - No other `libc::` call sites found.

## Comparison

| Crate | crates.io latest | crates.io updated_at | Downloads / recent | Maintenance signal | Blocking exclusive | Non-blocking exclusive | RAII release | Windows support (no elevation) | Dependency weight |
|---|---:|---|---:|---|---|---|---|---|---|
| `fs2` | `0.4.3` | `2018-01-06` | `56,942,474 / 8,817,758` | Old release, stable adoption | `FileExt::lock_exclusive()` | `FileExt::try_lock_exclusive()` (`WouldBlock` via contended lock error) | Yes (lock released when file handle dropped; tested in crate) | Yes (`LockFileEx`/`UnlockFile` backend on Windows) | Light: Linux tree `fs2 -> libc`; Windows tree `fs2 -> winapi` |
| `file-lock` | `2.1.11` | `2024-02-17` | `4,789,180 / 938,235` | Active-ish | `FileLock::lock(..., is_blocking=true, ...)` | `FileLock::lock(..., is_blocking=false, ...)` | Yes (`Drop` calls unlock) | **No (POSIX/fcntl-focused API + C shim)** | Medium: `file-lock -> libc`; build deps include `cc`, `find-msvc-tools`, `shlex` |
| `fd-lock` | `4.0.4` | `2025-03-10` | `40,693,883 / 7,998,350` | Most recently maintained | `RwLock::write()` | `RwLock::try_write()` (`ErrorKind::WouldBlock`) | Yes (read/write guards unlock on drop) | Yes (Windows backend uses `LockFileEx`; standard user-mode file API) | Medium-light: Linux `cfg-if + rustix (+ bitflags/linux-raw-sys)`; Windows `cfg-if + windows-sys/windows-targets` |

## Recommendation

**Hand-roll with `#[cfg]` platform modules.** Keep `libc` (Unix, already a dep), add `windows-sys` (Windows, Microsoft's official crate).

Reasoning:

- The underlying syscalls are ~30 lines total (`flock` on Unix, `LockFileEx` on Windows).
- All three evaluated crates are thin wrappers around exactly these calls — no value added.
- `fs2` hasn't been updated since 2018. `fd-lock`'s guard API creates a self-referential struct problem. `file-lock` has poor Windows support.
- `windows-sys` is the standard Rust crate for Windows API access, already ubiquitous in the ecosystem.
- Inlining the code keeps it auditable and avoids a transitive dependency chain for trivial functionality.

Implementation mapping for current `FileLock` API:

- Keep `open_lock_file()` exactly as-is (already creates parent dirs + opens lock file).
- Wrap `std::fs::File` with `fd_lock::RwLock<File>`.
- `acquire` => `lock.write()?` (blocking).
- `try_acquire` => `lock.try_write()` and map `WouldBlock` to `Ok(None)`.
- Store the write guard inside `FileLock` so unlock is automatic on `Drop`.

## Can `libc` Be Removed From `Cargo.toml`?

**Yes, if migrating to `fd-lock` (or `fs2`).**

- In current codebase, direct `libc::` usage is only the two `flock` calls in `src/fs/mod.rs`.
- No other source files use `libc::...`.
- After replacing those calls, `libc` is no longer needed as a direct dependency of `mars-agents`.

## Risks / Gotchas

- `fd-lock` API shape is guard-based (`RwLock`), so `FileLock` internals need a small structural change (store lock + guard, not just `File`).
- Ensure lock-file lifetime keeps guard alive for full critical section (existing pattern already uses scoped lock guard vars).
- Keep `WouldBlock` mapping behavior identical in `try_acquire`.
- `file-lock` appears POSIX-oriented and not a good fit for Windows portability despite recent updates.

