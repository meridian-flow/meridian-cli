# Plan Status — dead-code sweep

| Phase | Round | State | Depends on | Notes |
|---|---|---|---|---|
| `Phase 1 — auth-lifecycle-surface` | `Round 1` | `done` |  | Committed: da59ccd. Auth deleted, MCP cancel removed, D-25 added. |
| `Phase 2 — state-schema-cleanup` | `Round 2` | `done` | `Phase 1` | Committed: f0a89d5. All 8 items deleted/renamed. |
| `Phase 3 — module-compat-cleanup` | `Round 2` | `done` | `Phase 1` | Committed: 9da11ae. 5 orphaned modules + 2 shims deleted. |
| `Phase 4 — install-baseline-verification` | `Round 3` | `done` | `Phase 2`, `Phase 3` | ruff/pyright clean. Binary reinstalled v0.0.28. pytest has 1 pre-existing failure. |
| `Phase 5 — smoke-retest-survivors` | `Round 4` | `done` | `Phase 4` | Cancel lane: all PASS (p1830). AF_UNIX lane: all BLOCKED by app deps (p1831). |
