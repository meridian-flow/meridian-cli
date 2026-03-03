# Tech Debt

Code and test cleanup. Last verified: 2026-03-03.

## Open

| ID | Summary | Priority | Status | Tracking |
|----|---------|----------|--------|----------|
| TD-7 | Deduplicate launch resolution/assembly across `launch.py` and spawn prepare path | High | Open | `plans/unify-harness-launch.md` |
| TD-8 | Complete primary CLI redesign (`meridian` root entry + real `--continue`) | High | Open | `plans/primary-cli-redesign.md` |
| TD-9 | Finish space-plumbing follow-up cleanup (report-path semantics, artifact scoping) | Medium | Open | `plans/space-plumbing-fix.md` |
| TD-10 | Align bundled skill naming/content strategy with shipped bundle (`meridian-spawn-agent` vs `meridian-run`) | Medium | Open | `plans/bundled-skills.md` |
| TD-11 | Validate/polish Claude native-agent passthrough edge cases and doc/code alignment | Medium | Open | `plans/native-agent-passthrough.md` |

## Archived (2026-03-03 backlog execution batch)

| ID | Summary | Status | Resolution Commit(s) |
|----|---------|--------|----------------------|
| TD-1 | Unify spawn execution lifecycle paths | Closed | `deaee4c` |
| TD-2 | Consolidate space resolution and `@name` loading | Closed | `aeb01c9` |
| TD-3 | Merge warning/normalization utilities | Closed | `ae61da7` |
| TD-4 | Consolidate CLI spawn plumbing tests | Closed | `8b33a8a` |
| TD-5 | Remove overlapping streaming tests | Closed | `88a3429` |
| TD-6 | Centralize subprocess test helpers | Closed | `6d6fcf0` |

## Archive Reference

- Full batch archive: `backlog/archive/2026-03-03-backlog-execution.md`
- Execution anomalies/workarounds: `plans/backlog-execution-anomalies.md`
