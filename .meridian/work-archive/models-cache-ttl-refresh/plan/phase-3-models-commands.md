# Phase 3: Wire `mars models` Commands

**Repo:** mars-agents
**Depends on:** Phase 2 (`ensure_fresh` + shared helpers)
**Parallel with:** Phase 4
**Est. size:** ~80 LoC + tests

## Goal

Route `mars models list` and `mars models resolve` through
`ensure_fresh(Auto)`. **Do not touch `run_refresh` in this phase** —
phase 2 fully owns the rewrite of `run_refresh` to `ensure_fresh(Force)`.

## Files

- `src/cli/models.rs`
  - Add `no_refresh_models: bool` to `ListArgs` and `ResolveAliasArgs`.
  - Rewrite `run_list` to call `ensure_fresh` before reading the cache.
  - Rewrite `run_resolve` to call `ensure_fresh` before reading the
    cache.
  - **Do not touch `run_refresh`.** Phase 2 fully owns it.
  - Remove the "no models cache — run `mars models refresh`" hint from
    `run_list`, since the list command itself now refreshes.
  - On `RefreshOutcome::StaleFallback`, print a stderr warning (non-JSON
    case) or include a `"cache_warning"` field (JSON case).

## Implementation

### `run_list`

```rust
fn run_list(args: &ListArgs, ctx: &MarsContext, json: bool) -> Result<i32, MarsError> {
    let mars = mars_dir(ctx);
    let ttl = models::load_models_cache_ttl(ctx);
    let mode = models::resolve_refresh_mode(args.no_refresh_models);
    let (cache, outcome) = models::ensure_fresh(&mars, ttl, mode)?;

    // ...existing merged/resolved/visibility logic using `cache`...

    if json {
        // include cache_warning if StaleFallback
    } else {
        if let models::RefreshOutcome::StaleFallback { reason } = &outcome {
            eprintln!("warning: using stale models cache ({reason})");
        }
        // existing table output, minus the "no models cache" hint
    }
}
```

### `run_resolve`

Same shape. JSON error envelope: match the exact pattern `run_resolve`
already uses for the "unknown alias" case (see `cli/models.rs` lines
195-208 in the current source) — object with a single `"error"` key,
`serde_json::to_string_pretty`, exit 1. Quote that snippet literally in
the implementation, do not invent a new shape.

```rust
// Matches the existing run_resolve error envelope at cli/models.rs:195-208
println!(
    "{}",
    serde_json::to_string_pretty(&serde_json::json!({
        "error": format!("{err}"),
    })).unwrap()
);
return Ok(1);
```

### `cache_warning` JSON shape

Both `run_list` and `run_resolve` add an optional `cache_warning` string
to their JSON output when `RefreshOutcome::StaleFallback { reason }` is
returned:

```json
{
  "aliases": [...],
  "cache_available": true,
  "cache_warning": "models cache refresh failed: <reason>; using stale cache"
}
```

Absent the field means no warning. Do not use `null`; omit the key.

### `ListArgs` / `ResolveAliasArgs`

Add:

```rust
/// Skip automatic models-cache refresh; use whatever's on disk.
#[arg(long)]
no_refresh_models: bool,
```

Document the flag in `--help` text; user-facing verbiage should mention
`MARS_OFFLINE` as an equivalent env var.

## Verification

- `cargo test --package mars-agents cli::models::`
- Smoke: `rm -f .mars/models-cache.json && cargo run --package mars-agents
  -- models list` → triggers live fetch (or, in a test env with a stubbed
  URL, triggers the stubbed fetcher). Confirm no "no models cache" hint
  appears anymore.
- Smoke: `MARS_OFFLINE=1 cargo run -- models list` with an empty cache →
  clean error mentioning `mars models refresh`.
- Smoke: `cargo run -- models resolve <alias> --no-refresh-models` → same
  error path as `MARS_OFFLINE=1`.

## Unit Tests

- `run_list` with pre-populated fresh cache + `no_refresh_models` → does
  not call fetcher (use a test seam or factor `run_list` so a stub
  `MarsContext` + stub fetcher can be injected; worst case, rely on
  models-layer unit tests from phase 2 and do end-to-end smoke tests
  here).
- Parser test: `ListArgs` parses `--no-refresh-models` correctly.
- Parser test: `ResolveAliasArgs` parses `--no-refresh-models` correctly.

## Guard Rails

- Do not touch `run_refresh`'s Force behavior beyond the phase-2 rename.
- Do not change JSON output keys; only add `cache_warning` (optional,
  present on stale-fallback).
- Preserve `cache_available` key in `run_list` JSON output for backward
  compatibility with meridian's consumer code — meridian's
  `model_aliases.py` does not currently read it, but keeping it avoids a
  surprise later.
