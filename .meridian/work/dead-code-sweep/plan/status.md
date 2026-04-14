# Plan Status Seed — dead-code sweep

| Phase | Round | State | Depends on | Notes |
|---|---|---|---|---|
| `Phase 1 — auth-lifecycle-surface` | `Round 1` | `pending` |  | Foundational deletion phase. Removes auth and lifecycle cancel surface first. |
| `Phase 2 — state-schema-cleanup` | `Round 2` | `pending` | `Phase 1` | Owns dead schema/state ballast and stale lifecycle terminology. |
| `Phase 3 — module-compat-cleanup` | `Round 2` | `pending` | `Phase 1` | Safe parallel lane for wrappers, import redirects, and dead modules. |
| `Phase 4 — install-baseline-verification` | `Round 3` | `pending` | `Phase 2`, `Phase 3` | Closure gate before smoke. |
| `Phase 5 — smoke-retest-survivors` | `Round 4` | `pending` | `Phase 4` | Evidence-only smoke rerun and survivor capture. |

No prior phase is preserved. This work item starts with the full plan pending.
