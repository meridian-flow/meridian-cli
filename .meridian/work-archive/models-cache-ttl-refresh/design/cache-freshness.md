# Cache Freshness

## Definition

The models cache is **fresh** iff *all* of the following hold:

1. `.mars/models-cache.json` exists and parses as a valid `ModelsCache`.
2. Its `models` array is **non-empty**.
3. It has a non-empty `fetched_at` field that parses as a timestamp.
4. `now_unix() - fetched_at_unix() < ttl_hours * 3600`.

Any other state — missing file, unparseable JSON, missing `fetched_at`,
unparseable `fetched_at`, negative delta (clock skew), delta ≥ TTL,
**or `models=[]`** — counts as **stale**.

The empty-models rule exists specifically to close the "fresh but
empty" loophole: a file containing `{"models":[], "fetched_at":"..."}`
could otherwise pass every other freshness check and return nothing.
Instead it's stale (so `Auto` re-fetches) and unusable (so `Offline`
errors with `ModelCacheUnavailable`).

A TTL of `0` is a special case: every read is stale, every `Auto` call
refreshes. Useful for tests and CI.

## `fetched_at` Format

The existing `now_iso()` helper in `src/cli/models.rs` is mis-named — it
writes a bare Unix-seconds integer as a string (e.g. `"1712345678"`), not an
ISO-8601 timestamp. The name is preserved for now, but the TTL check must
parse **either**:

- **Unix seconds string** (current format, written by `now_iso()` today).
  Parse as `u64`.
- **ISO-8601 UTC** (reserved for future use) — skip for this work item;
  document that the format may evolve and callers should not depend on it
  being human-readable.

Going forward, `ensure_fresh` writes `fetched_at` using the same
Unix-seconds format the current `now_iso()` produces. The rename to
something honest (`now_unix_secs()`) is a drive-by cleanup — the existing
mis-name is a Chesterton's fence worth removing because the string
"`now_iso`" actively misleads any future reader.

## Tolerant Read

`ensure_fresh` uses a `read_cache_tolerant` wrapper that converts any
read or parse failure into an empty `ModelsCache { models: vec![],
fetched_at: None }`. This is the single implementation of the
"degraded input is stale and unusable" rule. The strict `read_cache`
stays available for code paths that must fail loudly (e.g. refresh
writes then reads back to verify round-trip).

## Degenerate Inputs

| On-disk state                              | Classified as |
|--------------------------------------------|---------------|
| File missing                               | Stale + unusable |
| Corrupt / truncated JSON                   | Stale + unusable (logged `debug!`) |
| Unexpected schema (wrong types)            | Stale + unusable (logged `debug!`) |
| Valid JSON, `models = []`, `fetched_at` present | Stale + unusable |
| Valid JSON, `models = []`, `fetched_at` absent  | Stale + unusable |
| Valid JSON, non-empty `models`, `fetched_at = None` | Stale + usable (can degrade on fetch failure) |
| Valid JSON, non-empty `models`, `fetched_at` unparseable | Stale + usable |
| Valid JSON, non-empty `models`, `fetched_at` in future | Stale + usable (logged `warn!`) |
| Valid JSON, non-empty `models`, `fetched_at` older than TTL | Stale + usable |
| Valid JSON, non-empty `models`, `fetched_at` within TTL | **Fresh** |

**Usable vs stale** matters for the offline-fallback path: a stale-but-
usable cache can degrade gracefully when a fetch fails; an unusable
cache cannot.

## No Migration

Existing `.mars/models-cache.json` files without `fetched_at` are *not*
rewritten on startup. They're silently refreshed on next `Auto` call. This
keeps the upgrade path zero-friction and avoids a one-shot migration routine.

## Why Not Mtime?

File mtime would work but is brittle: `cp -a`, `git checkout`, and container
image bakes all preserve stale mtimes or reset fresh ones. Embedding
`fetched_at` inside the JSON is explicit, portable, and already half-built
(the field exists on `ModelsCache`).
