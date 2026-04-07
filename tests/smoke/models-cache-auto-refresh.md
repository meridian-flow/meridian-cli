# Smoke: Models Cache Auto-Refresh

Verifies that `meridian spawn` triggers mars's automatic models-cache
refresh when the cache is empty or stale, and that `MARS_OFFLINE=1`
produces a clean error instead of a hang.

## Setup

1. Pick a project with at least one mars-managed agent that uses an
   alias you know maps to a provider covered by the models cache (e.g.
   an Anthropic alias).
2. `rm -f .mars/models-cache.json` to force a cold state.

## Case 0: `meridian mars add` then immediate spawn

Background: `mars add` runs sync internally, so a fresh `mars add`
already triggers `ensure_fresh(Auto)` inside sync. This case verifies
the end-to-end story from requirements §Success Criteria #2.

```bash
rm -f .mars/models-cache.json
meridian mars add <pkg-shipping-new-aliases>
meridian spawn -a <agent-using-new-alias> -p "echo hello"
```

**Expected:** the `mars add` already populated the cache via sync, so
the spawn resolves instantly without another refresh.

## Case 1: Cold cache, spawn succeeds

```bash
meridian spawn -a <alias-agent> -p "echo hello"
```

**Expected:** spawn succeeds. `.mars/models-cache.json` now exists with a
recent `fetched_at`.

## Case 2: Stale cache, spawn still succeeds

```bash
# Hand-edit .mars/models-cache.json and set fetched_at to an old value,
# e.g. 1 (Unix epoch + 1 sec).
meridian spawn -a <alias-agent> -p "echo hello"
```

**Expected:** spawn succeeds, cache `fetched_at` is now recent.

## Case 3: Empty cache, offline, spawn fails cleanly

```bash
rm -f .mars/models-cache.json
MARS_OFFLINE=1 meridian spawn -a <alias-agent> -p "echo hello"
```

**Expected:** spawn fails fast with a clear error message mentioning
`mars models refresh` and `MARS_OFFLINE`. No 60-second hang.

## Case 4: Fresh cache, offline, spawn succeeds

```bash
# Ensure cache is fresh first.
mars models refresh
MARS_OFFLINE=1 meridian spawn -a <alias-agent> -p "echo hello"
```

**Expected:** spawn succeeds using the cached catalog; no network
traffic.

## Case 5: Concurrent spawns

```bash
rm -f .mars/models-cache.json
meridian spawn -a <alias-agent> -p "echo 1" &
meridian spawn -a <alias-agent> -p "echo 2" &
meridian spawn -a <alias-agent> -p "echo 3" &
wait
```

**Expected:** all three spawns succeed. Only one network fetch observed
(verify via `.mars/models-cache.json` mtime; check with
`stat .mars/models-cache.json`; and/or watch network activity).
