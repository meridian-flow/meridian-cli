# Config Mutations Under Lock

## Problem

`persist_link()` and `remove_link()` in `link.rs` do a load-modify-save cycle on `agents.toml` without acquiring `.mars/sync.lock`. The sync pipeline (`sync/mod.rs:92`) consistently acquires this lock before any config mutation. This is a pattern violation — the codebase has an invariant that all config mutations happen under sync lock, and link breaks it.

## Solution: Extend ConfigMutation

Add two new variants to the existing `ConfigMutation` enum in `sync/mod.rs`:

```rust
pub enum ConfigMutation {
    UpsertSource { name: SourceName, entry: SourceEntry },
    RemoveSource { name: SourceName },
    SetOverride { source_name: SourceName, local_path: PathBuf },
    ClearOverride { source_name: SourceName },
    SetRename { source_name: SourceName, from: String, to: String },
    // NEW:
    /// Add a link target to settings.links (idempotent).
    SetLink { target: String },
    /// Remove a link target from settings.links.
    ClearLink { target: String },
}
```

## apply_mutation Changes

In `sync/mod.rs`, the `apply_mutation` function gains two new arms:

```rust
fn apply_mutation(config: &mut Config, mutation: &ConfigMutation) -> Result<(), MarsError> {
    match mutation {
        // ... existing arms ...
        ConfigMutation::SetLink { target } => {
            if !config.settings.links.contains(target) {
                config.settings.links.push(target.clone());
            }
            Ok(())
        }
        ConfigMutation::ClearLink { target } => {
            config.settings.links.retain(|l| l != target);
            Ok(())
        }
    }
}
```

## Link Command Integration

The link command no longer calls `config::load()` + `config::save()` directly. Instead, it persists the link via the sync pipeline:

```rust
// After creating symlinks successfully:
fn persist_link_config(ctx: &MarsContext, target: &str) -> Result<(), MarsError> {
    let request = SyncRequest {
        resolution: ResolutionMode::Normal,
        mutation: Some(ConfigMutation::SetLink {
            target: target.to_string(),
        }),
        options: SyncOptions {
            dry_run: false,
            // Skip the full sync — just apply the mutation
            mutation_only: true,
            ..SyncOptions::default()
        },
    };
    crate::sync::execute(&ctx.managed_root, &request)?;
    Ok(())
}
```

### Wait — Full Sync Is Overkill

Running the entire sync pipeline (resolve, fetch, diff, apply) just to add a line to `settings.links` is wasteful. The sync pipeline is designed for source management, not settings mutations.

**Better approach**: Extract a lightweight `config_mutate_under_lock` function that:
1. Acquires sync.lock
2. Loads config
3. Applies the mutation
4. Saves config
5. Releases lock

This is the minimal subset of `sync::execute` that link needs.

```rust
/// Apply a config mutation under sync lock, without running the full sync pipeline.
/// Used for settings changes (links) that don't require resolution/installation.
pub fn mutate_config(root: &Path, mutation: &ConfigMutation) -> Result<(), MarsError> {
    let lock_path = root.join(".mars").join("sync.lock");
    let _sync_lock = crate::fs::FileLock::acquire(&lock_path)?;

    let mut config = crate::config::load(root)?;
    apply_mutation(&mut config, mutation)?;
    crate::config::save(root, &config)?;

    Ok(())
}
```

This reuses the existing `apply_mutation` function and lock infrastructure, but skips the sync pipeline's resolution/installation stages. The `ConfigMutation` enum still provides the single point of truth for all config changes.

## Link String Normalization

Before persisting, normalize the link target:
- Strip trailing slashes: `.claude/` → `.claude`
- No path separators allowed (it's a directory name, not a path)

```rust
fn normalize_link_target(target: &str) -> Result<String, MarsError> {
    let normalized = target.trim_end_matches('/').trim_end_matches('\\');
    if normalized.contains('/') || normalized.contains('\\') {
        return Err(MarsError::Link {
            target: target.to_string(),
            message: "link target must be a directory name, not a path".to_string(),
        });
    }
    Ok(normalized.to_string())
}
```

## Where Each Mutation Type Gets Persisted

| Mutation | File | Through |
|---|---|---|
| UpsertSource, RemoveSource, SetRename | agents.toml | sync::execute (full pipeline) |
| SetOverride, ClearOverride | agents.local.toml | sync::execute (full pipeline) |
| SetLink, ClearLink | agents.toml | sync::mutate_config (lock only) |

The key insight: SetLink/ClearLink don't need resolution or installation because they don't affect which agents/skills are installed — they only affect where symlinks point, which is a filesystem operation separate from the sync pipeline.
