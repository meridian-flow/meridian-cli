# Phase 1: Cross-Platform Locking Foundation

## Round

Round 1, parallel with Phase 2.

## Scope and Boundaries

Implement R1 and REF-03 in `src/fs/mod.rs` and `Cargo.toml`. Keep the public `FileLock` API shape intact while moving platform details behind `#[cfg(unix)]` and `#[cfg(windows)]` helpers. This phase does not change `mars resolve`; that consumer work belongs to Phase 3.

## Touched Files and Modules

- `/home/jimyao/gitrepos/mars-agents/Cargo.toml`
- `/home/jimyao/gitrepos/mars-agents/src/fs/mod.rs`

## Claimed EARS Statement IDs

- `LOCK-01`
- `LOCK-02`
- `LOCK-03`
- `LOCK-04`
- `LOCK-05`
- `LOCK-06`

## Touched Refactor IDs

- `REF-03`

## Dependencies

- None.
- Must remain disjoint from Phase 2's sync-pipeline refactor.

## Tester Lanes

- `@verifier`: verify the `FileLock` API still blocks, try-locks, and releases by drop; confirm top-level Unix-only imports are gone.
- `@unit-tester`: add or update focused tests for contention, parent-directory creation, and `try_acquire` returning `Ok(None)` on contention.
- `@smoke-tester`: run `cargo build`, `cargo test`, `cargo clippy`, and `cargo check --target x86_64-pc-windows-msvc` from `/home/jimyao/gitrepos/mars-agents/`.

## Edge Cases and Constraints

- Keep `libc` as the Unix-only dependency for `flock`; do not follow the stale note that removes it.
- Add `windows-sys` only under `[target.'cfg(windows)'.dependencies]`.
- Map the Windows lock-contention case to `Ok(None)` in `try_acquire`.
- Preserve parent-directory creation in `open_lock_file()`.

## Exit Criteria

- `FileLock::acquire` and `FileLock::try_acquire` satisfy `LOCK-01` through `LOCK-05`.
- No top-level `libc::flock`, `AsRawFd`, or other Unix-only API remains exposed in the shared lock path.
- `cargo build`, `cargo test`, `cargo clippy`, and `cargo check --target x86_64-pc-windows-msvc` pass from `/home/jimyao/gitrepos/mars-agents/`.
