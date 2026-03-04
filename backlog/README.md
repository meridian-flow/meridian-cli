# Backlog

Central backlog for cross-cutting work not tied to a single implementation plan. Last verified: 2026-03-03.

## Current Status

- Open items: `8` (tech-debt follow-up items)
- Archived from backlog-execution batch: `17`
- Previously closed (pre-batch): `2` (`BUG-2`, `BUG-7`)

## Archive

- Batch archive: `backlog/archive/2026-03-03-backlog-execution.md`
- Execution plan: `plans/backlog-execution.md`
- Execution anomalies/workarounds: `plans/backlog-execution-anomalies.md`

## Priority Index (Archived on 2026-03-03)

| ID | Item | File | Priority | Status |
|----|------|------|----------|--------|
| BUG-1 | Orphaned spawns stay "running" after kill | `bugs.md` | Medium | Closed (archived) |
| BUG-3 | Token usage always reports 0/0 | `bugs.md` | Medium | Closed (archived) |
| BUG-4 | Thin reports with pseudo-paths in files_touched | `bugs.md` | Medium | Closed (archived) |
| BUG-5 | Empty artifacts on spawn failure | `bugs.md` | Medium | Closed (archived) |
| BUG-6 | E2BIG on large-file spawn (Claude/OpenCode) | `bugs.md` | Medium | Closed (archived) |
| IMP-2 | Stderr verbosity tiers | `improvements.md` | High | Closed (archived) |
| IMP-1 | Failure summary fields | `improvements.md` | Medium | Closed (archived) |
| IMP-3 | Spawn cancel command | `improvements.md` | Medium | Closed (archived) |
| IMP-4 | Heartbeat/progress for long spawns | `improvements.md` | Medium | Closed (archived) |
| IMP-5 | Space-state rules at spawn entry | `improvements.md` | Medium | Closed (archived) |
| IMP-6 | Finish `run` → `spawn` terminology | `improvements.md` | Low | Closed (archived) |
| TD-1 | Unify spawn execution lifecycle paths | `tech-debt.md` | High | Closed (archived) |
| TD-2 | Consolidate space-resolution + @name loading | `tech-debt.md` | High | Closed (archived) |
| TD-3 | Merge warning/normalization utilities | `tech-debt.md` | Medium | Closed (archived) |
| TD-4 | Consolidate CLI spawn plumbing tests | `tech-debt.md` | Medium | Closed (archived) |
| TD-5 | Remove overlapping streaming tests | `tech-debt.md` | Medium | Closed (archived) |
| TD-6 | Centralize subprocess test helpers | `tech-debt.md` | Medium | Closed (archived) |

## Active Plans (items tracked there, not here)

- Primary CLI root entry + real continue flow (still pending) -> `plans/primary-cli-redesign.md`
- Launch pipeline deduplication follow-up (partial implementation exists) -> `plans/unify-harness-launch.md`
- Space-plumbing follow-up cleanup/revalidation -> `plans/space-plumbing-fix.md`
- Bundled skills naming/content alignment (`meridian-spawn-agent` vs proposed `meridian-run`) -> `plans/bundled-skills.md`
- Remote workspace viewer is requirements-only so far -> `plans/remote-workspace/requirements.md`

## Structure

- `bugs.md` — archived bug ledger + legacy closed bug entries
- `improvements.md` — archived improvement ledger
- `tech-debt.md` — archived tech-debt ledger
- `archive/2026-03-03-backlog-execution.md` — closed 17-item execution batch
- `_reference/migration-gotchas.md` — Historical notes from `run` → `spawn` migration (not actionable)
