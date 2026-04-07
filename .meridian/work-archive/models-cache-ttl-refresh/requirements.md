# Models Cache TTL Refresh

## Problem

`mars sync` writes `.mars/models-merged.json` (the merged alias config from
deps) but never touches `.mars/models-cache.json` (the API-fetched catalog of
actual model IDs). Concretely:

1. `meridian mars add <pkg>` registers a new source that ships model aliases.
2. `meridian mars sync --force` writes the new aliases into `models-merged.json`.
3. The user spawns an agent using one of the new aliases.
4. `mars models list`/`resolve` reads `models-cache.json`, finds no entry for
   the new provider's models, auto-resolve returns nothing, and the agent
   profile fails to resolve. The model effectively doesn't exist.

The cache is currently only refreshed by an explicit `mars models refresh`,
which the user has to remember to run. Pinned aliases also can rely on the
cache for harness detection (`HarnessSource::Unavailable` path in
`cli/models.rs`), so the issue isn't limited to auto-resolve.

## Goal

Make the models cache refresh automatically whenever it's needed and stale,
so the user never sees a "missing model" failure caused by an unrefreshed
cache. Cache freshness is governed by a TTL with a sensible default,
configurable via mars.toml.

## Requirements

### Cache freshness

- Add `models_cache_ttl_hours: u32` to mars.toml `[settings]`. Default `24`.
  Integer hours only — no duration string parsing.
- Cache is **fresh** if `models-cache.json` exists, has a `fetched_at`
  timestamp, and `(now - fetched_at) < ttl_hours * 3600`. Otherwise stale.
- A `0` TTL means "always refresh on read" (useful for testing/CI).

### Refresh policy

A new `models::ensure_fresh(mars_dir, ttl, mode)` helper centralizes the
refresh decision. Modes:

- **Auto** (default): refresh if missing or stale; no-op if fresh.
- **Force**: refresh unconditionally (current `mars models refresh` behavior).
- **Offline**: never hit the network; return whatever's on disk (may be empty
  or stale).

`ensure_fresh` is **file-locked** via `fcntl.flock` on
`.mars/.models-cache.lock` so concurrent spawns don't all fetch
simultaneously. First caller fetches; others wait, then read the freshly
written cache.

On fetch failure:

- If a stale-but-existing cache is on disk: warn loudly, return the stale
  cache (graceful offline degradation).
- If no cache exists at all: hard error with a clear message pointing the
  user at `mars models refresh` and the `MARS_OFFLINE` opt-out.

### Call sites

`ensure_fresh(Auto)` is wired into every place where the cache is needed:

1. **`mars sync`** — call before writing `models-merged.json` so the cache is
   guaranteed populated whenever new aliases land.
2. **`mars models list`** and **`mars models resolve`** — lazy refresh on read,
   replacing the current "no models cache" hint with an actual refresh.
3. **Meridian's agent-launch model resolution path** — same lazy refresh, so
   spawning never hits an empty cache even if the user skipped sync.

`mars models refresh` continues to exist as the explicit `Force` entry point.

### Offline opt-out

Two opt-outs, both honored everywhere `ensure_fresh` is called:

- `MARS_OFFLINE=1` environment variable.
- `--no-refresh-models` CLI flag on `mars sync`, `mars models list`,
  `mars models resolve`. (Not on `mars models refresh` — that's explicitly
  online by definition.)

When offline mode is active and the cache is missing entirely, the same
hard error fires with a clear message.

## Non-goals

- No background refresh daemon. TTL is checked lazily on read.
- No partial-refresh (per-provider). Always refresh the whole catalog.
- No caching of resolved aliases — only the raw catalog. Resolution stays
  pure and cheap.
- No retroactive migration of existing `.mars/models-cache.json` files.
  Existing caches without `fetched_at` are treated as infinitely stale and
  refreshed on next read.

## Scope

Two repos, one work item:

- **mars-agents** (primary): TTL config, `ensure_fresh` helper, file lock,
  call-site wiring in `cli/sync.rs`, `cli/models.rs`, offline flag, error
  messages.
- **meridian-channel**: wire `ensure_fresh(Auto)` into the agent-launch
  model resolution path so spawning a profile triggers the same refresh
  guarantee. Small follow-up after the mars-agents change lands.

## Success criteria

- `meridian mars add <pkg-with-new-aliases> && meridian mars sync --force`
  followed by spawning an agent using a new alias **just works**, no extra
  steps. The cache is refreshed automatically as part of sync.
- `meridian mars add` then immediately spawning an agent (skipping sync)
  also works — meridian's launch path triggers refresh too.
- `MARS_OFFLINE=1 meridian mars sync` never hits the network. If the cache
  is empty, sync still completes but spawning a new alias errors clearly.
- TTL is configurable in mars.toml; the default is 24 hours.
- Concurrent spawns starting simultaneously do not produce duplicate
  network fetches (file lock works).
