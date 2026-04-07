# Phase 6: Meridian-Channel Integration

**Repo:** meridian-channel
**Depends on:** Phase 5 (mars changes published / available locally)
**Est. size:** ~10 LoC + smoke doc

## Goal

Make sure meridian spawns benefit from `ensure_fresh(Auto)` without
introducing any new refresh logic on meridian's side. The only code
change is raising the `mars models resolve` / `mars models list`
subprocess timeout to accommodate a cold fetch.

## Files

- `src/meridian/lib/catalog/model_aliases.py`
  - Raise the `subprocess.run(..., timeout=10)` argument to `60` in
    `_run_mars_models_list` and `run_mars_models_resolve`.
  - Add a short comment explaining the generous timeout ("mars may
    perform a cold models.dev fetch inside `ensure_fresh(Auto)`").
- `tests/smoke/` — add a markdown file `models-cache-auto-refresh.md`
  describing the user-level scenario (see below).

## Implementation

```python
# Both _run_mars_models_list and run_mars_models_resolve raise the
# subprocess timeout from 10s → 60s. Mars itself caps the HTTP request
# at 15s connect + 15s read inside fetch_models, so a worst-case cold
# fetch fits comfortably; the extra headroom absorbs first-boot DNS
# and slow disks. The same number is used for both calls because both
# can trigger ensure_fresh(Auto) on a cold cache and we want symmetric
# behavior.
result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
```

No structural changes, no new functions, no new config knobs.

The `meridian doctor` subcommand already surfaces mars-binary problems;
if a timeout becomes common in practice, doctor is the place to add
proactive diagnostics. Out of scope for this phase.

## Smoke Test: `tests/smoke/models-cache-auto-refresh.md`

```markdown
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
(verify via `mars_dir/models-cache.json` mtime and/or by watching
network activity).
```

## Verification

- `uv run pyright` → 0 errors.
- `uv run ruff check .`
- Manual execution of the smoke scenarios above.

## Out of Scope

- Touching `src/meridian/lib/catalog/models.py`'s `_CACHE_TTL_SECONDS` /
  `models.json` discovery cache. That's a separate meridian-internal
  cache used by the `meridian models` UI, not by spawn-time resolution.
  Follow-up work item if/when needed.
- Adding meridian-side config for the mars TTL.
- Adding meridian CLI flags for `--no-refresh-models`. Users pass
  `MARS_OFFLINE=1` on the meridian invocation; the env var flows through
  `subprocess.run` to mars.
