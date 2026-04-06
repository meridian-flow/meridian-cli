# Phase 2: `ensure_fresh` Helper

**Repo:** mars-agents
**Depends on:** Phase 1 (uses `Settings::models_cache_ttl_hours`)
**Est. size:** ~180 LoC + unit tests

## Goal

Introduce the single helper that centralizes refresh policy, concurrency,
and fallback. After this phase, nothing uses it yet — phases 3 and 4 wire
it in.

## Files

- `src/models/mod.rs`
  - Add `RefreshMode`, `RefreshOutcome` enums.
  - Add `ensure_fresh` function.
  - Add `read_cache_tolerant` wrapper (converts any read/parse error
    into empty cache + `debug!` log).
  - Add `is_fresh(cache, ttl_hours)` and `is_usable(cache)` private
    helpers; empty `models` vector is always stale+unusable.
  - Add shared helpers `is_mars_offline()`,
    `resolve_refresh_mode(no_refresh_flag: bool)`, and
    `load_models_cache_ttl(ctx: &MarsContext)`.
  - Rename `cli::models::now_iso` → `models::now_unix_secs` (returns
    `String`) and `now_unix_secs_value` (returns `u64`). Move into
    `models/mod.rs`.
  - Modify `fetch_models` to:
    1. Read `MARS_MODELS_API_URL` env var with fallback to
       `https://models.dev/api.json`.
    2. Set explicit `ureq::Agent` timeouts: 15s connect, 15s read.
       (Prevents sync from deadlocking on a hung endpoint while
       holding `sync.lock`.)
- `src/cli/models.rs`
  - **Fully rewrite** `run_refresh` to call `ensure_fresh(Force)`. This
    is the only place in this phase or later that touches `run_refresh`.
    Delete the old inline lock/fetch/write code. Delete the old local
    `now_iso` helper.
- `src/error.rs` — add `ModelCacheUnavailable { reason: String }` variant
  with `thiserror` message per `design/ensure-fresh.md` §"Error Types".
- `Cargo.toml` — add `httpmock = "0.7"` to `[dev-dependencies]` for the
  unit tests in this phase (and reused by phase 5).

## Implementation Notes

### Freshness computation

```rust
fn is_fresh(cache: &ModelsCache, ttl_hours: u32) -> bool {
    if ttl_hours == 0 {
        return false;
    }
    if cache.models.is_empty() {
        return false; // empty => stale (see design/cache-freshness.md)
    }
    let Some(fetched_str) = &cache.fetched_at else {
        return false;
    };
    let Ok(fetched) = fetched_str.parse::<u64>() else {
        return false; // unparseable — treat as stale
    };
    let now = now_unix_secs_value();
    if fetched > now {
        return false; // clock skew / future timestamp — treat as stale
    }
    // u32::MAX * 3600 fits comfortably in u64; no overflow guard needed.
    (now - fetched) < (ttl_hours as u64) * 3600
}

fn is_usable(cache: &ModelsCache) -> bool {
    !cache.models.is_empty()
}
```

Provide both `now_unix_secs() -> String` (for writing `fetched_at`) and
`now_unix_secs_value() -> u64` (for comparisons). The first is a thin
wrapper around the second.

### Tolerant read

```rust
fn read_cache_tolerant(mars_dir: &Path) -> ModelsCache {
    match read_cache(mars_dir) {
        Ok(cache) => cache,
        Err(err) => {
            tracing::debug!(
                "models cache read failed, treating as empty: {err}"
            );
            ModelsCache { models: Vec::new(), fetched_at: None }
        }
    }
}
```

`read_cache` stays strict (used by `refresh` after write-back for
round-trip verification); `read_cache_tolerant` is the one `ensure_fresh`
calls.

### Lock + double-check

