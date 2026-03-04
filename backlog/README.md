# Backlog

Central backlog for cross-cutting work not tied to a single implementation plan. Last verified: 2026-03-04.

## Current Status

- Open items: `1` (TD-9: space-plumbing Steps 1+3)
- Archived from 2026-03-04 cleanup batch: `8` (TD-7, TD-10–TD-16)
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

## Priority Index (Archived on 2026-03-04)

| ID | Item | File | Priority | Status |
|----|------|------|----------|--------|
| TD-7 | Deduplicate launch resolution/assembly | `tech-debt.md` | High | Closed (archived) |
| TD-10 | Align bundled skill content strategy | `tech-debt.md` | Medium | Closed (archived) |
| TD-11 | Claude native-agent passthrough polish | `tech-debt.md` | Low | Closed (archived) |
| TD-12 | Remove harness-id string branching in spawn prepare | `tech-debt.md` | Medium | Closed (archived) |
| TD-13 | Remove Claude allowed-tools merge from strategy builder | `tech-debt.md` | Medium | Closed (archived) |
| TD-14 | Unify primary launch env wiring with adapter flow | `tech-debt.md` | High | Closed (archived) |
| TD-15 | Replace hardcoded primary harness allowlist | `tech-debt.md` | Medium | Closed (archived) |
| TD-16 | Replace `_build_interactive_command` with adapter delegation | `tech-debt.md` | High | Closed (archived) |

## Active Plans (items tracked there, not here)

- Space-plumbing follow-up cleanup/revalidation (Steps 1+3 remain) -> `plans/space-plumbing-fix.md`
- Remote workspace viewer is requirements-only so far -> `plans/remote-workspace/requirements.md`

## Structure

- `bugs.md` — archived bug ledger + legacy closed bug entries
- `improvements.md` — archived improvement ledger
- `tech-debt.md` — archived tech-debt ledger
- `archive/2026-03-03-backlog-execution.md` — closed 17-item execution batch
- `_reference/migration-gotchas.md` — Historical notes from `run` → `spawn` migration (not actionable)
