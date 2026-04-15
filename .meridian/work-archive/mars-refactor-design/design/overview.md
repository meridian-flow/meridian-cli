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

6. **Model catalog + routing** — mars owns `[models]` config and cache. Model aliases need two modes (pinned and auto-resolve), dependency-tree merge with same precedence as other config sections, builtin defaults, and integration with rule discovery (per-model rules are classified by matching filename against merged model aliases)
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
               ↑          ↑          ↑                                                      ↓
          [models]    merge models   model aliases                                 apply → .mars/
          (per-dep)   from dep tree  inform rule                                          (canonical store)
               ↓      + builtins     discovery                                              ↓
        models cache                                                              sync all managed targets
        (.mars/)                     LocalPackage                                           ↓
                                     (first-class)              ┌──────────────────────┼──────────────┐
                                                                ↓                      ↓              ↓
                                                          .agents/              .claude/        .cursor/
                                                          (default target)      (cross-compiled) (cross-compiled)
                                                                                     ↓
                                                                          runtime adapters
                                                                          (content copy + variant resolution
                                                                           + capability cross-compilation)
```

**Key changes**:
- **`.mars/` is the canonical store** — all resolved content lives here. Every target directory is a managed output, including `.agents/`
- Pipeline decomposed into typed phases with explicit handoff structs
- `_self`/local-package is a first-class `SourceOrigin::Local` that participates in discovery/diff/plan like any other source
- DependencyEntry split into `InstallDep` (consumer) and `ManifestDep` (package export)
- Shared reconciliation layer used by both content apply and managed target sync
- ItemKind extensible for new item types including Rule files
- Per-kind materializers handle different apply semantics (file copy vs config merge)
- Harness-specific variant resolution during discovery
- **All targets are managed** — `.agents/`, `.claude/`, `.cursor/` are all materialized from `.mars/` via copy
- **Runtime adapters are cross-compilers** — map universal package features to harness-native equivalents, emit diagnostics for unsupported features, honor harness-specific schema extensions
- **Model catalog integrated into pipeline** — `[models]` sections merge from dependency tree during `resolve_graph()` using same precedence as other config; auto-resolve aliases match against `.mars/models-cache.json`; merged aliases inform rule discovery (per-model rules)
- **Copy, not symlink** for all target materialization — Windows compatibility, git friendliness, crash safety via tmp+rename

## Directory Layout

```
project/
  mars.toml                   # package config — committed
  mars.lock                   # lock file — committed
  .mars/                      # canonical content store — should be gitignored
    agents/                   # resolved agents
    skills/                   # resolved skills
    cache/
      bases/                  # merge base cache (existing)
    models-cache.json         # model metadata cache
  .agents/                    # managed target (default for generic harnesses)
  .claude/                    # managed target (Claude Code)
  .codex/                     # managed target (Codex)
  .cursor/                    # managed target (Cursor)
```

`.mars/` is derived state — regenerated from `mars.toml` + `mars.lock` + sources. Should be gitignored (like `node_modules/`). Mars does NOT auto-edit `.gitignore` — users add `.mars/` themselves. `mars doctor` warns if `.mars/` is not ignored. `mars.toml` and `mars.lock` live at project root and are committed.

## Subsystem Designs

| Subsystem | Doc | What It Covers |
|-----------|-----|----------------|
| [Pipeline decomposition](pipeline-decomposition.md) | Typed phases, _self as first-class, DependencyEntry split, shared reconciliation, structured diagnostics | Phase A — structural refactor |
| [Extension model](extension-model.md) | Generalized item kinds, rule files, harness variants, .mars/ canonical store, copy-based target materialization, cross-compiler adapters, harness-specific schema extensions, model catalog with pinned/auto-resolve aliases and dependency-tree merge | Phase B — new capabilities |

## Design Decisions

Recorded in [decisions.md](../decisions.md) as they were made during design.

## Phase Ordering

**Phase A must complete before Phase B.** The extension model builds on the decomposed pipeline — adding new item kinds to a monolithic `execute()` would reproduce the structural problems. Within Phase A, the ordering is:

1. **A1: Typed pipeline phases** — decompose `sync::execute` into explicit phase functions with handoff structs. This is the foundation everything else touches.
2. **A2: First-class LocalPackage** — make `_self` a typed `SourceOrigin::Local`, integrate into discovery/diff/plan instead of post-hoc injection. Depends on A1 (pipeline decomposition makes this clean).
3. **A3: DependencyEntry split** — separate `InstallDep` from `ManifestDep`, warn on unsupported manifest shapes. **Independent of A1** — lives at the config/manifest boundary and resolver. Can start immediately or parallel with A1/A2.
4. **A4: Shared reconciliation** — extract reconciliation layer from sync apply and link. Can parallel with A2/A3.
5. **A5: Structured diagnostics** — return `Diagnostic` values from library layers. Can run last (lowest risk, widest touch).

Phase B requires A1 (typed phases) and A2 (first-class LocalPackage). **This refactor ships A1-A5, B3, and B4.** B1, B2, B5-B8 are future work that the refactored pipeline enables.

**Ships with this refactor:**

6. **B3: `.mars/` canonical store + managed target sync** — `.mars/` becomes the canonical content store (`.mars/agents/`, `.mars/skills/`). All target directories (`.agents/`, `.claude/`, `.cursor/`) are managed outputs materialized via copy. **This is the architectural pivot** — the pipeline's apply phase writes to `.mars/`, and a new target sync phase copies to all configured targets.
7. **B4: Model catalog integration** — two-mode ModelAlias (pinned + auto-resolve), builtin aliases, dependency-tree merge in `resolve_graph()`, cache lifecycle, CLI (refresh/list/resolve/alias). Depends on A1 (pipeline phases) and A3 (manifest extension).

**Future work (enabled by this refactor):**

- **B1: Generalized item kinds + rule files** — extensible `ItemKind`, per-kind discovery, per-kind materializers. Depends on B4 (per-model rule classification needs merged aliases).
- **B2: Harness-specific variants** — variant resolution in discovery, variant-aware target building. Depends on B1.
- **B5-B8: Capability items** — Permission sync, tool distribution, MCP integration, hook distribution. Depend on B1 + B3.

## Constraints

- **Backwards compatibility**: mars.toml and mars.lock formats must either stay compatible or have clean migration. Lock file has `version: 1` field for schema evolution.
- **Crash safety**: All writes must remain atomic (tmp+rename). No partial state on crash. Copy-based materialization supports this naturally.
- **No runtime dependencies**: Mars is build-time/setup-time. Capability definitions are declarative, not executable.
- **Single binary**: No dynamic loading. New item kinds and adapters are compiled in.
- **~5k LOC budget for Phase A**: The refactor should not significantly increase total LOC. Prefer restructuring over adding. Phase B will add net new code but should stay lean.
- **Model catalog ships with everything**: No partial releases — model catalog, pipeline decomposition, and extension model ship together. Model config merge uses the same dependency-tree precedence as other config sections.
- **Copy, not symlink for targets**: All content materialized to targets via copy (not symlink). Reasons: Windows symlinks need admin/developer mode, git symlink handling is finicky, copy + tmp+rename is simpler for crash safety, no broken links if `.mars/` is rebuilt.
- **`.mars/` is derived state**: Should be gitignored by the user (mars does NOT auto-edit `.gitignore`). `mars doctor` warns if `.mars/` is not ignored. Regenerated from mars.toml + mars.lock + sources. Only mars.toml and mars.lock are committed.
