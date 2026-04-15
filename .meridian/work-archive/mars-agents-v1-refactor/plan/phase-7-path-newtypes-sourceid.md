# Phase 7: Path Newtypes, SourceUrl, SourceId, RenameRule

**Fixes:** #8 (stringly-typed — remainder), #9 (dependency identity by name), #15 (EffectiveConfig bundling)
**Design doc:** [newtypes-and-parsing.md](../design/newtypes-and-parsing.md) §DestPath, §SourceId, §RenameMap
**Risk:** Medium — SourceId adds dedup logic to resolver, RenameMap changes config format internals

## Scope and Intent

Introduce `DestPath` (PathBuf wrapper), `SourceUrl` (canonical URL), `SourceId` (composite identity enum), and `RenameMap`/`RenameRule` (typed rename rules). Wire `SourceId` into the resolver for dependency deduplication. Wire `SourceUrl` into source spec parser from phase 2.

## Files to Modify

- **`src/types.rs`** — Add `DestPath`, `SourceUrl`, `SourceId`, `RenameRule`, `RenameMap` with serde impls
- **`src/sync/target.rs`** — `TargetState.items` key → `DestPath`, `TargetItem.dest_path` → `DestPath`, `TargetItem.source_id` → `SourceId`
- **`src/lock/mod.rs`** — `LockedItem.dest_path` → `DestPath`, `LockedSource.url` → `Option<SourceUrl>`
- **`src/config/mod.rs`** — `SourceEntry` url → `SourceUrl`, rename → `RenameMap`. `EffectiveSource` gains `id: SourceId`.
- **`src/resolve/mod.rs`** — `ResolvedGraph` gains `id_index: HashMap<SourceId, SourceName>`. `ResolvedNode` gains `source_id: SourceId`. Dedup check before node insertion.
- **`src/source/parse.rs`** — Return `SourceUrl` instead of `String` for url field
- **`src/manifest/mod.rs`** — `DepSpec.url` → `SourceUrl`

## Dependencies

- **Requires:** Phase 6 (foundation newtypes must exist)
- **Requires:** Phase 2 (source parser must exist for SourceUrl construction)
- **Produces:** Complete type safety for all identity fields

## Sub-Steps

1. **7a: DestPath** — Target and lock dest_path fields. ~10 call sites.
2. **7b: SourceUrl** — Config, lock, manifest url fields. ~8 call sites.
3. **7c: SourceId** — EffectiveSource, ResolvedNode, TargetItem. Dedup check in resolver. ~6 call sites.
4. **7d: RenameMap** — Config rename fields, collision handling. ~4 call sites.

## Verification Criteria

- [ ] `cargo test` — passes after each sub-step
- [ ] New tests:
  - `SourceId` equality: HTTPS and SSH URLs to same repo → equal `SourceId`
  - `SourceId` dedup: two config entries pointing to same URL → resolver error with clear message
  - `RenameMap` TOML roundtrip: `{ "coder" = "cool-coder" }` format preserved
  - `DestPath.resolve(root)` produces correct absolute path
- [ ] `cargo clippy -- -D warnings` — clean

## Agent Staffing

- **Implementer:** `coder` with strong model (SourceId dedup logic needs careful reasoning)
- **Reviewer:** 1 reviewer focused on resolver correctness + serde compatibility
- **Tester:** `verifier`
