# Sync Smoke Notes

Use this reference when validating `meridian sync`.

## What Sync Does

`meridian sync` manages external skills and agents from local paths or git repos. The core operations:

- **install** — clones/copies a source, materializes its skills into `.agents/skills/` and agents into `.agents/agents/`, creates symlinks under `.claude/skills/`, records the source in `.meridian/config.toml`, and writes a content-addressed lock entry to `.meridian/sync.lock`
- **update** — re-resolves each source, diffs against the lock hash, and re-materializes changed items
- **remove** — deletes managed files, symlinks, config entry, and lock entry for one source
- **status** — compares current materialized state against lock entries, reports in-sync or drift

Key implementation files: `src/meridian/lib/sync/engine.py` (orchestration), `lock.py` (lock file I/O), `cache.py` (source resolution and caching), `hash.py` (content hashing).

## Minimum Bar

- Run `tests/smoke/quick-sanity.md`
- Run `tests/smoke/sync/install-cycle.md`
- Verify both CLI output and the resulting `.agents/`, `.claude/`, `.meridian/config.toml`, and `.meridian/sync.lock` state

## When To Go Beyond the Local Round Trip

The local-path cycle is enough for many sync changes, but it does not exercise remote clone and fetch behavior.

If your change touches:

- remote source resolution (GitHub slug → clone → tree walk)
- lock semantics (hash comparison, conflict detection)
- `.claude/` symlink materialization
- repo-vs-path source branching in `resolve_source()`

also run one real remote-source install, not just a local-path round trip.

## Edge Cases to Watch

- **Missing source** — install from a path/repo that doesn't exist should fail cleanly, not crash
- **Already-installed source** — re-installing the same source name should either skip or reinstall, never duplicate
- **Orphaned files** — if a source previously installed 3 skills but now only has 2, the removed skill should be cleaned up on update
- **Lock drift** — manually editing files under `.agents/` should cause `status` to report drift, not silently pass

## What To Inspect

Do not stop at command success. Check:

- installed files under `.agents/`
- symlinks under `.claude/`
- configured source entries in `.meridian/config.toml`
- commit and tree-hash data in `.meridian/sync.lock`

The concrete command sequence lives in `tests/smoke/sync/install-cycle.md`.
