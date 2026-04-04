# Mars Refactor Design: Overview

Refactor mars-agents for extensibility, then design extension points for capability packages (permissions, tools, MCP, hooks).

## Problem

Mars syncs agent profiles and skills from git/local sources into `.agents/` directories. It works well for content sync but can't evolve toward capability packages because the architecture has structural bottlenecks:

1. `sync::execute` is a 240-line function that owns the entire pipeline — 17 steps with hidden phase ordering and post-hoc `_self` injection that breaks the plan after it's built
2. `_self` is a string sentinel (`"_self"`) leaking across config, sync, lock, and plan instead of being a typed source kind
3. `DependencyEntry` is overloaded for consumer install intent and published manifest exports — the resolver silently compensates by skipping manifest deps without URLs
4. `mars link` duplicates reconciliation logic separate from sync
5. Diagnostics bypass the structured output layer — library code writes directly to stderr

These blockers make it impractical to add new item kinds (permissions, tools, MCP configs) because each new kind would need to be threaded through the monolithic pipeline, cope with string sentinel checks, and handle link separately.

## Architecture: Before and After

### Before (Current)

```
mars.toml → Config → resolve → TargetState → diff → SyncPlan → apply → lock
                                                          ↑
                                        inject_self_items (mutates plan after creation)
                                        
mars link → scan_link_target → merge_and_link (separate reconciliation)
```

**Problems**: Single execute() function, _self handled as afterthought, link is separate pipeline, only Agent/Skill item kinds hardcoded in discovery.

### After (Target)

```
mars.toml → Config → resolve → discover (all kinds) → TargetState → diff → SyncPlan → apply → lock
                        ↑                                                       ↓
                   LocalPackage                                          per-kind materializers
                   (first-class)                                               ↓
                                                                    reconcile (shared layer)
                                                                         ↓
                                                              runtime adapters (.claude, etc.)
```

**Key changes**:
- Pipeline decomposed into typed phases with explicit handoff structs
- `_self`/local-package is a first-class `SourceOrigin::Local` that participates in discovery/diff/plan like any other source
- DependencyEntry split into `InstallDep` (consumer) and `ManifestDep` (package export)
- Shared reconciliation layer used by both sync apply and link
- ItemKind extensible for new item types
- Per-kind materializers handle different apply semantics (file copy vs config merge)

## Subsystem Designs

| Subsystem | Doc | What It Covers |
|-----------|-----|----------------|
| [Pipeline decomposition](pipeline-decomposition.md) | Typed phases, _self as first-class, DependencyEntry split, shared reconciliation, structured diagnostics | Phase A — structural refactor |
| [Extension model](extension-model.md) | Generalized item kinds, per-kind materializers, runtime adapters, capability package schema | Phase B — new capabilities |

## Design Decisions

Recorded in [decisions.md](../decisions.md) as they were made during design.

## Phase Ordering

**Phase A must complete before Phase B.** The extension model builds on the decomposed pipeline — adding new item kinds to a monolithic `execute()` would reproduce the structural problems. Within Phase A, the ordering is:

1. **A1: Typed pipeline phases** — decompose `sync::execute` into explicit phase functions with handoff structs. This is the foundation everything else touches.
2. **A2: First-class LocalPackage** — make `_self` a typed `SourceOrigin::Local`, integrate into discovery/diff/plan instead of post-hoc injection. Depends on A1 (pipeline decomposition makes this clean).
3. **A3: DependencyEntry split** — separate `InstallDep` from `ManifestDep`, fail loudly on unsupported manifest shapes. Can parallel with A2.
4. **A4: Shared reconciliation** — extract reconciliation layer from sync apply and link. Can parallel with A2/A3.
5. **A5: Structured diagnostics** — return `Diagnostic` values from library layers. Can run last (lowest risk, widest touch).

Phase B items can start once A1 is done:

6. **B1: Generalized item kinds** — extensible `ItemKind`, per-kind discovery, per-kind materializers
7. **B2: Permission sync** — declarative permission policies materialized into runtime configs
8. **B3: Tool distribution** — packaged tool specs with per-runtime materialization
9. **B4: MCP integration** — package-managed MCP server registrations
10. **B5: Hook distribution** — lifecycle hooks (lowest priority)

## Constraints

- **Backwards compatibility**: mars.toml and mars.lock formats must either stay compatible or have clean migration. Lock file has `version: 1` field for schema evolution.
- **Crash safety**: All writes must remain atomic (tmp+rename). No partial state on crash.
- **No runtime dependencies**: Mars is build-time/setup-time. Capability definitions are declarative, not executable.
- **Single binary**: No dynamic loading. New item kinds are compiled in.
- **~5k LOC budget**: The refactor should not significantly increase total LOC. Prefer restructuring over adding.
