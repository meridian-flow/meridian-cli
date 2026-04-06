# Phase 5: Mars-side Tests & Smoke

**Repo:** mars-agents
**Depends on:** Phases 3 and 4
**Est. size:** smoke test fixture + ~150 LoC of integration tests

## Goal

Cover end-to-end behaviors that unit tests alone can't hit: CLI flag
plumbing, env precedence, concurrency across real processes, and the
"freshly added alias → spawn works" loop.

## Files

- `tests/` or `tests/integration/` — mars-agents already has integration
  harnesses via `assert_cmd`. Add a new file, e.g.
  `tests/models_cache_ttl.rs`.
- `tests/smoke/` or README smoke section — mars-agents follows the
  "smoke tests as markdown guides" convention from meridian-channel's
  CLAUDE.md; if mars-agents has a similar convention, add a markdown file
  describing manual repro steps; otherwise fold the steps into
  `tests/integration`.

## Integration Scenarios

All scenarios use `tempfile::tempdir` for the project root, write a
minimal `mars.toml`, optionally pre-populate `.mars/models-cache.json`,
and invoke the real `mars` binary via `assert_cmd`.

Because these scenarios should not hit the network, they use the same
testability seam introduced in phase 2: `fetch_models` reads
`MARS_MODELS_API_URL` and falls back to `https://models.dev/api.json`.
Integration tests start an `httpmock::MockServer` and set the env var
on every spawned `mars` subprocess via `assert_cmd::Command::env`.

Both `httpmock` and `serial_test` are already added to
`[dev-dependencies]` by phase 2. This phase only consumes them.

### Scenario A: Cold cache refreshes on `models list`

1. Empty `.mars/` (no cache file).
2. Run `mars models list` pointing at a stub models.dev server returning
   a small valid catalog.
3. Assert exit 0, cache file exists with non-empty models and a
   `fetched_at` timestamp.

### Scenario B: Fresh cache skips fetch

1. Write a cache with `fetched_at = now()`.
2. Run `mars models list` with the stub server returning 500.
3. Assert exit 0 (stale fallback not triggered because cache is fresh).

### Scenario C: Stale cache falls back on fetch failure

1. Write a cache with non-empty models and `fetched_at = now() - 25h`.
2. Stub server returns 500.
3. Run `mars models list`.
4. Assert exit 0, stderr contains "stale models cache", cache file
   unchanged.

### Scenario D: Empty cache + `MARS_OFFLINE` errors cleanly

1. Empty `.mars/`.
2. Run `MARS_OFFLINE=1 mars models resolve <some-alias>`.
3. Assert exit 1, stderr mentions `mars models refresh` and
   `MARS_OFFLINE`.

### Scenario E: `--no-refresh-models` equivalent to env

1. Same as D but use the flag instead of the env var.

### Scenario F: `mars sync` populates the cache

1. Empty `.mars/` with a minimal package dep that ships an alias.
2. Run `mars sync --force`.
3. Assert cache file now exists and covers the required models.

### Scenario G: `MARS_OFFLINE mars sync` succeeds without cache

1. Empty `.mars/`.
2. Run `MARS_OFFLINE=1 mars sync --force`.
3. Assert exit 0, cache file still absent, diag warning about
   "models-cache-refresh" present.

### Scenario H: Concurrent spawns fetch exactly once

1. Empty `.mars/`. Start a stub HTTP server that sleeps 500ms before
   responding and counts hits.
2. Spawn N=4 `mars models list` subprocesses in parallel.
3. Wait for all to finish.
4. Assert: all exited 0, all see the same catalog, stub server saw
   exactly **1** request.

This is the flock's integration test — the thing unit tests within a
single process can approximate but not prove.

### Scenario I: TTL = 0 always refreshes

1. Write `mars.toml` with `[settings] models_cache_ttl_hours = 0`.
2. Write a fresh cache (`fetched_at = now()`).
3. Run `mars models list`.
4. Assert the stub server was hit.

## Verification

- `cargo test --package mars-agents --test models_cache_ttl`
- `cargo clippy --all-targets -- -D warnings`
- `cargo fmt --check`

## Guard Rails

- Tests must never hit the real network. Any scenario that can't be
  stubbed is not worth running in CI. If you need a "live" probe, gate
  it behind `#[ignore]`.
- Do not introduce a new global singleton for the stub fetcher. Use the
  env-URL seam or pass-through.
- Keep scenario H's N small (4 is plenty) — the test is correctness, not
  throughput.
