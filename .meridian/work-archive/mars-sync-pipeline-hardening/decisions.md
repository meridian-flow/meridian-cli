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

## D7: Planning follows the locking architecture, not the stale crate recommendation

**Decision:** Treat `design/architecture/locking.md` as authoritative for R1. Implement hand-rolled `#[cfg(unix)]` and `#[cfg(windows)]` platform helpers in `src/fs/mod.rs`, keep `libc` as the Unix-only locking dependency, and add `windows-sys` as the Windows-only dependency.

**Reasoning:** The feasibility probe compared crates, but the architecture doc and pre-planning re-check already resolved the tradeoff in favor of inline platform modules. That decision keeps the public `FileLock` API unchanged, avoids the self-referential-guard problem from `fd-lock`, and matches the runtime note that `libc` is still needed for Unix `flock`. The symlink-removal architecture note claiming `Cargo.toml` can drop `libc` was written against the earlier `fs2` direction and is stale once hand-rolled locking is chosen.

**Alternatives rejected:**
- Follow D1 / `fs2`: superseded by the later architecture package and pre-planning review.
- Remove `libc` from `Cargo.toml`: incorrect for the chosen Unix locking implementation.

## D7: Hand-roll locking, not fs2 (overrides D1)

**Decision:** Follow architecture doc (hand-roll with platform modules), not D1 (fs2).

**Reasoning:** D1 was written during early feasibility. Architecture doc revised to hand-roll after deeper analysis: underlying syscalls are ~30 lines, all three crates are thin wrappers, fs2 unchanged since 2018. libc stays for Unix, windows-sys added for Windows.

**What changed:** D1 recommended fs2. Architecture doc overrides with hand-rolled implementation. D1's fallback ("inline the ~50 lines from fs2") is essentially what we're doing from the start.

## D8: Keep libc in Cargo.toml (contradicts symlink-removal architecture note)

**Decision:** Keep libc as Unix-only dependency. The symlink-removal architecture doc's note to "Remove libc" was wrong — it assumed fs2 would replace all libc usage.

**Reasoning:** Hand-rolled locking on Unix uses libc::flock. libc is the only dependency for this. Removing it would break Unix locking.

## D9: Windows cross-check blocked by ring/MSVC environment

**Decision:** Accept that `cargo check --target x86_64-pc-windows-msvc` cannot fully run on this Linux dev environment because `ring` (transitive dep via `ureq`) requires `lib.exe` from MSVC toolchain for its C build step.

**Evidence:** No Rust compilation errors. The build fails in ring's cc-rs build script, not in mars-agents code. Our `#[cfg(windows)]` code is syntactically/semantically correct (verified by independent compilation of the platform module in isolation).

**Mitigation:** All `#[cfg(windows)]` code follows the architecture doc exactly. The platform module pattern ensures Windows code is only compiled on Windows targets. Full Windows CI would be needed for runtime verification.

## D10: Review findings triage (final review loop)

**CKSUM-08 recovery path (p1656):** NOT a bug. CKSUM-09 spec explicitly says divergent targets warn and preserve. Only *missing* targets self-heal. The reviewer misread the spec's "self-healing" as applying to all divergence — it only applies to missing targets.

**PERM-02 in .mars/ atomic writes (p1656, p1658):** DEFERRED. The Windows read-only handling in atomic_write_file and atomic_install_dir is a defensive concern. No Windows CI to validate, and the current code is already correct for Unix. Adding clear_readonly calls in atomic operations without testing risks introducing bugs on a platform we can't verify. Will address when Windows CI is available.

**Legacy symlink normalization (p1658):** DEFERRED. Legacy symlinks from pre-migration installs should ideally be normalized by sync, but this is an edge case affecting zero current users (no users yet). doctor already reports them. Adding normalization logic complicates the diff phase for a case that won't occur in practice.

**Duplicate checksum validation (p1657):** ACCEPTED, will fix. Triple validation in lock building is redundant — the upfront validation loop can be the single point, and downstream code can unwrap safely.

**LOCK-06 interpretation (p1656):** The spec says "no Unix-only dependencies in lock path." The implementation gated them behind #[cfg(unix)] — they exist in the codebase but are not in the *shared* lock path. The shared path calls `platform::lock_exclusive()` which is platform-neutral. LOCK-06 is satisfied per intent.
