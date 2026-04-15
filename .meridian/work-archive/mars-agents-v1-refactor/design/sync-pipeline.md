# Unified Sync Pipeline

Fixes: #1 (forked engine), #2 (config races), #12 (build/check_collisions split), #13 (target.rs split), #14 (sync/mod.rs concerns).

See [overview](overview.md) for how this fits into the full refactor.

## Problem

Three related bugs share one root cause: the sync pipeline lacks a single entry point.

**Forked engine** (`cli/upgrade.rs:32-94`). The upgrade command reimplements the resolve→target→diff→plan→apply→lock-write pipeline instead of routing through `sync/mod.rs`. It duplicates `RealSourceProvider` as `SyncSourceProvider` (identical implementation), skips `validate_skill_refs` (silent validation regression), hardcodes `force: false, dry_run: false, frozen: false`, and most critically — never acquires flock. Any concurrent operation during upgrade corrupts state.

**Config load before flock** (`cli/add.rs:78`, `cli/remove.rs:19`, `cli/upgrade.rs:38`). All three commands call `config::load(root)` before the pipeline acquires flock. Two concurrent `mars add` operations both read the same config, both insert their source, then the second write clobbers the first. The window is small but real — CI scripts running `mars add` in parallel will hit this.

**Layered entry helpers** (`cli/sync.rs:46-109`). The current API has `run_sync` → `run_sync_with_config` → `run_sync_with_effective_config` → `sync::sync_with_effective_config`. Four layers of wrappers that each add one parameter. Callers that need different behavior (upgrade's `maximize`) bypass all of them.

## Design

### Core Type: `SyncRequest`

Every command constructs a `SyncRequest` and passes it to `sync::execute()`. The request captures **what** the command wants — resolution strategy, config changes, behavioral flags — without touching config files or state.

```rust
// sync/mod.rs

/// What a CLI command wants the sync pipeline to do.
///
/// All state-mutating commands construct this and call `sync::execute()`.
/// The pipeline handles flock, config loading, mutation, resolution, and
/// application as one atomic operation.
#[derive(Debug)]
pub struct SyncRequest {
    /// How to resolve versions.
    pub resolution: ResolutionMode,
    /// Config mutation to apply under flock (if any).
    pub mutation: Option<ConfigMutation>,
    /// Behavioral flags.
    pub options: SyncOptions,
}

/// Controls version resolution behavior.
///
/// Maps to `ResolveOptions` internally. Separates the CLI's intent
/// from the resolver's implementation.
#[derive(Debug, Clone)]
pub enum ResolutionMode {
    /// Normal sync: Minimum Version Selection, prefer locked versions.
    /// This is the default for `mars sync`.
    Normal,
    /// Upgrade: maximize versions for specified sources.
    /// Empty `targets` means upgrade all sources.
    /// This is `mars upgrade [sources...]`.
    Maximize {
        targets: HashSet<String>,
    },
}

/// Config mutations applied atomically under flock.
///
/// The pipeline loads config from disk, applies the mutation, validates
/// the result, runs the full sync, then persists the mutated config
/// only after the pipeline succeeds.
#[derive(Debug, Clone)]
pub enum ConfigMutation {
    /// Add or update a source entry (`mars add`).
    UpsertSource {
        name: String,
        entry: SourceEntry,
    },
    /// Remove a source by name (`mars remove`).
    RemoveSource {
        name: String,
    },
    /// Set a dev override in agents.local.toml (`mars override`).
    SetOverride {
        source_name: String,
        local_path: PathBuf,
    },
    /// Remove a dev override (`mars override --clear`).
    ClearOverride {
        source_name: String,
    },
}

/// Behavioral flags — unchanged from current `SyncOptions`.
#[derive(Debug, Clone)]
pub struct SyncOptions {
    /// Overwrite local modifications.
    pub force: bool,
    /// Show what would change without writing.
    pub dry_run: bool,
    /// Error if the lock file would change.
    pub frozen: bool,
}
```

### Why `frozen` Is in `SyncOptions`, Not `ResolutionMode`

Frozen mode doesn't change how versions are resolved — it runs normal resolution and then rejects the result if it would change the lock. The check happens at step 12 (after planning, before applying), not during resolution. Making frozen a resolution mode would conflate "how to pick versions" with "whether to allow changes," which are independent concerns.

The resolver-and-errors design (separate doc) will add locked-SHA replay to make frozen sync actually reproducible. That change lives in the resolver, not in the pipeline orchestration designed here.

### Rejected Alternative: `ResolutionMode::Frozen`

Considered making `Frozen` a third resolution mode alongside `Normal` and `Maximize`. Rejected because:
1. Frozen is orthogonal to resolution strategy — you could theoretically want "frozen upgrade" (check if upgrade would change anything) though we reject that combination today
2. The frozen check happens at plan time, not resolution time — putting it in resolution mode would split the concern across two stages
3. Current test coverage validates frozen behavior at the plan stage; moving it would require rewriting those tests for no functional gain

### Command Mapping

| Command | `ResolutionMode` | `ConfigMutation` | Key `SyncOptions` |
|---------|-----------------|------------------|--------------------|
| `mars sync` | `Normal` | `None` | `force`, `dry_run`, `frozen` from flags |
| `mars sync --frozen` | `Normal` | `None` | `frozen: true` |
| `mars upgrade` | `Maximize { targets: {} }` | `None` | defaults |
| `mars upgrade foo bar` | `Maximize { targets: {foo, bar} }` | `None` | defaults |
| `mars add owner/repo@v2` | `Normal` | `UpsertSource { name, entry }` | defaults |
| `mars remove foo` | `Normal` | `RemoveSource { name: "foo" }` | defaults |
| `mars override foo --path ./local` | `Normal` | `SetOverride { ... }` | defaults |

### Invalid Combinations

Validated eagerly before acquiring flock. Fail-fast with clear error messages.

```rust
/// Validate a SyncRequest before executing.
///
/// Called at the top of `execute()` — catches contradictory flags
/// before touching any state.
fn validate_request(request: &SyncRequest) -> Result<(), MarsError> {
    // Frozen + Maximize: contradictory intent
    if request.options.frozen {
        if matches!(request.resolution, ResolutionMode::Maximize { .. }) {
            return Err(MarsError::InvalidRequest {
                message: "cannot use --frozen with upgrade \
                         (frozen locks versions; upgrade maximizes them)"
                    .to_string(),
            });
        }
        // Frozen + mutation: can't modify config if lock can't change
        if request.mutation.is_some() {
            return Err(MarsError::InvalidRequest {
                message: "cannot modify config in --frozen mode \
                         (config change would require lock update)"
                    .to_string(),
            });
        }
    }
    Ok(())
}
```

`MarsError::InvalidRequest` is a new variant (exit code 2, usage error). Existing error variants are untouched — exit code mapping is handled by the [resolver-and-errors](resolver-and-errors.md) design.

## Pipeline: Step-by-Step

The pipeline preserves all 17 steps from the current `sync_with_effective_config`. The changes are: (a) config load and mutation move inside flock, (b) `ResolveOptions` are derived from `ResolutionMode`, (c) `SyncContext` is eliminated.

```rust
/// Execute the unified sync pipeline.
///
/// Single entry point for all state-mutating commands.
/// Config is loaded and mutated under flock — no concurrent writer
/// can see a partial state.
pub fn execute(root: &Path, request: &SyncRequest) -> Result<SyncReport, MarsError> {
    // Step 0: Validate request (fail-fast, no I/O)
    validate_request(request)?;

    // Ensure .mars/ directory exists
    std::fs::create_dir_all(root.join(".mars").join("cache"))?;

    // Step 1: Acquire flock
    let lock_path = root.join(".mars").join("sync.lock");
    let _sync_lock = crate::fs::FileLock::acquire(&lock_path)?;

    // ── Everything below runs under flock ──

    // Step 2: Load config from disk
    let mut config = match crate::config::load(root) {
        Ok(c) => c,
        Err(e) if is_config_not_found(&e) && request.mutation.is_some() => {
            // Auto-init: mutation on missing config starts from empty
            Config::default()
        }
        Err(e) => return Err(e),
    };

    // Step 3: Apply config mutation (if any)
    let has_mutation = request.mutation.is_some();
    if let Some(mutation) = &request.mutation {
        apply_mutation(&mut config, mutation)?;
    }

    // Step 4: Load and mutate agents.local.toml (for override mutations)
    let mut local = crate::config::load_local(root)?;
    if let Some(mutation) = &request.mutation {
        apply_local_mutation(&mut local, mutation)?;
    }

    // Step 4b: Merge config + local into effective config
    let effective = crate::config::merge(config.clone(), local.clone())?;

    // Step 5: Validate resolution targets exist in config
    validate_targets(&request.resolution, &effective)?;

    // Step 6: Load existing lock file
    let old_lock = crate::lock::load(root)?;

    // Step 7: Resolve dependency graph
    let cache = CacheDir::new(root)?;
    let provider = RealSourceProvider {
        cache_dir: &cache.path,
        project_root: root,
    };
    let resolve_options = to_resolve_options(&request.resolution);
    let graph = crate::resolve::resolve(
        &effective, &provider, Some(&old_lock), &resolve_options,
    )?;

    // Step 8: Build target state (discovery + filtering)
    let (mut target_state, renames) =
        target::build_with_collisions(&graph, &effective)?;

    // Step 9: Handle collisions + rewrite frontmatter refs
    if !renames.is_empty() {
        target::rewrite_skill_refs(&mut target_state, &renames, &graph)?;
    }

    // Step 10: Validate skill references
    let warnings = validate_skill_refs(root, &target_state);

    // Step 11: Check unmanaged on-disk collisions
    target::check_unmanaged_collisions(root, &old_lock, &target_state)?;

    // Step 12: Compute diff
    let sync_diff = diff::compute(
        root, &old_lock, &target_state, request.options.force,
    )?;

    // Step 13: Create plan
    let cache_bases_dir = root.join(".mars").join("cache").join("bases");
    let sync_plan = plan::create(&sync_diff, &request.options, &cache_bases_dir);

    // Step 14: Frozen gate — reject if plan has changes
    if request.options.frozen {
        let has_changes = sync_plan.actions.iter().any(|a| {
            !matches!(
                a,
                plan::PlannedAction::Skip { .. }
                    | plan::PlannedAction::KeepLocal { .. }
            )
        });
        if has_changes {
            return Err(MarsError::FrozenViolation {
                message: "lock file would change but --frozen is set"
                    .to_string(),
            });
        }
    }

    // Step 15: Persist config and/or local config (only if mutated and not dry-run)
    if has_mutation && !request.options.dry_run {
        match &request.mutation {
            Some(ConfigMutation::UpsertSource { .. } | ConfigMutation::RemoveSource { .. }) => {
                crate::config::save(root, &config)?;
            }
            Some(ConfigMutation::SetOverride { .. } | ConfigMutation::ClearOverride { .. }) => {
                crate::config::save_local(root, &local)?;
            }
            None => {}
        }
    }

    // Step 16: Apply plan
    let applied = apply::execute(
        root, &sync_plan, &request.options, &cache_bases_dir,
    )?;

    let pruned = Vec::new();

    // Step 17: Write lock file
    if !request.options.dry_run {
        let new_lock = crate::lock::build(&graph, &applied, &old_lock)?;
        crate::lock::write(root, &new_lock)?;
    }

    // Step 18: Lock released on drop of _sync_lock

    Ok(SyncReport {
        applied,
        pruned,
        warnings,
    })
}
```

### Helper Functions

```rust
/// Apply a ConfigMutation to a loaded Config.
///
/// Validates the mutation is well-formed (e.g., source exists for remove).
/// Does NOT write to disk — that happens after the pipeline succeeds.
fn apply_mutation(config: &mut Config, mutation: &ConfigMutation) -> Result<(), MarsError> {
    match mutation {
        ConfigMutation::UpsertSource { name, entry } => {
            config.sources.insert(name.clone(), entry.clone());
            Ok(())
        }
        ConfigMutation::RemoveSource { name } => {
            if !config.sources.contains_key(name) {
                return Err(MarsError::Source {
                    source_name: name.clone(),
                    message: format!("source `{name}` not found in agents.toml"),
                });
            }
            config.sources.shift_remove(name);
            Ok(())
        }
        ConfigMutation::SetOverride { source_name, local_path } => {
            // Validate the source exists in config
            if !config.sources.contains_key(source_name) {
                return Err(MarsError::Source {
                    source_name: source_name.clone(),
                    message: format!("source `{source_name}` not found in agents.toml"),
                });
            }
            // Override mutations are applied to local_config, not config.
            // Caller must also call apply_local_mutation().
            Ok(())
        }
        ConfigMutation::ClearOverride { source_name } => {
            Ok(())
        }
    }
}

/// Apply override mutations to agents.local.toml.
///
/// SetOverride adds/updates an entry; ClearOverride removes one.
/// Non-override mutations are no-ops here.
fn apply_local_mutation(
    local: &mut LocalConfig,
    mutation: &ConfigMutation,
) -> Result<(), MarsError> {
    match mutation {
        ConfigMutation::SetOverride { source_name, local_path } => {
            local.overrides.insert(
                source_name.clone(),
                OverrideEntry { path: local_path.clone() },
            );
            Ok(())
        }
        ConfigMutation::ClearOverride { source_name } => {
            local.overrides.shift_remove(source_name);
            Ok(())
        }
        _ => Ok(()), // Non-override mutations handled by apply_mutation
    }
}

/// Validate that upgrade targets exist in the effective config.
fn validate_targets(
    resolution: &ResolutionMode,
    effective: &EffectiveConfig,
) -> Result<(), MarsError> {
    if let ResolutionMode::Maximize { targets } = resolution {
        for name in targets {
            if !effective.sources.contains_key(name) {
                return Err(MarsError::Source {
                    source_name: name.clone(),
                    message: format!("source `{name}` not found in agents.toml"),
                });
            }
        }
    }
    Ok(())
}

/// Convert ResolutionMode to the resolver's ResolveOptions.
fn to_resolve_options(mode: &ResolutionMode) -> ResolveOptions {
    match mode {
        ResolutionMode::Normal => ResolveOptions::default(),
        ResolutionMode::Maximize { targets } => ResolveOptions {
            maximize: true,
            upgrade_targets: targets.clone(),
        },
    }
}
```

### What `SyncContext` Becomes

`SyncContext` currently bundles root, install_target, fetchers, cache, and options. After this change:

- **root**: parameter to `execute()`
- **install_target**: removed (always equals root; add back when workspace support is implemented)
- **fetchers**: `Fetchers` was unused in the current pipeline — `RealSourceProvider` calls source functions directly. Removed.
- **cache**: constructed inside `execute()` from root
- **options**: lives in `SyncRequest`

`SyncContext` is deleted. The struct added no value — it was a parameter object for a function with too many parameters, and the refactor eliminates the parameter explosion by putting everything in `SyncRequest`.

## CLI Layer Changes

### `cli/sync.rs` — After

```rust
//! `mars sync` — resolve + install (make reality match config).

use std::path::Path;

use crate::error::MarsError;
use crate::sync::{SyncOptions, SyncReport, SyncRequest, ResolutionMode};

use super::output;

#[derive(Debug, clap::Args)]
pub struct SyncArgs {
    #[arg(long)]
    pub force: bool,
    #[arg(long)]
    pub diff: bool,
    #[arg(long)]
    pub frozen: bool,
}

pub fn run(args: &SyncArgs, root: &Path, json: bool) -> Result<i32, MarsError> {
    let request = SyncRequest {
        resolution: ResolutionMode::Normal,
        mutation: None,
        options: SyncOptions {
            force: args.force,
            dry_run: args.diff,
            frozen: args.frozen,
        },
    };

    let report = crate::sync::execute(root, &request)?;

    output::print_sync_report(&report, json);
    if report.has_conflicts() { Ok(1) } else { Ok(0) }
}
```

Gone: `run_sync()`, `run_sync_with_config()`, `run_sync_with_effective_config()`. Three layers of helpers replaced by constructing `SyncRequest` directly.

### `cli/upgrade.rs` — After

```rust
//! `mars upgrade` — upgrade sources to newest versions within constraints.

use std::collections::HashSet;
use std::path::Path;

use crate::error::MarsError;
use crate::sync::{SyncOptions, SyncRequest, ResolutionMode};

use super::output;

#[derive(Debug, clap::Args)]
pub struct UpgradeArgs {
    /// Specific sources to upgrade (default: all).
    pub sources: Vec<String>,
}

pub fn run(args: &UpgradeArgs, root: &Path, json: bool) -> Result<i32, MarsError> {
    let request = SyncRequest {
        resolution: ResolutionMode::Maximize {
            targets: args.sources.iter().cloned().collect(),
        },
        mutation: None,
        options: SyncOptions::default(),
    };

    let report = crate::sync::execute(root, &request)?;

    output::print_sync_report(&report, json);
    if report.has_conflicts() { Ok(1) } else { Ok(0) }
}
```

Gone: 140 lines → 30 lines. The entire forked pipeline, the duplicate `SyncSourceProvider`, all of it. Source validation (does the target exist in config?) moved into the pipeline where it runs under flock.

### `cli/add.rs` — After

```rust
pub fn run(args: &AddArgs, root: &Path, json: bool) -> Result<i32, MarsError> {
    let parsed = parse_source_specifier(&args.source)?;

    let entry = SourceEntry {
        url: parsed.entry.url,
        path: parsed.entry.path,
        version: parsed.entry.version,
        agents: if args.agents.is_empty() { None } else { Some(args.agents.clone()) },
        skills: if args.skills.is_empty() { None } else { Some(args.skills.clone()) },
        exclude: if args.exclude.is_empty() { None } else { Some(args.exclude.clone()) },
        rename: None,
    };

    let request = SyncRequest {
        resolution: ResolutionMode::Normal,
        mutation: Some(ConfigMutation::UpsertSource {
            name: parsed.name.clone(),
            entry,
        }),
        options: SyncOptions::default(),
    };

    let report = crate::sync::execute(root, &request)?;

    if !json {
        output::print_info(&format!("added source `{}`", parsed.name));
    }
    output::print_sync_report(&report, json);
    if report.has_conflicts() { Ok(1) } else { Ok(0) }
}
```

Gone: the manual `config::load()` + `config.sources.insert()` before calling sync. The mutation is declarative — `UpsertSource` tells the pipeline what to do; the pipeline loads and mutates config under flock.

Also gone: the auto-init block (lines 40-49 in current add.rs). The pipeline handles auto-init internally when a mutation is requested but no config exists.

### `cli/remove.rs` — After

```rust
pub fn run(args: &RemoveArgs, root: &Path, json: bool) -> Result<i32, MarsError> {
    let request = SyncRequest {
        resolution: ResolutionMode::Normal,
        mutation: Some(ConfigMutation::RemoveSource {
            name: args.source.clone(),
        }),
        options: SyncOptions::default(),
    };

    let report = crate::sync::execute(root, &request)?;

    if !json {
        output::print_info(&format!("removed source `{}`", args.source));
    }
    output::print_sync_report(&report, json);
    if report.has_conflicts() { Ok(1) } else { Ok(0) }
}
```

Gone: the manual `config::load()` + `config.sources.shift_remove()` before calling sync. The "source not found" validation happens inside the pipeline under flock.

## Pipeline Step Comparison

| Step | Current (`sync_with_effective_config`) | After (`execute`) | Changed? |
|------|---------------------------------------|-------------------|----------|
| Validate request | — | `validate_request()` | **New** |
| 1. Acquire flock | Same | Same | No |
| 2. Load config | Done by caller (before flock) | Inside pipeline (under flock) | **Yes** |
| 3. Apply mutation | Done by caller (before flock) | Inside pipeline (under flock) | **Yes** |
| 4. Merge local | Done by caller or step 2 | Inside pipeline | **Moved** |
| 5. Validate targets | In cli/upgrade.rs (before flock) | Inside pipeline (under flock) | **Moved** |
| 6. Load old lock | Same | Same | No |
| 7. Resolve graph | Same (options differ per command) | Same (options derived from mode) | Minimal |
| 8. Build target | Same | Same | No |
| 9. Collisions + rewrite | Same | Same | No |
| 10. Validate skills | Same | Same | No |
| 11. Unmanaged collisions | Same | Same | No |
| 12. Compute diff | Same | Same | No |
| 13. Create plan | Same | Same | No |
| 14. Frozen gate | Same | Same (new error variant) | Minimal |
| 15. Persist config | `write_config` bool param | `has_mutation && !dry_run` | Cleaner |
| 16. Apply plan | Same | Same | No |
| 17. Write lock | Same | Same | No |

12 of 17 steps are unchanged. The changes are concentrated in the first 5 steps (flock, config, mutation) and the config persistence step.

## Concurrency Fix: Config Load Under Flock

The race condition in the current code:

```
Thread A: config = load()          ← reads {source: base}
Thread B: config = load()          ← reads {source: base}
Thread A: config.insert("foo")     ← {base, foo}
Thread B: config.insert("bar")     ← {base, bar}
Thread A: sync(config) → save()    ← writes {base, foo}
Thread B: sync(config) → save()    ← writes {base, bar}  ← foo is LOST
```

After the fix, `execute()` acquires flock before loading config:

```
Thread A: flock()
Thread A: config = load()          ← reads {source: base}
Thread A: config.insert("foo")     ← {base, foo}
Thread A: sync → save()            ← writes {base, foo}
Thread A: release flock
Thread B: flock()                  ← blocks until A releases
Thread B: config = load()          ← reads {base, foo}
Thread B: config.insert("bar")     ← {base, foo, bar}
Thread B: sync → save()            ← writes {base, foo, bar}
Thread B: release flock
```

## Types to Add to `MarsError`

```rust
// In error.rs — new variants
pub enum MarsError {
    // ... existing variants ...

    /// Invalid combination of flags or options.
    /// Exit code 2 (usage error).
    InvalidRequest { message: String },

    /// Frozen mode violated — lock would change.
    /// Exit code 2. Currently uses MarsError::Source as a workaround.
    FrozenViolation { message: String },
}
```

`FrozenViolation` replaces the current hack in `sync_with_effective_config` that constructs `MarsError::Source { source_name: "sync", message: "..." }` — a source error with a fake source name. The exit code mapping design (resolver-and-errors.md) will assign proper exit codes to all variants.

## What Gets Deleted

| File | What | Lines |
|------|------|-------|
| `sync/mod.rs` | `SyncContext` struct | 20→29 |
| `sync/mod.rs` | `sync()` function | 112→120 |
| `sync/mod.rs` | `sync_with_effective_config()` | 126→222 |
| `cli/sync.rs` | `run_sync()` | 46→54 |
| `cli/sync.rs` | `run_sync_with_config()` | 59→78 |
| `cli/sync.rs` | `run_sync_with_effective_config()` | 81→109 |
| `cli/upgrade.rs` | `SyncSourceProvider` struct + impl | 97→140 |
| `cli/upgrade.rs` | Forked pipeline (lines 32→94) | 62 lines |

~180 lines deleted, ~50 lines added (new types + `execute`). Net reduction: ~130 lines.

## Migration Strategy

Incremental — each step leaves the crate compiling and tests passing.

**Step 1: Add types.** Define `SyncRequest`, `ResolutionMode`, `ConfigMutation`, new `MarsError` variants. No callers yet. Pure addition.

**Step 2: Add `execute()`.** Implement the new pipeline function in `sync/mod.rs`. Internally delegates to the existing steps (they're already separate functions). Old entry points (`sync()`, `sync_with_effective_config()`) remain for now.

**Step 3: Migrate `cli/sync.rs`.** Replace `run_sync` / `run_sync_with_config` / `run_sync_with_effective_config` chain with direct `SyncRequest` construction + `execute()` call. Remove the old helper functions.

**Step 4: Migrate `cli/add.rs` and `cli/remove.rs`.** Replace config-load-then-sync pattern with `ConfigMutation` + `execute()`. Remove manual config loading.

**Step 5: Migrate `cli/upgrade.rs`.** Replace forked pipeline with `SyncRequest { resolution: Maximize { targets } }`. Delete `SyncSourceProvider`. This is where the forked engine dies.

**Step 6: Migrate `cli/override.rs` (if using sync).** Replace with `ConfigMutation::SetOverride` + `execute()`.

**Step 7: Delete dead code.** Remove `SyncContext`, old `sync()`, `sync_with_effective_config()`. Remove `run_sync*` helpers from `cli/sync.rs`.

Each step: `cargo test`, `cargo clippy`, verify CLI still works.

## Impact on Other Designs

**Frontmatter module** ([frontmatter.md](frontmatter.md)): No conflict. Frontmatter rewriting happens in steps 8-9 (unchanged). The frontmatter module replaces the implementation inside those steps but the pipeline orchestration is the same.

**Newtypes** ([newtypes-and-parsing.md](newtypes-and-parsing.md)): `ConfigMutation::UpsertSource` uses `SourceEntry` (current stringly-typed struct). When newtypes are introduced, `SourceEntry` fields change type but `ConfigMutation` variant structure stays the same.

**Resolver locked SHA replay** ([resolver-and-errors.md](resolver-and-errors.md)): The resolver change is internal to step 7 (resolve graph). This design doesn't constrain it — `ResolveOptions` is still the interface between pipeline and resolver.

## Test Strategy

### Existing Tests (Must Pass)

The 281 existing tests exercise pipeline stages (target, diff, plan, apply, lock) in isolation. Those stages are unchanged — the tests pass without modification.

The integration tests in `sync/mod.rs` (lines 261-800+) construct graphs and configs directly, bypassing the pipeline entry point. These also pass unchanged since the internal APIs they test (`build_with_collisions`, `diff::compute`, `plan::create`, `apply::execute`, `lock::build`) aren't modified.

### New Tests

1. **Request validation**: frozen+maximize rejected, frozen+mutation rejected
2. **Config mutation under flock**: concurrent `execute()` calls with `UpsertSource` don't lose writes (use `std::thread` + shared temp dir)
3. **Auto-init on add**: `execute()` with `UpsertSource` when no `agents.toml` exists creates config
4. **Upgrade target validation**: `Maximize { targets: {"nonexistent"} }` returns error
5. **Dry-run + mutation**: config is NOT written to disk
6. **Round-trip**: `SyncRequest` → `execute()` produces same `SyncReport` as the old path for equivalent inputs
