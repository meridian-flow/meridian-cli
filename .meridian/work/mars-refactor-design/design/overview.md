# Mars Refactor Design: Overview

Refactor mars-agents for extensibility, then extend with capability packages, model catalog integration, rule files, harness-specific variants, managed targets with cross-compilation, and a canonical `.mars/` content store.

## Problem

Mars syncs agent profiles and skills from git/local sources into `.agents/` directories. It works well for content sync but can't evolve toward capability packages or broader ecosystem management because the architecture has structural bottlenecks:

1. `sync::execute` is a 240-line function that owns the entire pipeline — 17 steps with hidden phase ordering and post-hoc `_self` injection that breaks the plan after it's built
2. `_self` is a string sentinel (`"_self"`) leaking across config, sync, lock, and plan instead of being a typed source kind
3. `DependencyEntry` is overloaded for consumer install intent and published manifest exports — the resolver silently compensates by skipping manifest deps without URLs
4. `mars link` duplicates reconciliation logic separate from sync
5. Diagnostics bypass the structured output layer — library code writes directly to stderr

Additionally, new requirements have emerged since the initial design:

6. **Model catalog + routing** is being implemented independently (issue #7) — mars owns `[models]` config and cache, but the pipeline must be aware of model metadata as a non-item artifact
7. **Rule files** (per-model and per-harness behavioral instructions) need to be synced like content items — operational rules like "you're on opus, think deeply" or "you're on codex, go straight to code"
8. **Harness-specific variants** (issue #6) — packages can ship different versions of agents/skills optimized for different harnesses, resolved at sync time
9. **`.mars/` as canonical content store** — `.agents/` can't serve as both source of truth and harness-specific target. If a harness reads `.agents/` directly, mars can't control what it sees. All target directories (`.agents/`, `.claude/`, `.codex/`, `.cursor/`) must be managed targets that mars materializes content into
10. **Runtime adapters as cross-compilers** — each harness has unique capabilities (Claude: hooks, settings.json; Cursor: .mdc rules with frontmatter; Codex: sandbox model). Adapters must map universal features to harness-native equivalents and support harness-specific extensions in the package schema

## Architecture: Before and After

### Before (Current)

```
mars.toml → Config → resolve → TargetState → diff → SyncPlan → apply → lock
                                                          ↑
                                        inject_self_items (mutates plan after creation)
                                        
mars link → scan_link_target → merge_and_link (separate reconciliation)
models.rs → fetch/cache (standalone, not integrated into pipeline)
```

**Problems**: Single execute() function, _self handled as afterthought, link is separate pipeline, only Agent/Skill item kinds hardcoded in discovery, no variant resolution, no managed target sync, .agents/ is both source of truth and target (can't do per-harness content).

### After (Target)

```
mars.toml → Config → resolve → discover (all kinds + variants) → TargetState → diff → SyncPlan
               ↑                    ↑                                                      ↓
          [models]             LocalPackage                                        apply → .mars/content/
          (routing)            (first-class)                                              (canonical store)
               ↓                                                                           ↓
        models cache                                                              sync all managed targets
        (.mars/)                                                                          ↓
                                                                    ┌──────────────────────┼──────────────┐
                                                                    ↓                      ↓              ↓
                                                              .agents/              .claude/        .cursor/
                                                              (default target)      (cross-compiled) (cross-compiled)
                                                                                         ↓
                                                                              runtime adapters
                                                                              (content copy + variant resolution
                                                                               + capability cross-compilation)
```

**Key changes**:
- **`.mars/content/` is the canonical store** — all resolved content lives here. Every target directory is a managed output, including `.agents/`
- Pipeline decomposed into typed phases with explicit handoff structs
- `_self`/local-package is a first-class `SourceOrigin::Local` that participates in discovery/diff/plan like any other source
- DependencyEntry split into `InstallDep` (consumer) and `ManifestDep` (package export)
- Shared reconciliation layer used by both content apply and managed target sync
- ItemKind extensible for new item types including Rule files
- Per-kind materializers handle different apply semantics (file copy vs config merge)
- Harness-specific variant resolution during discovery
- **All targets are managed** — `.agents/`, `.claude/`, `.cursor/` are all materialized from `.mars/content/` via copy
- **Runtime adapters are cross-compilers** — map universal package features to harness-native equivalents, emit diagnostics for unsupported features, honor harness-specific schema extensions
- Model catalog as a pipeline-adjacent artifact (cache refresh, not a sync item)
- **Copy, not symlink** for all target materialization — Windows compatibility, git friendliness, crash safety via tmp+rename

## Directory Layout

```
project/
  mars.toml                   # package config — committed
  mars.lock                   # lock file — committed
  .mars/                      # canonical content store — gitignored
    content/                  # all resolved package content
      agents/
      skills/
      rules/                  # shared rules
      rules/claude/           # harness-specific rules
      rules/opus.md           # per-model rules
      permissions/
      tools/
      mcp/
      hooks/
    models-cache.json         # model metadata cache — gitignored
  .agents/                    # managed target (default for generic harnesses)
  .claude/                    # managed target (Claude Code)
    rules/                    # rules materialized into Claude's native convention
  .codex/                     # managed target (Codex)
  .cursor/                    # managed target (Cursor)
```

`.mars/` is entirely gitignored — it's derived state regenerated from `mars.toml` + `mars.lock` + sources. `mars.toml` and `mars.lock` live at project root and are committed.

## Subsystem Designs

| Subsystem | Doc | What It Covers |
|-----------|-----|----------------|
| [Pipeline decomposition](pipeline-decomposition.md) | Typed phases, _self as first-class, DependencyEntry split, shared reconciliation, structured diagnostics | Phase A — structural refactor |
| [Extension model](extension-model.md) | Generalized item kinds, rule files, harness variants, .mars/ canonical store, copy-based target materialization, cross-compiler adapters, harness-specific schema extensions | Phase B — new capabilities |

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

6. **B1: Generalized item kinds + rule files** — extensible `ItemKind`, per-kind discovery (including `Rule` kind with per-harness and per-model subtypes), per-kind materializers.
7. **B2: Harness-specific variants** — variant resolution in discovery, variant-aware target building. Depends on B1 (discovery conventions).
8. **B3: `.mars/` canonical store + managed target sync** — `.mars/content/` becomes the canonical content store. All target directories (`.agents/`, `.claude/`, `.cursor/`) are managed outputs materialized via copy. Content sync + capability cross-compilation into targets. Depends on B1 (new item kinds to materialize) and benefits from B2 (variant-resolved content for targets). **This is the architectural pivot** — the pipeline's apply phase writes to `.mars/content/`, and a new target sync phase materializes to all configured targets.
9. **B4: Model catalog integration** — `[models]` config handling, cache refresh lifecycle, model metadata in pipeline context. **Independent** — already being implemented (issue #7). Cache location moves to `.mars/models-cache.json`.
10. **B5-B8: Capability items** — Permission sync, tool distribution, MCP integration, hook distribution (in priority order). Depend on B1 + B3.

## Constraints

- **Backwards compatibility**: mars.toml and mars.lock formats must either stay compatible or have clean migration. Lock file has `version: 1` field for schema evolution.
- **Crash safety**: All writes must remain atomic (tmp+rename). No partial state on crash. Copy-based materialization supports this naturally.
- **No runtime dependencies**: Mars is build-time/setup-time. Capability definitions are declarative, not executable.
- **Single binary**: No dynamic loading. New item kinds and adapters are compiled in.
- **~5k LOC budget for Phase A**: The refactor should not significantly increase total LOC. Prefer restructuring over adding. Phase B will add net new code but should stay lean.
- **Model catalog is independent**: Issue #7 implementation proceeds in parallel. The design must accommodate it without blocking on it.
- **Copy, not symlink for targets**: All content materialized to targets via copy (not symlink). Reasons: Windows symlinks need admin/developer mode, git symlink handling is finicky, copy + tmp+rename is simpler for crash safety, no broken links if `.mars/` is rebuilt.
- **`.mars/` is derived state**: Entirely gitignored, regenerated from mars.toml + mars.lock + sources. Only mars.toml and mars.lock are committed.
