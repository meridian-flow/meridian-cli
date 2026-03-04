# Tech Debt

Code and test cleanup. Last verified: 2026-03-03.

## Open

| ID | Summary | Priority | Status | Tracking |
|----|---------|----------|--------|----------|
| TD-7 | Deduplicate launch resolution/assembly across `launch.py` and spawn prepare path | High | In-progress (Step 0 done, Steps 1-2 remain) | `plans/unify-harness-launch.md` |
| TD-9 | Finish space-plumbing follow-up cleanup (report-path semantics, artifact scoping) | Medium | In-progress (Steps 0+2 done, Steps 1+3 remain) | `plans/space-plumbing-fix.md` |
| TD-10 | Align bundled skill content strategy (naming is correct: `meridian-spawn-agent`) | Medium | In-progress (skills shipped, content not fully rewritten) | `plans/bundled-skills.md` |
| TD-11 | Validate/polish Claude native-agent passthrough edge cases and doc/code alignment | Low | Near-complete (feature done, doc/edge-case polish only) | `plans/native-agent-passthrough.md` |
| TD-12 | Remove harness-id string branching for reference loading mode (`_spawn_prepare.py` uses `str(harness.id) == "codex"`) in favor of adapter-declared behavior | Medium | Open | `plans/unify-harness-launch.md` |
| TD-13 | Remove Claude-specific allowed-tools merge from generic strategy builder (`_strategies.py`) and move harness-specific merge logic behind adapter hooks | Medium | Open | `plans/unify-harness-launch.md` |
| TD-14 | Unify primary launch env wiring with adapter env/MCP env flow (`launch.py` vs `exec/spawn.py`) so primary/child harness setup is assembled from one pipeline | High | Open | `plans/unify-harness-launch.md` |
| TD-15 | Replace hardcoded primary harness override allowlist in `launch.py:_resolve_harness()` with registry-derived validation to avoid dual updates when harnesses change | Medium | Open | `plans/unify-harness-launch.md` |

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
