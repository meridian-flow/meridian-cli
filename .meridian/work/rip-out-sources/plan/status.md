# Implementation Status

| Phase | Description | Status | Notes |
|-------|-------------|--------|-------|
| 1 | Atomic removal — install module, callers, CLI, tests | in-progress | Sequential: must go first |
| 2a | Clean state paths and gitignore | pending | Sequential: after Phase 1 |
| 2b | Remove provenance/bootstrap schema fields (~12 files) | pending | Sequential: after Phase 2a |
| 3 | Update ALL docs (README, INSTALL, AGENTS, config, smoke tests, meridian-base README) | pending | Parallel with Phase 4; includes AGENTS.md submodule/source-repo guidance |
| 4 | Improve error UX + `meridian mars` passthrough + doctor legacy-file warnings + required pyproject dep | pending | Parallel with Phase 3 (no AGENTS.md overlap) |
