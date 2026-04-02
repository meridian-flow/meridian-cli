# Phase 4: Global Cache + Repair Fix

**Risk:** Medium — changes cache paths, affects all callers  
**Design doc:** [overview.md](../design/overview.md) §Global Cache Layout

## Scope

Wire `GlobalCache` through the full pipeline (replacing per-project `CacheDir`). Fix `mars repair` to handle corrupt lock files. Clean up any remaining git2 references.

## Steps

1. **Wire GlobalCache through pipeline**:
   - `sync/mod.rs`: `execute()` creates `GlobalCache::new()` instead of `CacheDir::new(root)`
   - `resolve/mod.rs`: `RealSourceProvider` takes `&GlobalCache` instead of `cache_dir: &Path`
   - `cli/outdated.rs`: use `GlobalCache` for version listing
   - Ensure per-project `.mars/cache/bases/` still works for three-way merge base content

2. **src/cli/repair.rs** — fix corrupt lock handling:
   - Wrap lock loading in a match: parse error → warn + use empty lock
   - Normal `mars sync` keeps erroring on corrupt lock ("run `mars repair`")

3. **Clean up any remaining git2 references**:
   - Search entire codebase for `git2::` — should be zero
   - Remove any git2-related test helpers (`create_test_repo`, `create_commit_with_file`, etc.)
   - Rewrite git.rs tests using `Command::new("git")` subprocess

4. **Add `mars cache` subcommand** (optional, nice to have):
   - `mars cache path` — print cache location
   - `mars cache clean` — remove all cached content

## Verification

- `cargo test` — all 24 integration tests + all unit tests pass
- `cargo clippy -- -D warnings` — clean
- Manual: `mars repair` with corrupt lock file recovers
- Manual: `mars add haowjy/meridian-base` works end-to-end with global cache
- Verify cache is at `~/.mars/cache/` not `.mars/cache/`

## Dependencies

Requires Phase 3 (fetch implementation).
