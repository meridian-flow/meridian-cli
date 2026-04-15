# fs/ Mirror Redesign

## Goal

Restructure `$MERIDIAN_FS_DIR` (.meridian/fs/) from an ad-hoc collection of research docs into a structured codebase mirror organized by domain. Make fs/ mirror updates a required part of the implementation workflow.

## fs/ Convention

Domain-based directory structure mirroring the conceptual architecture:

```
fs/
  overview.md                    # system-level: what meridian is, how subsystems connect
  harness/
    overview.md                  # adapter protocol, capabilities matrix, command assembly
    claude.md                    # Claude-specific
    codex.md                     # Codex-specific
    opencode.md                  # OpenCode-specific
    direct.md                    # Direct adapter: in-process API
  state/
    overview.md                  # storage architecture: JSONL events, crash tolerance
    spawns.md                    # spawn store, event model, terminal merging, reaper
    sessions.md                  # session store, locking, leases, compaction
    work-items.md                # work store, rename crash safety, archive lifecycle
  catalog/
    overview.md                  # model resolution pipeline, agent/skill loading
    models.md                    # mars resolution → pattern fallback, models.dev cache
    agents-and-skills.md         # profile loading, skill composition, default agent policy
  launch/
    overview.md                  # spawn lifecycle: prepare → resolve → process → finalize
    process.md                   # subprocess management, signals, timeouts, heartbeat
    prompt.md                    # prompt assembly, injection mitigation, references
    reports.md                   # report creation, auto-extraction fallback chain
  config/
    overview.md                  # precedence chain, settings model, runtime overrides
  ops/
    overview.md                  # manifest architecture, CLI/MCP shared surface
  mars/
    overview.md                  # mars integration: binary resolution, init/link, sync
    feature-gaps.md              # (migrated from existing)
```

No research/ folder in fs/. Research lives in $MERIDIAN_WORK_DIR during work items. Lasting findings get synthesized into the relevant domain doc.

## Agent Profile Updates (in meridian-dev-workflow/ source submodule)

### impl-orchestrator
- Make fs/ mirror update a **required post-implementation step** (not optional background work)
- After all phases pass, spawn code-documenter to update fs/ docs for touched subsystems
- This is a workflow change, not just a suggestion

### code-documenter
- Bake in the fs/ directory convention so it knows the structure to maintain
- Currently just says "maintain the mirror" with no defined shape
- Should know the domain layout and what goes in each domain

### dev-artifacts skill
- Add the fs/ convention to the artifact placement spec
- Clarify: fs/ = agent-facing codebase mirror, docs/ = user-facing documentation
- No research/ in fs/ — research is work-scoped

## Existing Doc Migration
- model-catalog-and-resolution.md → synthesize into fs/catalog/models.md
- codex-session-management.md → synthesize into fs/harness/codex.md
- mars-agents-feature-gaps.md → move to fs/mars/feature-gaps.md
- agent-skill-design-principles.md → does NOT go in fs/ (it's design guidance, not a codebase mirror; lives in the skill source)
- research/ subfolder → contents archived or dropped

## Key Principles
- fs/ is for agents, not humans. Compressed, navigable, domain-scoped.
- Each doc covers: what exists, how it works, why it's that way.
- Domain-based, not source-path-based. fs/harness/ not fs/lib/harness/.
- docs/ is for humans. CLI reference, getting started, configuration.
