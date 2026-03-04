# Tech Debt

Code and test cleanup. Last verified: 2026-03-04.

## Open

| ID | Summary | Priority | Status | Tracking |
|----|---------|----------|--------|----------|
| TD-9 | Finish space-plumbing follow-up cleanup (report-path semantics, artifact scoping) | Medium | In-progress (Steps 0+2 done, Steps 1+3 remain) | `plans/space-plumbing-fix.md` |

Note: Steps 0 (thread space_id explicitly) and 2 (thread space into reference loading) are complete. Remaining work is Step 1 (report_path semantics) and Step 3 (space-aware artifact keys). File paths are now `_spawn_*.py` (not `_run_*.py`).

## Archived (2026-03-04 cleanup batch)

| ID | Summary | Status | Resolution Commit(s) |
|----|---------|--------|----------------------|
| TD-7 | Deduplicate launch resolution/assembly across `launch.py` and spawn prepare path | Closed | `bda59aa` |
| TD-10 | Align bundled skill content strategy (naming, materialization, skill content) | Closed | `b1d859d`, `77cffef`, `d434984`, `a7ccecf` |
| TD-11 | Validate/polish Claude native-agent passthrough edge cases and doc/code alignment | Closed | `e444f60`, `9f39e24`, `a28143b` |
| TD-12 | Remove harness-id string branching for reference loading mode | Closed | `87af9f0` |
| TD-13 | Remove Claude-specific allowed-tools merge from generic strategy builder | Closed | `87af9f0` |
| TD-14 | Unify primary launch env wiring with adapter env/MCP env flow | Closed | `bda59aa` |
| TD-15 | Replace hardcoded primary harness override allowlist with registry-derived validation | Closed | `87af9f0` |
| TD-16 | Replace `_build_interactive_command` with adapter-delegated command building | Closed | `bda59aa` |

## Archived (2026-03-03 backlog execution batch)

| ID | Summary | Status | Resolution Commit(s) |
|----|---------|--------|----------------------|
| TD-8 | Complete primary CLI redesign (`meridian` root entry + real `--continue`) | Closed | `ec5f806`, `76d9678`, `248b97d`, `2950a8b`, `f533a23` |
| TD-1 | Unify spawn execution lifecycle paths | Closed | `deaee4c` |
| TD-2 | Consolidate space resolution and `@name` loading | Closed | `aeb01c9` |
| TD-3 | Merge warning/normalization utilities | Closed | `ae61da7` |
| TD-4 | Consolidate CLI spawn plumbing tests | Closed | `8b33a8a` |
| TD-5 | Remove overlapping streaming tests | Closed | `88a3429` |
| TD-6 | Centralize subprocess test helpers | Closed | `6d6fcf0` |

## Archive Reference

- Full batch archive: `backlog/archive/2026-03-03-backlog-execution.md`
- Execution anomalies/workarounds: `plans/backlog-execution-anomalies.md`
