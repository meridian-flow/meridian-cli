# Phase 3: A2 — First-Class LocalPackage

**Round:** 2 (parallel with Phase 4 and Phase 5)
**Depends on:** Phase 1 (A1 — typed pipeline phases)
**Risk:** Medium — removes inject_self_items, changes how local items enter the pipeline
**Estimated delta:** ~+100 LOC (SourceOrigin, integration in build_target), ~-150 LOC (inject_self_items, PlannedAction::Symlink special case)
**Codebase:** `/home/jimyao/gitrepos/mars-agents/`

## Scope

Replace the `_self` string sentinel and post-hoc `inject_self_items()` with a first-class `SourceOrigin` enum. Local packages participate in `build_target()` like any other source — through the same `discover_source()` path. The plan is final after `create_plan()` — no more post-creation mutation.

## Why This Matters

`inject_self_items()` mutates the plan after creation, breaking phase ordering. It also maintains a separate discovery path (`discover_local_items`) that won't pick up new item kinds when Phase B adds them. Making local packages first-class means new item kinds work for local packages automatically.

## Files to Modify

| File | Changes |
|------|---------|
| `src/types.rs` | Add `SourceOrigin` enum with `Dependency(SourceName)` and `LocalPackage` variants. Add `Materialization` enum with `Copy` and `Symlink { source_abs: PathBuf }` variants. |
| `src/sync/target.rs` | Integrate local package discovery into `build_target()`. After building target from graph, if `config.package.is_some()`, run project root through the same `discover_source()` as dependencies. Apply shadow precedence (local wins with warning). Set `Materialization::Symlink` for local items. |
| `src/sync/self_package.rs` | **Delete** `inject_self_items()`. Keep `discover_local_items` temporarily as a thin wrapper around `discover_source()` if needed for the transition, or remove entirely and call `discover_source()` directly from `build_target()`. |
| `src/sync/mod.rs` | Remove the `inject_self_items()` call from `create_plan()` (or wherever Phase 1 placed it). |
| `src/sync/plan.rs` | Generate `PlannedAction::Symlink` from `Materialization::Symlink` during plan creation — no longer injected after the fact. |
| `src/sync/diff.rs` | Handle `SourceOrigin::LocalPackage` entries in old lock for orphan detection — stale local items generate `DiffEntry::Orphan` naturally. |
| `src/lock/mod.rs` | Serialize `SourceOrigin::LocalPackage` as `"_self"` for backwards compatibility. Deserialize `"_self"` as `SourceOrigin::LocalPackage`. |
| `src/sync/apply.rs` | Update `ActionOutcome` to use `SourceOrigin` instead of `SourceName` (or keep `SourceName` and map `LocalPackage` → synthetic name for display). |
| `src/discover/mod.rs` | Ensure `discover_source()` works when called with the project root (local package). It already scans `agents/*.md` and `skills/*/SKILL.md` — verify it handles the project root path correctly. |

## Interface Contract

```rust
/// Where an item came from.
pub enum SourceOrigin {
    Dependency(SourceName),
    LocalPackage,
}

/// How an item is materialized in .mars/ (or currently in .agents/).
pub enum Materialization {
    Copy,
    Symlink { source_abs: PathBuf },
}
```

Lock serialization for backwards compatibility:
```rust
impl Serialize for SourceOrigin {
    fn serialize<S>(&self, s: S) -> Result<S::Ok, S::Error> {
        match self {
            Self::Dependency(name) => name.serialize(s),
            Self::LocalPackage => "_self".serialize(s),
        }
    }
}
```

## Key Behavioral Changes

1. **Local items enter the pipeline during `build_target()`**, not after `create_plan()`.
2. **Shadow detection** happens in `build_target()` — local items replace dependency items with a warning.
3. **Orphan pruning** for local items happens in the diff phase — old lock entries with `SourceOrigin::LocalPackage` that aren't in the new target generate `DiffEntry::Orphan`.
4. **No more plan mutation** — `create_plan()` output is final.

## What Gets Deleted

- `sync/self_package.rs::inject_self_items()` — the entire function
- The post-plan `_self` action retention filter
- `SourceName::from("_self")` magic string usages (replaced by `SourceOrigin::LocalPackage`)

## Constraints

- **Use the same `discover_source()` for local packages** (D10). Don't create a separate local discovery path.
- **Only materialization and shadow precedence remain local-specific.** Everything else uses the standard pipeline.
- **Lock backwards compatibility.** `_self` string in lock files must round-trip correctly.

## Verification Criteria

- [ ] `cargo build` compiles cleanly
- [ ] `cargo test` — all existing tests pass
- [ ] `inject_self_items` function is deleted
- [ ] `grep -r '"_self"' src/` returns only the serde serialization in lock.rs (and maybe a test)
- [ ] Local items appear in `mars list` output correctly
- [ ] A project with `[package]` section: `mars sync` produces the same .agents/ content as before
- [ ] A project without `[package]` section: `mars sync` works unchanged

## Agent Staffing

- **Coder:** 1x gpt-5.3-codex
- **Reviewers:** 2x — correctness (verify orphan pruning, shadow precedence), design alignment (verify pipeline participation matches design)
- **Tester:** 1x smoke-tester — test with a project that has both `[package]` and `[dependencies]`, verify local items shadow correctly
