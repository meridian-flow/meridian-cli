# Mars Sync Pipeline Hardening + Windows Support

## Background

Mars is a package manager for `.agents/` directories (agent profiles and skills as markdown+YAML). Rust codebase at `/home/jimyao/gitrepos/mars-agents/`. Currently v0.0.14, no real users yet — breaking changes are fine.

A comprehensive audit (8 parallel spawns: 5 smoke testers, 2 code reviewers, 1 coder) surfaced structural issues in the sync pipeline that overlap with the work needed for Windows support. This work item addresses them together because the fixes share code paths and designing them separately risks contradictory decisions.

## Evidence Sources

All findings come from spawns under parent p1621 (session c1538):

- **p1629** (gpt-5.4 structural review): skill merge bug, checksum decay, `models alias` bypass
- **p1630** (opus consistency review): `resolve` missing lock, `models alias` bypass, `has_conflict_markers` duplication
- **p1624** (smoke: root config): local package items are regular files not symlinks — now intentional (Windows compat)
- **p1625** (smoke: sync edge cases): read-only `.agents/` causes permanent drift, manual edits silently overwritten
- **p1627** (smoke: check/doctor/repair): doctor misses orphaned files

## Requirements

### R1: Cross-platform file locking

**Current state:** `FileLock` in `src/fs/mod.rs` uses `libc::flock()` with `AsRawFd` — Unix-only. Used by sync, link, git cache, and models cache.

**Required:** Replace with a cross-platform advisory lock that works on Windows (e.g. `fs2` crate's `FileExt::lock_exclusive()`, or `file-lock`, or hand-rolled `LockFileEx`). The lock must:
- Block until acquired (existing `acquire` semantic)
- Support try-acquire with immediate failure (existing `try_acquire` semantic)
- Release on drop (existing RAII semantic)
- Create parent directories if missing (existing behavior)
- Work on Windows without elevated privileges

### R2: Resolve command lock acquisition

**Current state:** `mars resolve` (`src/cli/resolve_cmd.rs`) reads and writes the lock file without acquiring `sync.lock`. Concurrent `mars resolve` + `mars sync` can corrupt the lock file. Every other lock-mutating command (sync, link) acquires the lock.

**Required:** `mars resolve` must acquire the sync advisory lock before reading/writing `mars.lock`, matching the pattern in `sync` and `link`.

### R3: Eliminate symlinks from sync pipeline

**Current state:** Local package items (`_self` source) are symlinked into `.mars/` via `atomic_symlink()` in `src/reconcile/fs_ops.rs`. The target sync layer then copies from `.mars/` → `.agents/` following symlinks. `atomic_symlink()` already has a `#[cfg(not(unix))]` branch that returns an error.

**Required:** Replace symlink materialization with copy for `_self` items. The `PlannedAction::Symlink` variant and `atomic_symlink()` function should be removed entirely. Local package items get copied like any other source. This means:
- Edits to source agents/skills require `mars sync` to propagate (acceptable tradeoff for Windows compat)
- The sync planner no longer needs a symlink-vs-copy branch for `_self` sources
- `target_sync` no longer needs symlink-following logic (it already copies, but has special handling)
- Test code using `std::os::unix::fs::symlink` in non-test paths must be eliminated

**Decision:** We explicitly chose copies over symlinks for Windows compatibility. Symlinks on Windows require developer mode or elevated privileges — unacceptable friction for a package manager. The `_self` dev-edit loop trades instant propagation for a `mars sync` step, which is acceptable.

### R4: Skill directory merge path

**Current state:** `sync/plan.rs` plans `PlannedAction::Merge` for any copy-materialized conflict without checking `ItemKind`. `sync/apply.rs` executes merge by writing merged bytes to the dest path, but for skills (which are directories containing `SKILL.md` + optional `resources/`), this path either fails or loses directory-level changes.

**Required:** The sync planner must branch on `ItemKind::Skill` when planning conflict resolution. Skills are directories, not single files — they cannot use the same merge strategy as agents (single `.md` files). Options include:
- Force-overwrite skill directories on conflict (simpler, acceptable given no real users)
- Directory-aware merge that handles `SKILL.md` + resources separately
- Reject skill conflicts and require user intervention

The design should pick the simplest option that doesn't lose data silently.

### R5: Checksum validation discipline

**Current state:** Checksums are optional on `ActionOutcome` (`sync/apply.rs`). Symlink hash failures are swallowed with `unwrap_or_default()`. Missing checksums are persisted as empty strings in the lock file. The lock is trusted as ground truth without disk verification.

**Required:**
- Checksums must be mandatory for all write-producing actions (copy, merge). Lock building must error if a required checksum is absent.
- After writing a file/directory, verify the written content matches the expected checksum before recording success.
- On sync, detect when disk state diverges from lock state (covers both the read-only `.agents/` drift bug and manual edit detection).
- When divergence is detected, warn the user and re-sync rather than silently trusting stale lock state.

### R6: Unix permission handling

**Current state:** `PermissionsExt` usage in `fs_ops.rs:178` and `fs/mod.rs:35` is already behind `#[cfg(unix)]`. Windows path does nothing (default perms).

**Required:** Verify this is sufficient. No new work expected, but the design should confirm the Windows permission model doesn't cause failures (e.g. read-only files that can't be overwritten during sync).

## Constraints

- All changes are in the `mars-agents` Rust repo at `/home/jimyao/gitrepos/mars-agents/`
- Breaking changes are fine — no real users yet
- Must pass `cargo test`, `cargo fmt`, `cargo clippy` on the current (Unix) platform
- Windows CI is not required in this work item, but the code must compile on Windows (no `#[cfg(unix)]`-only paths in non-test code without a Windows fallback)
- The `mars models alias` config bypass (both reviewers flagged) is explicitly OUT of scope — it's a trivial standalone fix
- UX polish (exit codes, error messages, `--dry-run` naming, doctor orphan detection) is OUT of scope

## Success Criteria

1. `FileLock` compiles and works on both Unix and Windows without elevated privileges
2. `mars resolve` acquires the sync lock before mutating `mars.lock`
3. No symlink creation in any non-test code path; `PlannedAction::Symlink` variant removed
4. Skill directory conflicts are handled explicitly (not silently broken)
5. Checksums are mandatory for write actions; divergent disk state is detected and re-synced
6. `cargo test` passes on Unix; `cargo check --target x86_64-pc-windows-msvc` compiles clean (cross-check, not full test)
