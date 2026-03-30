# Agent Package Management Redesign

## Problem

`meridian sources` is poorly named and missing key features. The current system copies files from git repos or local paths into `.agents/` and tracks what it installed. It works but has real gaps that showed up during dev-workflow iteration.

## Pain Points (concrete)

- **No dependency validation**: `frontend-coder` declares `skills: [frontend-design]` but nothing checks if that skill is installed. Agent breaks silently.
- **Binary conflict handling**: either keep local (`sources update`) or overwrite everything (`--force`). No merge, no diff, no per-file strategy.
- **"Sources" naming**: doesn't communicate what it does. Everyone expects `install`/`sync`/`update`.
- **`.agents/` treated as editable**: should be treated as generated output (like `node_modules/`). Edits get wiped on `--force`.

## Design Ideas

### Rename

`sources` -> `sync` or `install`/`update`. Match developer expectations.

### `.agents/` is generated, not authored

Like `node_modules/` — you don't edit it directly. You edit the source (e.g., `meridian-dev-workflow/`), commit, then sync. Local customizations should be structured (patches/overlays), not ad-hoc edits.

### Manifests

Each source declares what it provides:

```yaml
# meridian-dev-workflow/manifest.yaml
name: meridian-dev-workflow
description: Opinionated dev workflow with review fan-out and decision tracking
agents: [coder, frontend-coder, designer, dev-orchestrator, ...]
skills: [dev-orchestration, review, frontend-design, ...]
depends:
  - meridian-base  # needs core orchestrator skills
```

Benefits: explicit declaration, self-documenting, prevents syncing stray files, enables dependency validation.

### Dependency Validation

Agent profiles already declare their skill dependencies in frontmatter (`skills: [frontend-design]`). Meridian should validate the graph:

- At sync time: "agent `frontend-coder` requires skill `frontend-design` — not found in any installed source"
- At spawn time: "can't spawn frontend-coder — missing skill: frontend-design"

The dependency data already exists. Meridian just needs to read it and check.

### Merge Strategies

Replace binary keep/overwrite with real conflict handling:

```bash
meridian sync                  # default: keep local mods, update clean items
meridian sync --force           # theirs wins — overwrite everything
meridian sync --merge           # attempt merge, surface conflicts
meridian sync --diff            # show what would change, don't apply
```

Three-way diff using lock file as base (base -> local changes vs base -> source changes). Conflicts shown with actual diffs.

### Persisting Merge Decisions

Two approaches considered:

**Per-file overrides in manifest:**
```yaml
overrides:
  smoke-tester.md:
    strategy: local    # always keep my version
  __meridian-orchestrator.md:
    strategy: source   # always take upstream
```

**Patch/overlay (preferred):**
Save local modifications as patches reapplied after every sync:
```
.meridian/patches/
  smoke-tester.md.patch    # model: codex -> sonnet
  orchestrator.md.patch    # tools: scoped -> full
```

On sync: pull source -> apply patches -> prompt only when patches conflict with source changes. Cleanly separates "what upstream provides" from "what I customized."

### Generic vs Meridian

The sync mechanics (git clone, copy, merge, dep validation) are generic — they don't need to know what `$MERIDIAN_CHAT_ID` or `--from` means. But:

- The skill/agent content references meridian concepts (spawn, sessions, work items)
- Dependency validation needs to understand agent frontmatter format
- Runtime validation (does this model exist? is this harness available?) is meridian-specific

Conclusion: keep it in meridian. The agent format IS meridian's format. Separating would just duplicate the understanding of what an agent profile is. Like cargo is part of Rust — the package manager and runtime share the same model.

The sync mechanics could theoretically be extracted as a library if demand appears, but there's no need to force the separation now.

### Existing Ecosystem

Skills.sh (Vercel), Skild, SkillsMP, Tessl etc. handle skill installation but none do:
- Dependency resolution between agents and skills
- Merge strategies / conflict handling
- Agent profile management (only skills)
- Manifest-based source declarations

The gap is real — nobody manages the full `.agents/` directory with deps and merges.

### Orphan Pruning

Discovered during a bulk rename (agents + skills, 15 items). When a skill is renamed in the source, the install system creates the new directory but does NOT remove the old one. `.agents/` accumulates orphans.

Fix: lock-based reconciliation. On update, diff old lock vs new lock. Items in old lock but not new lock → remove from `.agents/`. Same pattern as npm prune, cargo clean, pip-sync.

### Local Submodule Preference

`agents.toml` has meridian-base as `kind = "git"` (fetches from GitHub). But the repo has meridian-base as a local submodule. During dev, you edit the submodule, commit locally, but `sources update` fetches the stale remote. You have to push before sync sees your changes.

Fix: if a git source URL matches a local submodule, prefer the local checkout. Zero config needed — just detect the submodule.

### Rename/Breaking Change Detection

When a skill is renamed, agents that depend on the old name break silently. The dependency graph should surface this: "agent `verifier` depends on `verification-testing` which no longer exists in source — did you mean `verification`?"

## Next Steps

1. Design the manifest format
2. Implement dependency validation (low-hanging fruit — data already exists in frontmatter)
3. Rename `sources` command
4. Add `--diff` to show what sync would change
5. Design and implement merge strategies
6. Design patch/overlay system for persistent local customizations
7. Orphan pruning via lock diff
8. Local submodule detection for git sources
9. Rename/breaking change warnings
