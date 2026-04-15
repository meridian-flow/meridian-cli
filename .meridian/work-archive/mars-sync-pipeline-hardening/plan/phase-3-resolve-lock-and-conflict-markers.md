# Phase 3: Resolve Lock and Conflict-Marker Cleanup

## Round

Round 2, after Phase 1.

## Scope and Boundaries

Implement R2 and REF-02 in the CLI layer. `mars resolve` must acquire `sync.lock` before reading or writing `mars.lock`, and the duplicate `has_conflict_markers` helpers must collapse onto the canonical merge implementation. This phase does not change the sync planner's skill-conflict policy; that belongs to Phase 4.

## Touched Files and Modules

- `/home/jimyao/gitrepos/mars-agents/src/cli/resolve_cmd.rs`
- `/home/jimyao/gitrepos/mars-agents/src/cli/list.rs`
- `/home/jimyao/gitrepos/mars-agents/src/merge/mod.rs`

## Claimed EARS Statement IDs

- `LOCK-07`
- `LOCK-08`
- `LOCK-09`

## Touched Refactor IDs

- `REF-02`

## Dependencies

- Phase 1, because this phase consumes the settled `FileLock` implementation.

## Tester Lanes

- `@verifier`: confirm `resolve` acquires `sync.lock` before any `mars.lock` read/write and holds it through completion.
- `@smoke-tester`: run `cargo build`, `cargo test`, `cargo clippy`, and `cargo check --target x86_64-pc-windows-msvc` from `/home/jimyao/gitrepos/mars-agents/`; exercise concurrent `mars resolve` plus `mars sync`.

## Edge Cases and Constraints

- The lock must cover both lock-file reads and writes, not only the write path.
- `cli/resolve_cmd.rs` and `cli/list.rs` must delegate to the same conflict-marker logic as `merge/mod.rs`; no third implementation remains.
- Keep CLI-visible behavior unchanged except for the added synchronization safety.

## Exit Criteria

- `mars resolve` serializes access to `mars.lock` with the sync advisory lock.
- Concurrent `resolve` and `sync` no longer risk concurrent lock-file mutation.
- The duplicate `has_conflict_markers` logic is consolidated.
- `cargo build`, `cargo test`, `cargo clippy`, and `cargo check --target x86_64-pc-windows-msvc` pass from `/home/jimyao/gitrepos/mars-agents/`.
