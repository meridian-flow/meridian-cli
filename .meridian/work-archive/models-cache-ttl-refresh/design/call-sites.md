# Call Sites

Every consumer that reads the models cache calls `ensure_fresh`. There
are no exceptions: `mars sync`, `mars models list`, `mars models
resolve`, and `mars models refresh` all route through the same helper.
The mode (`Auto` / `Force`) varies; the path does not.

## 1. `mars sync` — `src/sync/mod.rs`

Context: around line 561, sync writes `.mars/models-merged.json` right after
building the new lock file. We want the models *catalog* (raw model IDs from
API) refreshed *before* the merged alias file is written, so that any
downstream reader seeing the new aliases also sees a catalog that covers
them.

Insertion point: immediately before the `match serde_json::to_string_pretty
(&dep_model_aliases)` block at line 559.

```rust
// Ensure the models catalog covers any new aliases we're about to persist.
let mode = resolve_refresh_mode(request.options.no_refresh_models);
let ttl = load_models_cache_ttl(ctx);
match crate::models::ensure_fresh(&ctx.project_root.join(".mars"), ttl, mode) {
    Ok((_, outcome)) => {
        report_refresh_outcome(&mut diag, outcome);
    }
    Err(err) => {
        diag.warn("models-cache-refresh", format!("{err}"));
        // Do not fail sync — sync's job is to land the alias config; the
        // catalog refresh is best-effort at sync time. Failure surfaces
        // loudly on the next `mars models list`/`resolve` call.
    }
}
```

Sync does **not** abort on `ensure_fresh` failure. Rationale: the user's
`sync` goal is to land manifest/alias changes. If the network is down, they
should still be able to sync, and the first actual agent spawn will surface
the cache problem in its own error path.

### New `SyncOptions` field

```rust
pub struct SyncOptions {
    pub force: bool,
    pub dry_run: bool,
    pub frozen: bool,
    pub no_refresh_models: bool,   // NEW
}
```

### New CLI flag in `cli/sync.rs`

```rust
pub struct SyncArgs {
    // ...existing fields...
    /// Skip the automatic models-cache refresh.
    #[arg(long)]
    pub no_refresh_models: bool,
}
```

Wired through the existing `SyncRequest` conversion.

## 2. `mars models list` — `src/cli/models.rs::run_list`

Replace:
```rust
let cache = models::read_cache(&mars)?;
// ...
if cache.fetched_at.is_none() {
    eprintln!("hint: no models cache — run `mars models refresh` for ...");
}
```

With:
```rust
let mode = resolve_refresh_mode(args.no_refresh_models);
let ttl = load_models_cache_ttl(ctx);
let (cache, outcome) = models::ensure_fresh(&mars, ttl, mode)?;
warn_on_stale_fallback(&outcome);
```

Add `--no-refresh-models: bool` to `ListArgs`.

`mars models list` *does* propagate `ensure_fresh`'s errors (unlike sync) —
if the cache is empty and offline, listing aliases is the command's entire
job, so failing loudly is correct.

## 3. `mars models resolve` — `src/cli/models.rs::run_resolve`

Same pattern as `list`. Add `--no-refresh-models` to `ResolveAliasArgs`.
Resolve fails loudly if the cache is empty and offline.

`meridian`'s agent-launch path shells out to this command, so threading
`ensure_fresh(Auto)` into `run_resolve` is what gives meridian the refresh
guarantee "for free".

## 4. `mars models refresh` — `src/cli/models.rs::run_refresh`

Routes through `ensure_fresh(Force)`. `Force` mode is defined to ignore
`MARS_OFFLINE` (see `ensure-fresh.md` §"MARS_OFFLINE Coercion"), which
preserves the user's intent: "I typed this, fetch now."

```rust
fn run_refresh(ctx: &MarsContext, json: bool) -> Result<i32, MarsError> {
    let mars = mars_dir(ctx);
    let ttl = models::load_models_cache_ttl(ctx);
    eprint!("Fetching models catalog... ");
    let (cache, outcome) = models::ensure_fresh(&mars, ttl, RefreshMode::Force)?;
    // ...existing output, using `cache.models.len()` for count...
}
```

Consolidating through `ensure_fresh` eliminates the previously-proposed
bypass path, so every cache mutation — refresh, sync, list, resolve —
flows through the same lock + double-check + fetch + write logic. One
place to fix bugs.

Phase 2 is the only phase that touches `run_refresh`. Phases 3 and 4
must not rewrite this function.

## 5. `meridian` agent-launch

No direct change on the mars side; meridian already calls
`mars models resolve --json`, which now runs `ensure_fresh(Auto)` internally.
See `meridian-integration.md` for the small timeout adjustment needed on
meridian's subprocess call.

## Shared Helpers

Two small helpers live in `cli/models.rs` (or a new `cli/models_support.rs`)
to avoid duplication across call sites:

```rust
/// Truthy `MARS_OFFLINE` parsing: 1 / true / yes (case-insensitive).
/// Anything else — including unset, empty, "0", "false" — is NOT offline.
pub fn is_mars_offline() -> bool {
    match std::env::var("MARS_OFFLINE") {
        Ok(v) => matches!(
            v.trim().to_ascii_lowercase().as_str(),
            "1" | "true" | "yes"
        ),
        Err(_) => false,
    }
}

/// Resolve the refresh mode from CLI flag + env.
/// Used by Auto-mode callers (list, resolve, sync). Force-mode callers
/// (refresh) call `ensure_fresh(Force)` directly.
pub fn resolve_refresh_mode(no_refresh_flag: bool) -> RefreshMode {
    if no_refresh_flag || is_mars_offline() {
        RefreshMode::Offline
    } else {
        RefreshMode::Auto
    }
}

/// Load configured TTL; default 24.
pub fn load_models_cache_ttl(ctx: &MarsContext) -> u32 {
    crate::config::load(&ctx.project_root)
        .map(|c| c.settings.models_cache_ttl_hours)
        .unwrap_or(24)
}

/// Surface a stale-fallback warning to stderr (non-JSON output only).
pub fn warn_on_stale_fallback(outcome: &RefreshOutcome) { /* ... */ }
```

`sync` also uses these — they live in a module both `cli/` and `sync/`
can see. Placement: `src/models/mod.rs` next to `ensure_fresh`. This
keeps all policy (`ensure_fresh`, `resolve_refresh_mode`,
`is_mars_offline`, `load_models_cache_ttl`) in one module so callers
import exactly one namespace. `ensure_fresh` itself **does not** call
`is_mars_offline` — the env check lives inside `ensure_fresh` as a
separate inline check so that any direct caller (not via
`resolve_refresh_mode`) still inherits `Auto → Offline` coercion.

## Error Messages

When `ensure_fresh` errors with `ModelCacheUnavailable`, callers print:

```
error: models cache is empty and no refresh is allowed (<reason>).
       Run `mars models refresh` to populate it, or unset MARS_OFFLINE.
```

JSON callers return the same message under an `"error"` key and exit code
1, consistent with mars's existing JSON error shape.
