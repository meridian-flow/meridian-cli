# Mars Refactor Design: Overview

Refactor mars-agents for extensibility, then extend with capability packages, model catalog integration, soul files, harness-specific variants, and managed link targets.

## Problem

Mars syncs agent profiles and skills from git/local sources into `.agents/` directories. It works well for content sync but can't evolve toward capability packages or broader ecosystem management because the architecture has structural bottlenecks:

1. `sync::execute` is a 240-line function that owns the entire pipeline — 17 steps with hidden phase ordering and post-hoc `_self` injection that breaks the plan after it's built
2. `_self` is a string sentinel (`"_self"`) leaking across config, sync, lock, and plan instead of being a typed source kind
3. `DependencyEntry` is overloaded for consumer install intent and published manifest exports — the resolver silently compensates by skipping manifest deps without URLs
4. `mars link` duplicates reconciliation logic separate from sync
5. Diagnostics bypass the structured output layer — library code writes directly to stderr

Additionally, new requirements have emerged since the initial design:

6. **Model catalog + routing** is being implemented independently (issue #7) — mars owns `[models]` config and cache, but the pipeline must be aware of model metadata as a non-item artifact
7. **Soul files** (`.agents/soul/<alias>.md`) need to be synced like content items — per-model system prompt addons
8. **Harness-specific variants** (issue #6) — packages can ship different versions of agents/skills optimized for different harnesses, resolved at sync time
9. **Link reframing** — 'link' no longer means symlink; it means 'mars owns and manages this target directory', keeping it in sync with `.agents/` plus harness-specific content

## Architecture: Before and After

### Before (Current)

```
mars.toml → Config → resolve → TargetState → diff → SyncPlan → apply → lock
                                                          ↑
                                        inject_self_items (mutates plan after creation)
                                        
mars link → scan_link_target → merge_and_link (separate reconciliation)
models.rs → fetch/cache (standalone, not integrated into pipeline)
```

**Problems**: Single execute() function, _self handled as afterthought, link is separate pipeline, only Agent/Skill item kinds hardcoded in discovery, no variant resolution, no managed target sync.

### After (Target)

```
mars.toml → Config → resolve → discover (all kinds + variants) → TargetState → diff → SyncPlan → apply → lock
               ↑                    ↑                                                       ↓
          [models]             LocalPackage                                          per-kind materializers
          (routing)            (first-class)                                               ↓
               ↓                                                                  reconcile (shared layer)
        models cache                                                                     ↓
        (.agents/)                                                            managed targets (.claude, etc.)
                                                                              ↑
                                                              runtime adapters (content sync + capability merge)
```

**Key changes**:
- Pipeline decomposed into typed phases with explicit handoff structs
- `_self`/local-package is a first-class `SourceOrigin::Local` that participates in discovery/diff/plan like any other source
- DependencyEntry split into `InstallDep` (consumer) and `ManifestDep` (package export)
- Shared reconciliation layer used by both sync apply and managed target sync
- ItemKind extensible for new item types including Soul files
- Per-kind materializers handle different apply semantics (file copy vs config merge)
- Harness-specific variant resolution during discovery
- Link reframed as "managed target sync" — mars owns target directories, not just symlinks
- Model catalog as a pipeline-adjacent artifact (cache refresh, not a sync item)

## Subsystem Designs

| Subsystem | Doc | What It Covers |
|-----------|-----|----------------|
| [Pipeline decomposition](pipeline-decomposition.md) | Typed phases, _self as first-class, DependencyEntry split, shared reconciliation, structured diagnostics | Phase A — structural refactor |
| [Extension model](extension-model.md) | Generalized item kinds, soul files, harness variants, managed targets, model catalog, per-kind materializers, runtime adapters, capability package schema | Phase B — new capabilities |

## Design Decisions

Recorded in [decisions.md](../decisions.md) as they were made during design.

## Phase Ordering

**Phase A must complete before Phase B.** The extension model builds on the decomposed pipeline — adding new item kinds to a monolithic `execute()` would reproduce the structural problems. Within Phase A, the ordering is:

1. **A1: Typed pipeline phases** — decompose `sync::execute` into explicit phase functions with handoff structs. This is the foundation everything else touches.
2. **A2: First-class LocalPackage** — make `_self` a typed `SourceOrigin::Local`, integrate into discovery/diff/plan instead of post-hoc injection. Depends on A1 (pipeline decomposition makes this clean).
3. **A3: DependencyEntry split** — separate `InstallDep` from `ManifestDep`, warn on unsupported manifest shapes. **Independent of A1** — lives at the config/manifest boundary and resolver. Can start immediately or parallel with A1/A2.
4. **A4: Shared reconciliation** — extract reconciliation layer from sync apply and link. Can parallel with A2/A3.
5. **A5: Structured diagnostics** — return `Diagnostic` values from library layers. Can run last (lowest risk, widest touch).

Phase B requires A1 (typed phases) and A2 (first-class LocalPackage). Phase B items are ordered by dependency:

6. **B1: Generalized item kinds + soul files** — extensible `ItemKind`, per-kind discovery (including `Soul` kind), per-kind materializers
7. **B2: Harness-specific variants** — variant resolution in discovery, variant-aware target building. Depends on B1 (discovery conventions).
8. **B3: Managed target sync** — reframe link as "mars manages this target directory." Content sync + capability materialization into targets. Depends on B1 (new item kinds to materialize) and benefits from B2 (variant-resolved content for targets).
9. **B4: Model catalog integration** — `[models]` config handling, cache refresh lifecycle, model metadata in pipeline context. **Independent** — already being implemented (issue #7). Listed here for completeness; the pipeline just needs to carry the model config through.
10. **B5-B8: Capability items** — Permission sync, tool distribution, MCP integration, hook distribution (in priority order). Depend on B1 + B3.

## Constraints

- **Backwards compatibility**: mars.toml and mars.lock formats must either stay compatible or have clean migration. Lock file has `version: 1` field for schema evolution.
- **Crash safety**: All writes must remain atomic (tmp+rename). No partial state on crash.
- **No runtime dependencies**: Mars is build-time/setup-time. Capability definitions are declarative, not executable.
- **Single binary**: No dynamic loading. New item kinds are compiled in.
- **~5k LOC budget for Phase A**: The refactor should not significantly increase total LOC. Prefer restructuring over adding. Phase B will add net new code but should stay lean.
- **Model catalog is independent**: Issue #7 implementation proceeds in parallel. The design must accommodate it without blocking on it.
