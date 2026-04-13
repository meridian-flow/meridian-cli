# Decision Log

## D1: fs2 over fd-lock for cross-platform locking

**Decision:** Use `fs2` crate (not `fd-lock`) to replace `libc::flock()`.

**Reasoning:** Both crates provide cross-platform advisory file locking. `fd-lock` has a guard-based API (`RwLock::write()` returns `RwLockWriteGuard<'_, File>`) that creates a self-referential struct problem when trying to store both the lock and the guard in `FileLock`. `fs2` uses `FileExt` trait methods (`lock_exclusive()`, `try_lock_exclusive()`) that lock the file handle in place — the lock releases when the `File` is dropped. This maps 1:1 to the existing `FileLock { _fd: File }` pattern with 3 lines changed.

**Alternatives rejected:**
- `fd-lock`: Guard lifetime requires self-referential struct (ouroboros or unsafe). More code, more complexity, no benefit.
- `file-lock`: POSIX/fcntl-focused, questionable Windows support, heavier build deps.
- Hand-rolled `LockFileEx`: Unnecessary when `fs2` wraps it correctly.

**Risk:** `fs2` last released 2018. Mitigated by: stable API, 57M downloads, `flock`/`LockFileEx` are OS primitives that don't change. Fallback: inline the ~50 lines of platform code from `fs2` if the crate becomes unmaintained.

## D2: Copy everywhere, no symlinks

**Decision:** Remove `Materialization::Symlink` and all symlink creation code. Local package items use copy like dependencies.

**Reasoning:** Windows symlinks require developer mode or elevation — unacceptable for a package manager. The tradeoff (edits require `mars sync` to propagate) is acceptable for `_self` dev-edit workflows.

**Alternatives rejected:**
- Windows junction points: Only work for directories, not files. Still creates cross-platform behavioral differences.
- Conditional symlink/copy: Doubles the code paths and testing surface for a dying use case.

## D3: Skill conflicts overwrite, not merge

**Decision:** When both source and local change a skill directory, source wins (overwrite). User's local modifications are lost.

**Reasoning:** Skills are directories. Three-way merge operates on byte streams and cannot merge directory trees. The merge path in `apply.rs` reads `SKILL.md` only, writes the merged bytes to the dest path, and overwrites the directory with a file — silently losing resources. Overwrite is the only correct simple option.

**Alternatives rejected:**
- Per-file merge within skill directory: High complexity, low value with no real users.
- Reject and require user intervention: Adds friction for a case that should be rare (local skill edits + upstream changes).

**Risk:** Overwrites user-added resource files without backup. Acceptable given no real users. Warning message explicitly states "directory contents will be replaced."

## D4: Lock advances even when target sync fails

**Decision:** The lock file records `.mars/` state, not target state. If target sync fails, the lock still advances. Target divergence is healed on the next sync.

**Reasoning:** Blocking lock advancement would force a wasteful re-fetch from source on the next sync. The `.mars/` canonical store has correct content — only the target copy failed. Self-healing via target divergence detection (comparing target hash to lock's `installed_checksum`) catches both permission failures and manual edits.

**Alternatives rejected:**
- Don't advance lock on target failure: Causes unnecessary source re-fetch, doesn't help the target problem.
- Track per-target lock state: Over-engineering for the current design.

## D5: Warning plumbing via DiagnosticCollector, not SyncPlan.warnings

**Decision:** Thread `DiagnosticCollector` into `plan::create()` and emit warnings directly, rather than adding a `warnings` field to `SyncPlan`.

**Reasoning:** `SyncPlan` is a data structure for actions, not diagnostics. Adding warnings creates a second diagnostic channel parallel to `DiagnosticCollector`. The planner phase already receives `diag` in the pipeline — threading it one level deeper is minimal change.

## D6: Remove is_symlink from InstalledItem, update doctor

**Decision:** Remove `InstalledItem.is_symlink` entirely. Update `cli/doctor.rs` to detect symlinks on-the-fly via `symlink_metadata()` and report them as anomalies rather than silently skipping them.

**Reasoning:** After R3, no installed items should be symlinks. Legacy symlinks from pre-R3 installs are anomalous and should be reported, not hidden.
