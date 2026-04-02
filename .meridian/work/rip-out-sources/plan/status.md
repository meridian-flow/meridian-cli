# Implementation Status

| Phase | Description | Status | Notes |
|-------|-------------|--------|-------|
| 1 | Atomic removal — install module, callers, CLI, tests | done | Commit: 8cea261 |
| 2a | Clean state paths and gitignore | done | Commit: d0614b9 |
| 2b | Remove provenance/bootstrap schema fields (~12 files) | in-progress | Sequential: after Phase 2a |
| 3 | Update ALL docs (README, INSTALL, AGENTS, config, smoke tests, meridian-base README) | pending | Parallel with Phase 4 |
| 4 | Improve error UX + `meridian mars` passthrough + doctor legacy-file warnings + required pyproject dep | pending | Parallel with Phase 3 |
