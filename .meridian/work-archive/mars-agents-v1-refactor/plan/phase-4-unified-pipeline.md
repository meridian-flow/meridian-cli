# Phase 4: Unified Sync Pipeline + Flock-First Config Mutation

**Fixes:** #1 (forked engine), #2 (config races), #12 (build/check_collisions split), #13 (target.rs split), #14 (sync/mod.rs concerns)
**Design doc:** [sync-pipeline.md](../design/sync-pipeline.md)
**Risk:** HIGH — largest structural change, touches the core pipeline and all CLI commands

## Scope and Intent

Introduce `SyncRequest`/`ResolutionMode`/`ConfigMutation` types. Implement `sync::execute()` as the single entry point. Migrate all CLI commands (sync, upgrade, add, remove, override) to construct `SyncRequest` and call `execute()`. Delete the forked upgrade engine and wrapper chain. Config is loaded and mutated under flock.

## Files to Modify

- **`src/sync/mod.rs`** — Add `SyncRequest`, `ResolutionMode`, `ConfigMutation`, `SyncOptions`, `execute()`, `validate_request()`, `apply_mutation()`, `validate_targets()`, `to_resolve_options()`. Remove `SyncContext`, `sync()`, `sync_with_effective_config()`.
- **`src/cli/sync.rs`** — Replace `run_sync*` chain with `SyncRequest` construction + `execute()`. Remove wrapper functions.
- **`src/cli/upgrade.rs`** — Replace 140-line forked pipeline with 30-line `SyncRequest { resolution: Maximize }` + `execute()`. Delete `SyncSourceProvider`.
- **`src/cli/add.rs`** — Replace config-load-then-sync with `ConfigMutation::UpsertSource` + `execute()`.
- **`src/cli/remove.rs`** — Replace config-load-then-sync with `ConfigMutation::RemoveSource` + `execute()`.
- **`src/cli/override_cmd.rs`** — Replace with `ConfigMutation::SetOverride`/`ClearOverride` + `execute()` if it currently does a sync.
- **`src/error.rs`** — Variants `InvalidRequest`, `FrozenViolation` already added in phase 3.

## Dependencies

- **Requires:** Phase 3 (error variants for `InvalidRequest`, `FrozenViolation`)
- **Produces:** `sync::execute()` API that all subsequent phases' CLI changes route through
- **Benefits from:** Phase 1 (frontmatter extracted, so target.rs has fewer responsibilities to reason about)

## Interface Contract

```rust
pub struct SyncRequest {
    pub resolution: ResolutionMode,
    pub mutation: Option<ConfigMutation>,
    pub options: SyncOptions,
}

pub enum ResolutionMode {
    Normal,
    Maximize { targets: HashSet<String> },
}

pub enum ConfigMutation {
    UpsertSource { name: String, entry: SourceEntry },
    RemoveSource { name: String },
    SetOverride { source_name: String, local_path: PathBuf },
    ClearOverride { source_name: String },
}

pub fn execute(root: &Path, request: &SyncRequest) -> Result<SyncReport, MarsError>;
```

## Migration Steps (within this phase)

The design doc prescribes 7 incremental steps, each compiling:

1. Add types (pure addition, no callers)
2. Add `execute()` delegating to existing internal functions
3. Migrate `cli/sync.rs`
4. Migrate `cli/add.rs` and `cli/remove.rs`
5. Migrate `cli/upgrade.rs` (forked engine dies here)
6. Migrate `cli/override_cmd.rs`
7. Delete dead code: `SyncContext`, old `sync()`, wrapper chain

## Constraints and Boundaries

- **Out of scope:** Resolver changes (that's phase 5)
- **Out of scope:** Newtype changes (that's phases 6-7)
- **Out of scope:** target.rs file split (the responsibility reduction from phase 1 is enough; further split can happen in phase 8)
- **Preserve:** Internal pipeline stages (target, diff, plan, apply, lock) are UNCHANGED. Only the entry point and config handling change.

## Verification Criteria

- [ ] `cargo test` — all 281 existing tests pass (internal stage tests don't change)
- [ ] New tests:
  - `validate_request`: frozen+maximize rejected, frozen+mutation rejected
  - Config mutation under flock: concurrent `execute()` calls don't lose writes
  - Auto-init: `execute()` with `UpsertSource` when no config exists
  - Upgrade target validation: nonexistent source → error
  - Dry-run + mutation: config NOT written to disk
- [ ] `cargo clippy -- -D warnings` — clean
- [ ] `cli/upgrade.rs` no longer contains pipeline logic (just `SyncRequest` construction)
- [ ] No `config::load()` calls outside `sync::execute()` (except read-only commands: list, why, outdated, doctor)
- [ ] Smoke: `mars sync`, `mars upgrade`, `mars add`, `mars remove` all work

## Design Conformance

- [ ] All mutation commands go through `sync::execute()` with `ConfigMutation`
- [ ] Config is loaded AFTER flock acquisition (verify by reading `execute()` step order)
- [ ] `SyncContext` struct is deleted
- [ ] No `run_sync*` wrapper functions remain

## Agent Staffing

- **Implementer:** `coder` with strong model (architectural ambiguity, many files touched)
- **Reviewers:** 2 reviewers — one for pipeline correctness, one for design alignment
- **Tester:** `verifier` + `smoke-tester` (CLI behavior must be verified end-to-end)
