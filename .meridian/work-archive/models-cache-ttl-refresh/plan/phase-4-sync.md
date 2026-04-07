# Phase 4: Wire `mars sync`

**Repo:** mars-agents
**Depends on:** Phase 2
**Parallel with:** Phase 3
**Est. size:** ~60 LoC + tests

## Goal

Call `ensure_fresh(Auto)` inside `mars sync` so that new aliases landing in
`models-merged.json` are always accompanied by a catalog that covers them.
Sync never aborts on cache refresh failure — it warns and continues.

## Files

- `src/cli/sync.rs`
  - Add `--no-refresh-models: bool` to `SyncArgs`.
  - Thread the flag into `SyncOptions.no_refresh_models`.
- `src/sync/mod.rs`
  - Add `no_refresh_models: bool` to `SyncOptions`.
  - Call `ensure_fresh` right before the `models-merged.json` write block
    (~line 559 in current file).
  - Report `RefreshOutcome` via the existing `DiagnosticCollector` warn
    channel on `StaleFallback` or errors; silent on `AlreadyFresh` and
    `Refreshed`.

## Implementation

### Insertion point (`sync/mod.rs` around line 559)

```rust
// Catalog refresh: ensure the models cache covers any new aliases we're
// about to persist. Best-effort — warn and continue on failure so sync
// never blocks on network hiccups.
if !request.options.dry_run {
    let mars_path = ctx.project_root.join(".mars");
    let ttl = crate::models::load_models_cache_ttl(ctx);
    let mode = crate::models::resolve_refresh_mode(
        request.options.no_refresh_models,
    );
    match crate::models::ensure_fresh(&mars_path, ttl, mode) {
        Ok((_, crate::models::RefreshOutcome::StaleFallback { reason })) => {
            diag.warn(
                "models-cache-refresh",
                format!("using stale models cache: {reason}"),
            );
        }
        Ok((_, crate::models::RefreshOutcome::Offline)) => {
            // Offline and cache present — silent. Consumers that need the
            // catalog will surface their own errors.
        }
        Ok(_) => { /* AlreadyFresh or Refreshed — silent */ }
        Err(err) => {
            diag.warn(
                "models-cache-refresh",
                format!("failed to refresh models cache: {err}"),
            );
        }
    }
}
```

This block goes *before* the existing `match serde_json::to_string_pretty
(&dep_model_aliases)` so the catalog is populated first, even though the
two files are logically independent. Ordering aids debuggability: a user
looking at "did sync finish?" sees catalog, then merged, then done.

### `SyncOptions`

```rust
pub struct SyncOptions {
    pub force: bool,
    pub dry_run: bool,
    pub frozen: bool,
    pub no_refresh_models: bool,  // NEW
}
```

**Known construction sites** (update all of them):

1. `src/cli/sync.rs::run` — the primary CLI entry. Wire in
   `args.no_refresh_models`.
2. `src/cli/add.rs` — `mars add` constructs a `SyncRequest` internally.
   Default to `false` so `mars add` always refreshes.
3. Any `SyncOptions { ... }` struct literal in `src/sync/` tests.
4. Any `SyncOptions::default()` or `..Default::default()` path — if
   `SyncOptions` derives `Default`, the new field becomes `false` for
   free; verify no existing site depends on a specific construction
   shape that rejects unknown fields.

Before starting, the coder runs
`rg -n 'SyncOptions\\s*\\{' ../mars-agents/src` and
`rg -n 'SyncOptions::default' ../mars-agents/src` to produce an
exhaustive list, and updates every hit. The review of phase 4 verifies
no construction site was missed.

### `SyncArgs`

```rust
/// Skip the automatic models-cache refresh during sync.
#[arg(long)]
pub no_refresh_models: bool,
```

Wire into `SyncRequest::options` in `cli/sync.rs::run`.

## Verification

- `cargo test --package mars-agents sync::`
- Smoke:
  1. `rm -f .mars/models-cache.json`
  2. `cargo run -- sync --force` in a test fixture → cache populated after
     sync.
  3. `MARS_OFFLINE=1 cargo run -- sync --force` → cache remains empty,
     sync still exits 0.
  4. `cargo run -- sync --force --no-refresh-models` → same as case 3.

## Unit Tests

- `SyncArgs` parser test for `--no-refresh-models`.
- A `SyncOptions` construction test ensuring the field defaults to
  `false` in the obvious constructor path.
- An integration test for the sync pipeline using the `MARS_MODELS_API_URL`
  + `httpmock` seam introduced in phase 2: stand up a stub server, run
  `mars sync --force` against a temp project, assert the cache file
  exists with non-empty `models` after sync. Same scenario with the
  stub returning 500 → sync still exits 0, diag warning recorded.

## Guard Rails

- **Do not** make sync fail on ensure_fresh errors. The requirements are
  explicit that sync should complete even offline.
- **Do not** call `ensure_fresh` inside `dry_run` — dry-run is
  side-effect-free by convention, and refreshing the cache is a
  side-effect.
- **Do not** move the `models-merged.json` write into `ensure_fresh` or
  vice versa — they stay separate concerns.
- **Rely on phase 2's `fetch_models` timeout.** Sync holds `sync.lock`
  across the whole pipeline; an unbounded fetch inside `ensure_fresh`
  would deadlock concurrent syncs. Phase 2 sets a 15s+15s ureq timeout,
  so the worst-case extra stall is ~30s. Do not add another timeout
  layer here.
