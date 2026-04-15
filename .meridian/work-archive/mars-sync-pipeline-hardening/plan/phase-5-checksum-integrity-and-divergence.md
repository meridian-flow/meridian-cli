# Phase 5: Checksum Integrity and Target Divergence

## Round

Round 3, after Phases 1, 2, and 4.

## Scope and Boundaries

Implement R5 and R6 in the post-refactor pipeline. Enforce mandatory checksums for write-producing actions, verify writes before recording success, carry expected checksums into skipped outcomes, detect target divergence without clobbering local edits, and add defensive Windows read-only handling where overwrite paths need it. This phase does not reopen the symlink-removal refactor or the resolve-command CLI lane.

## Touched Files and Modules

- `/home/jimyao/gitrepos/mars-agents/src/sync/apply.rs`
- `/home/jimyao/gitrepos/mars-agents/src/sync/mod.rs`
- `/home/jimyao/gitrepos/mars-agents/src/sync/diff.rs`
- `/home/jimyao/gitrepos/mars-agents/src/lock/mod.rs`
- `/home/jimyao/gitrepos/mars-agents/src/target_sync/mod.rs`
- `/home/jimyao/gitrepos/mars-agents/src/fs/mod.rs`

## Claimed EARS Statement IDs

- `CKSUM-01`
- `CKSUM-02`
- `CKSUM-03`
- `CKSUM-04`
- `CKSUM-05`
- `CKSUM-06`
- `CKSUM-07`
- `CKSUM-08`
- `CKSUM-09`
- `PERM-01`
- `PERM-02`

## Touched Refactor IDs

- None.

## Dependencies

- Phase 1, because this phase adds Windows overwrite handling in `src/fs/mod.rs`.
- Phase 2, because checksum logic must target the copy-only action model after REF-01.
- Phase 4, because `sync/mod.rs` and planner/apply expectations need the settled conflict-policy shape before checksum rules are pinned down.

## Tester Lanes

- `@verifier`: confirm all write-producing outcomes carry non-empty checksums and that divergent items are preserved rather than silently overwritten.
- `@smoke-tester`: run `cargo build`, `cargo test`, `cargo clippy`, and `cargo check --target x86_64-pc-windows-msvc` from `/home/jimyao/gitrepos/mars-agents/`; exercise failed target copies, skipped-item divergence, and force/repair recovery paths.
- `@unit-tester`: add or update focused tests for post-write verification, lock-build rejection of missing checksums, skipped-outcome checksum propagation, and Windows read-only handling.

## Edge Cases and Constraints

- Lock advancement still tracks `.mars/` canonical state even when target sync fails; the phase must preserve that behavior while surfacing failures clearly.
- Divergent targets and divergent managed items must warn and preserve local content until `mars sync --force` or `mars repair`.
- Missing targets should self-heal by re-copying from `.mars/`; edited or otherwise divergent targets should not be overwritten automatically.
- Preserve the existing `#[cfg(unix)]` permission gating and add only the Windows-specific read-only mitigation that the architecture calls for.

## Exit Criteria

- All write-producing outcomes have mandatory `installed_checksum` values and lock building rejects empty or missing checksums.
- Install and overwrite paths verify written content before recording success.
- Sync detects disk-lock and target divergence, warns clearly, preserves divergent local content, and re-copies only missing targets.
- Windows read-only overwrite handling is explicit and does not break Unix permission gating.
- `cargo build`, `cargo test`, `cargo clippy`, and `cargo check --target x86_64-pc-windows-msvc` pass from `/home/jimyao/gitrepos/mars-agents/`.
