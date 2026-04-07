# `ensure_fresh` — The Refresh Helper

All cache freshness logic lives in one function in `src/models/mod.rs`:

```rust
pub enum RefreshMode {
    /// Refresh if missing or stale; no-op if fresh.
    /// Respects MARS_OFFLINE (coerced to Offline when set).
    Auto,
    /// Refresh unconditionally. Intentionally ignores MARS_OFFLINE —
    /// this mode exists specifically to satisfy `mars models refresh`,
    /// which is "I typed this command, fetch now."
    Force,
    /// Never hit the network; return whatever's on disk, or error if
    /// the cache is absent/unusable.
    Offline,
}

pub enum RefreshOutcome {
    /// Cache was fresh on disk (or another process just refreshed it
    /// under the lock). No network call from us.
    AlreadyFresh,
    /// We performed the fetch and wrote a new cache.
    Refreshed { models_count: usize },
    /// Fetch failed, returning stale cache on disk.
    StaleFallback { reason: String },
    /// Offline mode, returning whatever's on disk (non-empty).
    Offline,
}

pub fn ensure_fresh(
    mars_dir: &Path,
    ttl_hours: u32,
    mode: RefreshMode,
) -> Result<(ModelsCache, RefreshOutcome), MarsError>;
```

The function returns both the cache *and* a structured outcome so callers can
decide how loudly to surface each path (e.g. `mars models refresh` prints
"Cached N models" on `Refreshed`; `mars sync` stays silent on `AlreadyFresh`
but warns on `StaleFallback`).

## Flow

```
enter ensure_fresh(mode)
  |
  | MARS_OFFLINE coercion: if env is truthy AND mode == Auto, mode := Offline
  |                       (Force deliberately ignores MARS_OFFLINE; see contract)
  v
read_cache_tolerant()  --> ModelsCache (empty if missing/unparseable/corrupt)
  |
  +-- mode == Auto && is_fresh(cache) -----> return (cache, AlreadyFresh)
  |
  +-- mode == Offline ---------------------> return offline_or_error(cache)
  |
  +-- mode == Auto && !fresh --\
  +-- mode == Force ------------+-> do_refresh(prior=cache)
                               /
do_refresh(prior):
  acquire FileLock on .mars/.models-cache.lock
  # Re-check freshness under the lock for Auto (a peer may have refreshed).
  under_lock = read_cache_tolerant()
  if mode == Auto and is_fresh(under_lock):
      return (under_lock, AlreadyFresh)
  attempt fetch_models()
    on success:
      if returned_models is empty:
        # treat an empty API response as a fetch failure
        fall through to the "on failure" branch with reason
          "API returned empty catalog"
      else:
        write_cache({ models, fetched_at: now })
        return (cache, Refreshed{count})
    on failure (including empty-catalog coercion):
      if under_lock passes is_usable (non-empty models, any fetched_at):
        warn("models cache refresh failed: {err}; using stale cache")
        return (under_lock, StaleFallback{reason})
      else:
        return Err(MarsError::ModelCacheUnavailable{reason})

offline_or_error(cache):
  if cache is_usable (non-empty models):
      return (cache, Offline)
  else:
      return Err(MarsError::ModelCacheUnavailable{
          reason: "MARS_OFFLINE/--no-refresh-models set and cache is empty"
      })
```

## Tolerant read

`read_cache_tolerant` wraps the existing `read_cache` and coerces **any**
read error (missing file, JSON parse error, unexpected schema) into
`Ok(ModelsCache { models: vec![], fetched_at: None })`. This is the
single point that implements the "corrupt/missing is stale, not fatal"
rule from `cache-freshness.md`. Logged at `debug!` so a corrupted file
isn't silent. The existing `read_cache` stays as the strict reader used
by `mars models refresh` after a successful write (belt-and-braces:
refresh writes and then reads back, fails loudly on parse errors that
would indicate a serialization bug).

## `is_fresh` and `is_usable`

```rust
fn is_fresh(cache: &ModelsCache, ttl_hours: u32) -> bool {
    if ttl_hours == 0 { return false; }
    if cache.models.is_empty() { return false; }  // empty => stale
    let Some(s) = cache.fetched_at.as_deref() else { return false; };
    let Ok(fetched) = s.parse::<u64>() else { return false; };
    let now = now_unix_secs_value();
    if fetched > now { return false; }
    (now - fetched) < (ttl_hours as u64) * 3600
}

fn is_usable(cache: &ModelsCache) -> bool {
    !cache.models.is_empty()
}
```