```rust
let cache_path = mars_dir.join(CACHE_FILE);
let lock_path = mars_dir.join(".models-cache.lock");
std::fs::create_dir_all(mars_dir)?;

// MARS_OFFLINE coercion: Auto → Offline, Force and Offline pass through.
let effective_mode = match mode {
    RefreshMode::Auto if is_mars_offline() => RefreshMode::Offline,
    m => m,
};

// First read, outside the lock. Tolerant: corrupt/missing => empty.
let prior = read_cache_tolerant(mars_dir);

if effective_mode == RefreshMode::Auto && is_fresh(&prior, ttl_hours) {
    return Ok((prior, RefreshOutcome::AlreadyFresh));
}

if effective_mode == RefreshMode::Offline {
    if is_usable(&prior) {
        return Ok((prior, RefreshOutcome::Offline));
    }
    return Err(MarsError::ModelCacheUnavailable {
        reason: offline_reason(mode),  // distinguishes env vs flag
    });
}

// Auto!fresh or Force: we're going to try to fetch.
let _guard = crate::fs::FileLock::acquire(&lock_path)?;

// Re-check under the lock (Auto only): another process may have just
// refreshed. Force ignores freshness and always attempts to fetch.
let under_lock = read_cache_tolerant(mars_dir);
if effective_mode == RefreshMode::Auto && is_fresh(&under_lock, ttl_hours) {
    return Ok((under_lock, RefreshOutcome::AlreadyFresh));
}

// We own the fetch.
let fetch_result = fetch_models();
match fetch_result {
    Ok(models) if !models.is_empty() => {
        let count = models.len();
        let cache = ModelsCache {
            models,
            fetched_at: Some(now_unix_secs()),
        };
        write_cache(mars_dir, &cache)?;
        Ok((cache, RefreshOutcome::Refreshed { models_count: count }))
    }
    Ok(_) => {
        // Empty catalog — treat as fetch failure.
        fall_back(under_lock, "API returned empty catalog".to_string())
    }
    Err(err) => fall_back(under_lock, format!("fetch failed: {err}")),
}

fn fall_back(
    under_lock: ModelsCache,
    reason: String,
) -> Result<(ModelsCache, RefreshOutcome), MarsError> {
    if is_usable(&under_lock) {
        tracing::warn!("models cache refresh failed: {reason}; using stale cache");
        Ok((under_lock, RefreshOutcome::StaleFallback { reason }))
    } else {
        Err(MarsError::ModelCacheUnavailable { reason })
    }
}

fn offline_reason(requested_mode: RefreshMode) -> String {
    // If caller passed Offline explicitly, the trigger was the
    // `--no-refresh-models` flag (or a programmatic caller). Otherwise
    // it was MARS_OFFLINE coercion.
    match requested_mode {
        RefreshMode::Offline =>
            "--no-refresh-models was passed and no cached catalog is available".into(),
        _ =>
            "MARS_OFFLINE is set and no cached catalog is available".into(),
    }
}
```

Note: no `ensure_fresh_with` / `ModelFetcher` trait. The testability
seam is `MARS_MODELS_API_URL` read inside `fetch_models` itself. Phase-2
unit tests spin up an in-process `httpmock::MockServer` and set that
env var per-test; phase 5 uses the same mechanism for multi-process
integration tests.

### Helpers

```rust
pub fn is_mars_offline() -> bool {
    match std::env::var("MARS_OFFLINE") {
        Ok(v) => matches!(
            v.trim().to_ascii_lowercase().as_str(),
            "1" | "true" | "yes"
        ),
        Err(_) => false,
    }
}

pub fn resolve_refresh_mode(no_refresh_flag: bool) -> RefreshMode {
    if no_refresh_flag || is_mars_offline() {
        RefreshMode::Offline
    } else {
        RefreshMode::Auto
    }
}

pub fn load_models_cache_ttl(ctx: &MarsContext) -> u32 {
    crate::config::load(&ctx.project_root)
        .map(|c| c.settings.models_cache_ttl_hours)
        .unwrap_or(24)
}
```

`ensure_fresh` also calls `is_mars_offline()` internally as a
defense-in-depth check, so a direct call like
`ensure_fresh(&mars, 24, RefreshMode::Auto)` from a non-CLI caller
still inherits the env opt-out.

### `run_refresh` rewrite (owned by this phase)

```rust
fn run_refresh(ctx: &MarsContext, json: bool) -> Result<i32, MarsError> {
    let mars = mars_dir(ctx);
    let ttl = models::load_models_cache_ttl(ctx);
    eprint!("Fetching models catalog... ");

    let (cache, _outcome) = models::ensure_fresh(
        &mars, ttl, models::RefreshMode::Force,
    )?;

    let count = cache.models.len();
    // ...existing JSON / text output using `count` and `cache.fetched_at`...
}
```

Phases 3 and 4 must **not** touch `run_refresh`. Phase 2 fully owns it.

## Unit Tests

All tests use `tempfile::tempdir` for a temporary `.mars` dir,
`httpmock::MockServer` for the API stub, and `#[serial_test::serial]`
for env var isolation.

