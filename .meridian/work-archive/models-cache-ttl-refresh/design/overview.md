# Models Cache TTL Refresh — Design Overview

## Problem

`mars sync` writes `.mars/models-merged.json` (the merged alias catalog from
dependency manifests) but never touches `.mars/models-cache.json` (the catalog
of real model IDs fetched from models.dev). A user who runs
`meridian mars add <pkg>` followed by `meridian mars sync` picks up new aliases
but not the models they point at; the next agent spawn sees an empty slot for
the new provider's models and fails with a confusing "missing model" error.

The only current remedy is for the user to remember `mars models refresh` —
an escape hatch, not a workflow.

## Goal

The models cache refreshes lazily and automatically whenever a consumer needs
it and the on-disk copy is stale. Freshness is governed by a TTL (default 24h,
configurable via `mars.toml`). Concurrency-safe, offline-tolerant, and
invisible when it's working.

## Shape of the Solution

One new helper — `models::ensure_fresh(mars_dir, ttl_hours, mode)` — owns the
entire refresh decision. Every consumer that touches the cache calls
`ensure_fresh` first; nothing decides freshness on its own. The helper:

1. Stats `models-cache.json`, parses `fetched_at`, compares against `ttl_hours`.
2. If fresh → returns the cache.
3. If stale and mode is `Auto` or `Force` → acquires an exclusive flock on
   `.mars/.models-cache.lock`, re-checks freshness under the lock (to avoid
   duplicate fetches across concurrent callers), fetches, writes, returns.
4. If stale and mode is `Offline` → returns whatever's on disk, or errors if
   empty.
5. On fetch failure with a stale-but-existing cache → warns and returns stale.
6. On fetch failure with no cache at all → hard error with actionable message.

The three policy knobs (`Auto` / `Force` / `Offline`) let each call site state
its intent without duplicating the freshness logic.

## Consumers (Call Sites)

Every place that previously called `read_cache` or assumed freshness switches
to `ensure_fresh(Auto)` (or `Force` in the case of `mars models refresh`).

| Call site                                | Mode    | Source of mode |
|------------------------------------------|---------|---------------|
| `mars sync` (before writing `models-merged.json`) | `Auto` | CLI flag + env |
| `mars models list`                       | `Auto`  | CLI flag + env |
| `mars models resolve <name>`             | `Auto`  | CLI flag + env |
| `mars models refresh`                    | `Force` | always |
| `meridian` agent-launch path (via `mars models resolve`) | `Auto` | mars-side |

Meridian never calls `ensure_fresh` directly — it already shells out to
`mars models resolve --json`, which runs `ensure_fresh(Auto)` on mars's side,
so the refresh guarantee propagates for free. The only meridian-side change is
raising the `mars models resolve` subprocess timeout to accommodate a cold
fetch (see `meridian-integration.md`).

## Configuration Surface

`mars.toml`:

```toml
[settings]
models_cache_ttl_hours = 24   # default; 0 = always refresh on read
```

Environment and flags:

- `MARS_OFFLINE=1` — coerce `ensure_fresh(Auto)` calls on this process
  to `Offline`. **Force mode is not affected** (see ensure-fresh.md
  §"MARS_OFFLINE Coercion") so `mars models refresh` still works
  inside an offline-flagged shell.
- `--no-refresh-models` — CLI flag on `mars sync`, `mars models list`,
  `mars models resolve`. Same effect as `MARS_OFFLINE=1` but scoped to one
  invocation. Not exposed on `mars models refresh` (that command is explicitly
  online by definition).

Precedence: `MARS_OFFLINE=1` or `--no-refresh-models` → `Offline`.
Otherwise → the mode the caller asked for.

## Reading Order

1. **overview.md** *(this doc)* — problem, shape, surface area.
2. **cache-freshness.md** — TTL, `fetched_at` format, staleness definition,
   migration of legacy caches.
3. **ensure-fresh.md** — the helper itself: signature, modes, fetch/lock/retry
   flow, error paths.
4. **concurrency.md** — file lock layout, double-check pattern, failure modes.
5. **call-sites.md** — how each consumer wires in, flag plumbing, what error
   messages look like.
6. **meridian-integration.md** — meridian-channel follow-up (subprocess
   timeout, env pass-through, no new refresh logic).
7. **configuration.md** — `mars.toml` schema addition, defaults, validation.

## Out of Scope

- Background refresh daemon / watcher.
- Per-provider partial refreshes.
- Persisted resolved-alias cache (resolution stays pure).
- Migrating existing `.mars/models-cache.json` — absent `fetched_at` is
  treated as infinitely stale and refreshed on next read.