An empty `models` vector is treated as stale *and* unusable regardless
of `fetched_at`. This closes the "fresh-but-empty" loophole: a cache
file containing `{"models":[], "fetched_at":"..."}` from any source
(test fixture, failed partial write, API returning empty) never passes
`is_fresh`, so `Auto` will re-fetch, and `Offline` will error out with
`ModelCacheUnavailable`.

The "re-read under lock" step is the key correctness guard: the first
caller into a concurrent burst fetches; every subsequent caller wakes up,
sees the fresh timestamp, and returns `AlreadyFresh` immediately without
repeating the network round-trip.

## MARS_OFFLINE Coercion

`ensure_fresh` checks `MARS_OFFLINE` exactly once, at the top of the
function. **`Auto` is coerced to `Offline`**; **`Force` is not**. This
asymmetry is deliberate:

- `Auto` is "refresh if needed" — the user expressing that the fetch is
  implicit. Honoring `MARS_OFFLINE=1` here is correct: the user typed
  the env var, they mean it.
- `Force` is "refresh right now" — the user explicitly asking for a
  fetch. If `MARS_OFFLINE=1` also disabled `Force`, there would be no
  way to refresh an offline-flagged shell without unsetting the env
  var. `Force` is the escape hatch, and `mars models refresh` routes
  through `ensure_fresh(Force)` to inherit it.

`MARS_OFFLINE` truthy values: `1`, `true`, `yes` (case-insensitive).
Anything else — including `0`, `false`, or the unset state — is
not-offline. See `call-sites.md` for the shared `is_mars_offline()`
helper.

The `--no-refresh-models` CLI flag is equivalent to `MARS_OFFLINE=1` for
`Auto`-mode callers; `ensure_fresh` accepts no direct flag argument.
Instead, the CLI-side helper `resolve_refresh_mode(no_refresh_flag)`
returns `Offline` when the flag is set, so the mode passed in is
already `Offline` before `ensure_fresh` runs (see call-sites.md).

## Error Types

Add to `MarsError`:

```rust
#[error("models cache is empty and cannot be refreshed: {reason}. \
         Run `mars models refresh` to populate it.")]
ModelCacheUnavailable { reason: String },
```

`reason` distinguishes the cause so the outer message the user sees can
guide them:

| Cause                                    | `reason` string |
|------------------------------------------|-----------------|
| `MARS_OFFLINE` set, cache missing/empty  | `"MARS_OFFLINE is set and no cached catalog is available"` |
| `--no-refresh-models` flag, empty cache  | `"--no-refresh-models was passed and no cached catalog is available"` |
| Fetch failed online, no prior cache      | `"automatic refresh failed: <err>"` |
| Fetch returned empty catalog, no prior   | `"API returned an empty catalog and no prior cache exists"` |

Callers that print this error **do not** add any extra guidance — the
error's `Display` impl is the single source of truth. A helper in the
error module can synthesize the outer sentence so it stays consistent.

## What `ensure_fresh` Does *Not* Do

- It does not decide *which* caller gets to print status output. Callers
  inspect `RefreshOutcome` and choose their own verbosity.
- It does not cache results in-process. Every call re-reads from disk. This
  keeps state authoritative (see project principle #2: Files as Authority)
  and simplifies test setup.
- It does not retry fetch failures. One attempt, then fall back.
- It does not touch `models-merged.json`. That's sync's concern.
- It does not handle `--dry-run` semantics. Callers that implement dry-run
  skip calling `ensure_fresh` altogether; `ensure_fresh` always has
  side effects on disk when it refreshes.

## Testability seam

`fetch_models` reads a single env var to locate the API:

```rust
fn models_api_url() -> String {
    std::env::var("MARS_MODELS_API_URL")
        .unwrap_or_else(|_| "https://models.dev/api.json".to_string())
}
```

Tests (both phase-2 unit tests and phase-5 integration tests) start an
in-process `httpmock` server and point `MARS_MODELS_API_URL` at it.
No trait, no dual-API split, no `ensure_fresh_with` variant — one
function, one seam, used by both test tiers. The env-URL approach is
the only seam that works for phase-5's multi-process concurrency test
(which drives real `mars` binary subprocesses).

`fetch_models` also sets an explicit request timeout (see `ureq::Agent`
configuration) so `sync` can't deadlock on a hung catalog endpoint while
holding `sync.lock`. Recommended timeout: 15s for connect, 15s for read.
