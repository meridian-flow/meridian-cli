# Task: Accuracy Review of docs/ Spawn-Lifecycle Updates

The tech-writer just updated user-facing documentation to reflect the spawn-lifecycle / reaper refactor (commits f6d9f20..27d5237, issue #14). Verify factual accuracy against source code. Not a prose review.

## Files updated

- `docs/commands.md`
- `docs/troubleshooting.md`
- `docs/mcp-tools.md`
- `docs/_internal/ARCHITECTURE.md`

## Source of truth

- `src/meridian/lib/core/spawn_lifecycle.py`
- `src/meridian/lib/state/spawn_store.py`
- `src/meridian/lib/state/reaper.py`
- `src/meridian/lib/launch/runner.py`

## What to flag

1. **Wrong status set** — every enumeration of spawn statuses must include `finalizing`; order should be `queued, running, finalizing, succeeded, failed, cancelled`.
2. **Wrong timing values** — 120s heartbeat, 15s startup grace, 30s PID-reuse margin, 30s heartbeat tick. Flag any that disagree with source.
3. **Authority rule clarity** — troubleshooting / architecture should explain (in user terms) that a runner's terminal report can correct a reaper's orphan stamp. If it sounds like orphan stamps are final, flag it.
4. **`orphan_finalization` vs `orphan_run`** — both should be mentioned in troubleshooting; the distinction (crashed during execution vs crashed during drain/report) should be accurate.
5. **MCP tool responses** — `docs/mcp-tools.md` should reflect that `finalizing` can appear in status fields and MCP consumers should treat it like `running` for polling.
6. **ARCHITECTURE.md internals** — event-sourcing example and launch-lifecycle diagram should match actual in-tree behavior (event types, `origin` field on finalize events, `mark_finalizing` CAS).
7. **Stale content** — any lingering pre-refactor enumerations or descriptions.

## Output

Structured findings per file: quote, what's wrong, what source says. Group by file. If clean, say so. Do not edit.
