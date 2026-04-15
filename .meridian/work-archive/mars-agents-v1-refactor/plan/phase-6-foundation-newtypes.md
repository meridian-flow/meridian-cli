# Phase 6: Foundation Newtypes

**Fixes:** #8 (stringly-typed identities — partial), #15 (EffectiveConfig bundling — partial)
**Design doc:** [newtypes-and-parsing.md](../design/newtypes-and-parsing.md) §Newtype Definitions, §Migration Strategy Phase 7
**Risk:** Medium — many files touched, but each sub-step is mechanical (type change + compiler-driven migration)

## Scope and Intent

Introduce `SourceName`, `ItemName`, `CommitHash`, `ContentHash` newtypes via a `string_newtype!` macro in `src/types.rs`. Migrate core types (`ItemId`, `EffectiveConfig`, `ResolvedGraph`, `LockFile`, `TargetItem`) to use them. Each sub-step compiles independently.

## Files to Modify

- **`src/types.rs`** (NEW) — `string_newtype!` macro, `SourceName`, `ItemName`, `CommitHash`, `ContentHash` definitions
- **`src/lib.rs`** — Add `pub mod types;`
- **`src/lock/mod.rs`** — `ItemId.name` → `ItemName`, `LockedSource.commit` → `CommitHash`, `LockedItem.source` → `SourceName`, checksums → `ContentHash`
- **`src/config/mod.rs`** — `EffectiveConfig.sources` key → `SourceName`, `EffectiveSource.name` → `SourceName`, filter lists → `Vec<ItemName>`
- **`src/resolve/mod.rs`** — `ResolvedGraph.nodes` key → `SourceName`, `ResolvedNode.source_name` → `SourceName`, `ResolvedRef.commit` → `CommitHash`
- **`src/sync/target.rs`** — `TargetItem.source_name` → `SourceName`, `TargetItem.source_hash` → `ContentHash`
- **`src/discover/mod.rs`** — `ItemId` construction with `ItemName`
- **`src/validate/mod.rs`** — `ItemId` usage
- **`src/cli/*.rs`** — Where source names / item names are constructed from CLI args
- **`src/manifest/mod.rs`** — `DepSpec.items` → `Vec<ItemName>`

## Dependencies

- **Requires:** Nothing strictly, but easier after phase 4 (fewer call sites due to eliminated wrapper chain)
- **Produces:** Typed identities that phase 7 builds on
- **Independent of:** Phase 5

## Sub-Steps

1. **6a: Define types.rs** — Macro + all newtype definitions. Zero behavior change.
2. **6b: ItemName into ItemId** — ~8 construction sites
3. **6c: SourceName into config** — ~15 read sites + filter lists
4. **6d: SourceName into resolve/lock/target** — ~25 call sites
5. **6e: CommitHash and ContentHash** — ~12 call sites

Each sub-step: `cargo test`, verify, commit.

## Constraints and Boundaries

- **Out of scope:** `DestPath`, `SourceUrl`, `SourceId`, `RenameMap` — those are phase 7
- **Preserve:** TOML serialization format (serde impls on newtypes serialize as bare strings)
- **Preserve:** All 281 tests — newtype serde is transparent

## Verification Criteria

- [ ] `cargo test` — passes after each sub-step
- [ ] New tests: serde roundtrip for each newtype (serialize → deserialize = same value)
- [ ] `cargo clippy -- -D warnings` — clean
- [ ] No raw `String` for source names in `EffectiveConfig`, `ResolvedGraph`, `LockFile`, `TargetItem`
- [ ] No raw `String` for item names in `ItemId`

## Agent Staffing

- **Implementer:** `coder` (mechanical but high touch count — needs patience)
- **Reviewer:** 1 reviewer focused on serde compatibility (lock file format, TOML roundtrip)
- **Tester:** `verifier`