1. **Missing cache, offline** → `ModelCacheUnavailable` with
   `MARS_OFFLINE` reason.
2. **Missing cache, auto, stub 500** → `ModelCacheUnavailable` with
   `fetch failed` reason.
3. **Stale-but-usable cache, offline** → returns stale,
   `RefreshOutcome::Offline`.
4. **Fresh cache, auto** → no HTTP call (assert stub hit count = 0),
   `AlreadyFresh`.
5. **Stale cache, auto, stub 200** → returns new cache, `Refreshed`.
6. **Stale cache, auto, stub 500** → returns stale cache,
   `StaleFallback`.
7. **Stale cache, auto, stub 200 with empty array** → treated as fetch
   failure; returns stale cache, `StaleFallback`.
8. **Empty cache (`models=[]`, `fetched_at` present), auto, stub 200**
   → refetches; `Refreshed`.
9. **Empty cache, offline** → `ModelCacheUnavailable` (empty is not
   usable).
10. **Corrupt JSON file, auto, stub 200** → refetches; `Refreshed`.
11. **Corrupt JSON file, offline** → `ModelCacheUnavailable`.
12. **TTL = 0, auto, fresh-by-other-criteria cache, stub 200** → refetches.
13. **`fetched_at` unparseable** → treated as stale.
14. **`fetched_at` in future** → treated as stale.
15. **`MARS_OFFLINE=1` + auto + fresh cache** → `AlreadyFresh`, no stub
    hit.
16. **`MARS_OFFLINE=0`** → not offline (parsed as non-truthy).
17. **`MARS_OFFLINE=TRUE`** → offline (case-insensitive).
18. **Force mode + `MARS_OFFLINE=1` + stub 200** → still fetches
    (Force ignores env). This is the `mars models refresh` contract.
19. **Concurrency**: two threads calling `ensure_fresh(Auto)` against a
    stale cache with a stub that sleeps 200ms and counts hits → both
    threads return `AlreadyFresh`/`Refreshed`, exactly one hit recorded.
20. **`run_refresh` → ensure_fresh(Force)** integration test:
    `cargo run -- models refresh` in a temp dir writes a cache; assert
    `fetched_at` is recent and `models` is non-empty.

### Mocking `fetch_models`

Seam: `fetch_models` reads `MARS_MODELS_API_URL` with fallback to
`https://models.dev/api.json`. Every test (unit and integration)
points that env var at an in-process `httpmock::MockServer`.

```rust
#[test]
fn auto_refreshes_stale_cache() {
    let server = httpmock::MockServer::start();
    server.mock(|when, then| {
        when.method(GET).path("/api.json");
        then.status(200).json_body(sample_catalog_json());
    });
    std::env::set_var("MARS_MODELS_API_URL", server.url("/api.json"));

    let tmp = tempfile::tempdir().unwrap();
    write_stale_cache(tmp.path());

    let (cache, outcome) =
        ensure_fresh(tmp.path(), 24, RefreshMode::Auto).unwrap();
    assert!(!cache.models.is_empty());
    assert!(matches!(outcome, RefreshOutcome::Refreshed { .. }));
}
```

No `ensure_fresh_with`, no `ModelFetcher` trait. One API, one seam.

**Env var isolation:** tests must set `MARS_MODELS_API_URL` and
`MARS_OFFLINE` via a serial fixture or guarded pattern — Cargo runs
tests in parallel by default and the env is process-global. Either
(a) use `#[serial_test::serial]` on the affected tests (add
`serial_test` to dev-deps), or (b) serialize with a `Mutex<()>` inside
the test module. Pick (a); it's the standard Rust pattern.

## Verification

- `cargo test --package mars-agents models::`
- `cargo clippy --all-targets -- -D warnings`
- Manual smoke: `rm -f .mars/models-cache.json && cargo run -- models
  list` in a test fixture should trigger a fetch via the test's stub path
  (covered by phase 3, but spot-check in an integration test if
  convenient).

## Guard Rails

- **Do not** bundle the phase 3/4 call-site rewires into this phase. The
  review of phase 2 must see only the helper in isolation.
- **Do not** rename `fetched_at` or change `ModelsCache`'s serialized
  shape. Unparseable tolerance is in `is_fresh`, not in the struct.
- If you hit a reason to change `ensure_fresh`'s signature, stop and
  surface it to the orchestrator — downstream phases rely on it.
