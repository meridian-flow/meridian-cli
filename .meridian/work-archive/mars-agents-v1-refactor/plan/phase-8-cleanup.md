# Phase 8: Cleanup

**Fixes:** #10 (dead SourceFetcher), #11 (lock provenance heuristic), #17 (fat SourceProvider)
**Risk:** Low — removing dead code and cleaning up interfaces

## Scope and Intent

Remove dead abstractions, improve lock provenance, and optionally split the fat `SourceProvider` trait. This is the lowest-risk phase — it cleans up after the structural changes.

## Files to Modify

- **`src/source/mod.rs`** — Remove dead `SourceFetcher` trait and `Fetchers` struct (if they still exist after phase 4). Consider splitting `SourceProvider` into `VersionLister` + `Fetcher` + `ManifestReader` if the split improves testability.
- **`src/lock/mod.rs`** — `build()` takes `ResolvedRef` with full provenance (source URL via `SourceId`) directly instead of heuristically reconstructing from old lock. Single collision-safe builder API.
- **`src/sync/target.rs`** — Consider splitting remaining responsibilities if the file is still large after phases 1 and 4.

## Dependencies

- **Requires:** All prior phases (cleanup builds on the cleaner codebase)
- **Produces:** Final clean state

## Verification Criteria

- [ ] `cargo test` — all tests pass
- [ ] No dead `SourceFetcher`/`Fetchers` types
- [ ] `lock::build()` doesn't reference old lock for URL provenance
- [ ] `cargo clippy -- -D warnings` — clean

## Agent Staffing

- **Implementer:** `coder`
- **Reviewer:** `refactor-reviewer` for structural quality assessment
- **Tester:** `verifier`
