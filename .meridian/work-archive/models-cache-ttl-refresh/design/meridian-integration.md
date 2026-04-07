# Meridian-Channel Integration

## The Happy Path Is Free

Meridian resolves models by shelling out to `mars models resolve <name>
--json` from `src/meridian/lib/catalog/model_aliases.py::run_mars_models_
resolve`. Once `mars models resolve` calls `ensure_fresh(Auto)` internally
(see `call-sites.md`), any spawn that triggers a model resolution also
triggers the refresh — no meridian-side refresh logic required.

This is deliberate: meridian stays a coordination layer and delegates
model-catalog concerns to mars. See project principle: *harness-agnostic,
files-as-authority, coordination-not-control*.

## What Must Change

### 1. Raise the `mars models resolve` subprocess timeout

Current code in `src/meridian/lib/catalog/model_aliases.py`:

```python
result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
```

A cold `ensure_fresh(Auto)` will make mars call models.dev, parse the
response, and write the cache. In benign conditions this takes ~1-3s; on
slow links or when models.dev is degraded it can run up against the
current 10-second budget.

Change: raise the timeout to `60` seconds for both
`_run_mars_models_list` and `run_mars_models_resolve`. These are
launch-critical paths so we accept the worst-case wait rather than fail a
spawn on a transient catalog fetch. Document the number next to the call
so future maintainers understand why it's generous.

The retry/catch logic that converts `subprocess.TimeoutExpired` to a clean
`RuntimeError` stays as-is; only the number changes.

### 2. Ensure `MARS_OFFLINE` flows through

`subprocess.run` inherits the parent process env by default, so
`MARS_OFFLINE=1 meridian spawn ...` reaches mars untouched. No code
change — just verify this in the smoke test (see plan).

### 3. Nothing else

- No new configuration surface on meridian.
- No new CLI flag (`--no-refresh-models` is mars's concern).
- No changes to `resolve_model`, `load_merged_aliases`, or the launch
  pipeline.
- No duplicate cache reads on meridian's side.

## Stale In-Process `_CACHE_TTL_SECONDS`?

`src/meridian/lib/catalog/models.py` has its own `_CACHE_TTL_SECONDS = 24
* 60 * 60` constant used by the `DiscoveredModel` flow that reads
models.dev directly for the `meridian models list` / catalog UI.

**Out of scope.** That is a separate, meridian-internal cache for a
different feature surface (models listing UI, not alias resolution). It
doesn't participate in spawn-time resolution and is not what the
requirements target. Note its existence but do not touch it.

If the discovery cache ever needs the same TTL treatment, it's a follow-up
work item — the design there would mirror this one (own `ensure_fresh`
for `meridian models`) but the two caches stay independent because they
live at different layers.

## Smoke Test Hooks

The plan includes a dedicated smoke scenario:

1. `meridian mars sync --force` to seed a cache.
2. `touch -t 200001010000 .mars/models-cache.json` *and* rewrite
   `fetched_at` to a very old Unix-secs value to simulate a stale cache.
3. `meridian spawn -a <agent-with-new-alias> -p noop` — verify the refresh
   happens inside the mars subprocess before resolution completes, and
   the spawn succeeds.
4. `MARS_OFFLINE=1 meridian spawn ...` with an empty cache — verify the
   spawn fails with a clean error that mentions `mars models refresh`.
