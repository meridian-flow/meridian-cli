# mars-agents: Feature Spec

## v1: Core Package Management

V1 commands: `init`, `add`, `sync`, `sync --force`, `sync --diff`, `remove`, `resolve`, `list`, `why`.

### `mars init`

Scaffold `.agents/agents.toml`. Detect existing `.agents/` content and offer to adopt it. Add `.agents/.mars/` to `.gitignore` if cache shouldn't be committed.

Note: `mars add` auto-initializes if no `.agents/` exists, so explicit `mars init` is only needed when you want to set up the directory before adding sources.

### `mars add <source>`

Add a source to `agents.toml`, resolve, install, and update the lock file. If `.agents/` doesn't exist, auto-initializes first (no separate `mars init` required).

Accepts git URLs, GitHub shorthand (`owner/repo`), and local paths. Defaults to `@latest` when no version is specified.

```bash
mars add haowjy/meridian-base                            # GitHub shorthand, @latest
mars add haowjy/meridian-base@v0.5.0                     # pinned version
mars add github.com/haowjy/meridian-dev-workflow@v2      # full URL, latest v2.x.x
mars add ../meridian-dev-workflow                          # local path
```

### `mars sync`

The core operation. Fetch sources, resolve dependencies, install into `.agents/`, update lock file.

1. Read `agents.toml` for declared sources (merged with `agents.local.toml` if present)
2. Fetch/update source content (git clone/pull or local copy)
3. Read manifests from each source (if present; filesystem discovery otherwise)
4. Resolve dependency graph (topological sort with version constraints)
5. Validate: warn if any `skills: [X]` reference in agent frontmatter doesn't resolve
6. Detect name collisions — error if two sources provide the same item name
7. Diff current `.agents/` against resolved target state
8. Apply changes:
   - New files: copy in
   - Unchanged files: skip
   - Clean updates (no local modifications): overwrite
   - Conflicting updates (local mods + upstream changes): three-way merge, write conflict markers if needed
9. Prune orphans: files in old lock but not new lock get removed (one owner per item)
10. Write new `agents.lock`
11. Report: installed, updated, conflicted, pruned

Exit code: 0 if clean, 1 if unresolved conflicts remain.

### `mars sync --force`

Source wins for managed files. Overwrite managed files with upstream content, discard local modifications. Does NOT touch user-authored files (only mars-managed files per lock file). This is the escape hatch for "I don't care about my local changes, give me what the source ships."

### `mars sync --diff`

Dry run. Show what would change without applying. Preview before committing to a sync.

### `mars remove <source>`

Remove a source from `agents.toml` and prune all files owned by that source. Since each item has exactly one owner, removal is straightforward — delete everything that source provided.

```bash
mars remove meridian-base
```

### `mars resolve`

After conflicts are resolved by the user (conflict markers removed), mark files as resolved and update the lock file checksums.

```bash
mars resolve                    # resolve all conflicted files
mars resolve agents/coder.md   # resolve specific file
```

### `mars list`

Show all managed items, their source, version, and status. Distinguish managed items from user-authored content.

```bash
$ mars list
SOURCE                    ITEM                          VERSION   STATUS
meridian-base             agents/architect.md           v0.5.2    ok
meridian-base             skills/__meridian-spawn/      v0.5.2    ok
meridian-dev-workflow     agents/dev-orchestrator.md    v2.1.0    modified
meridian-dev-workflow     skills/planning/              v2.1.0    ok

$ mars list --source meridian-base    # filter by source
$ mars list --kind agents             # filter by item kind
```

### `mars why <name>`

Explain why an agent or skill is installed — which source provides it, which agents depend on it.

```bash
$ mars why frontend-design
frontend-design (skill)
  provided by: meridian-dev-workflow@2.1.0
  required by:
    agents/frontend-coder.md (skills: [frontend-design])

$ mars why architect
architect (agent)
  provided by: meridian-base@v0.5.2
  required by: (no dependents)
```

## v1: Three-Way Merge

Three-way merge is the core differentiating feature. Without it, mars offers the same binary keep/overwrite behavior as existing tools.

Uses `threeway_merge` crate (libgit2/xdiff algorithms, 100% compatible with `git merge-file`). Base = last synced version (checksum + cached content from lock). Local = current file on disk. Theirs = new source version.

Four cases on sync, determined by comparing checksums against lock:

| Source changed? | Local changed? | Action |
|---|---|---|
| No | No | Skip |
| Yes | No | Overwrite (clean update) |
| No | Yes | Keep local |
| Yes | Yes | Three-way merge, conflict markers if needed |

Clean merges are applied automatically. Conflicts get standard git conflict markers (`<<<<<<<` / `=======` / `>>>>>>>`). Users resolve in their editor with full IDE support.

## v1: Name Collisions

Name collision = hard error at sync time. Two sources providing the same item name is always an error — no silent precedence, no implicit ordering.

```
error: agents/coder is provided by both `meridian-base` and `cool-agents`
  hint: use `exclude` on one source, or `rename` to install under a different filename
```

Resolution options:
- **`exclude`** on one source — don't install that item at all
- **`rename`** on one source — install under a different filename

Rename only changes the filename on disk. The frontmatter `name:` field is preserved, so the agent remains reachable by its original name (harnesses match on both filename and frontmatter name). Renames don't break cross-references.

## v1: Dependency System

### Version Resolution

URL-based package identity with constraint-based version resolution and lock file. Git tags are versions:

- `@v0.5.0` — exact version
- `@v2` — latest v2.x.x
- `@latest` — newest tag (default when unspecified)
- `@branch` or `@commit` — pin to ref
- `>=0.5.0, <1.0` — range constraint in dependencies

Transitive resolution via topological sort with constraint intersection. If constraints conflict, clear error showing the chain. Lock stores both tag name and commit SHA — if a tag is force-pushed, mars warns loudly.

### Agent-to-Skill Validation

Agent profiles declare `skills: [X, Y, Z]` in YAML frontmatter. Mars validates that every referenced skill exists in `.agents/skills/` after resolution. **Warning at sync time** (not error) — a missing skill doesn't prevent sync from completing but is surfaced clearly.

### Pruning

Simple one-owner-per-item model. If an item is in the old lock but not the new lock, remove it. No multi-provider logic — each item has exactly one owning source.

## v1: Config

### `agents.toml`

TOML format. Lives in `.agents/`. Primarily managed via CLI, not hand-edited. Supports `include`, `exclude`, and `rename` per source.

```toml
[sources.meridian-base]
url = "github.com/haowjy/meridian-base"
version = ">=0.5.0"

[sources.meridian-dev-workflow]
url = "github.com/haowjy/meridian-dev-workflow"
version = "^2.0"
exclude = ["agents/deprecated-agent"]

[sources.cool-agents]
url = "github.com/someone/cool-agents"
version = ">=1.0.0"
include = ["agents/researcher", "skills/web-search"]

[sources.my-local-agents]
path = "./my-agents"

# Rename to resolve name collisions between sources
[sources.cool-agents.rename]
"agents/coder" = "agents/cool-coder"
```

### `agents.local.toml` (Gitignored)

Dev overrides and local-only config. Merged on top of `agents.toml` at runtime. Not committed — each developer has their own.

```toml
[overrides]
meridian-base = { path = "../meridian-base" }  # use local checkout instead of git
```

### `mars.toml` (Per Source/Package, Optional)

Lives in the package repo root. **Optional** — mars works without it by discovering items from filesystem convention (`agents/*.md`, `skills/*/SKILL.md`). Most packages won't have one.

When present, `mars.toml` declares dependencies on other packages. What the repo provides is discovered from the filesystem, not the manifest — there is no `[provides]` section.

```toml
[package]
name = "meridian-dev-workflow"
version = "2.1.0"
description = "Opinionated dev workflow with review fan-out and decision tracking"

[dependencies.meridian-base]
url = "github.com/haowjy/meridian-base"
version = ">=0.5.0"
items = ["skills/frontend-design"]  # cherry-pick specific items from this dep

[dependencies.meridian-core]
url = "github.com/haowjy/meridian-core"
version = ">=1.0.0"
# no items = everything from this package
```

### Lock: `agents.lock`

Tracks every managed file with provenance and integrity. Each item has exactly one owning source.

```toml
[agents."dev-orchestrator.md"]
source = "meridian-dev-workflow"
version = "2.1.0"
commit = "a1b2c3d4e5f6..."
checksum = "sha256:abc123..."

[skills."__meridian-spawn"]
source = "meridian-base"
version = "0.5.2"
commit = "f6e5d4c3b2a1..."
checksum = "sha256:def456..."
```

## v1.5 and Later

Features deferred from v1. Ordered roughly by expected value.

### `mars doctor`

Validate state:
- Lock file matches actual files on disk (checksums)
- All dependency references resolve
- No orphaned files in lock
- No conflict markers left in files
- Config is well-formed

### `mars repair`

Rebuild `.agents/` from lock file. Re-fetch sources, re-install to match lock. Recovery from corruption or manual deletions.

### Rename / Breaking Change Detection

Diff old lock vs new lock. If a name disappears from a source, check if dependents still reference it. Surface: "agent `verifier` depends on `verification-testing` which no longer exists — did you mean `verification`?"

### `mars outdated` / `mars update` / `mars upgrade`

- `mars outdated` — show sources with newer versions available
- `mars update` — update within current version constraints
- `mars upgrade` — bump version constraints to latest

### Rerere (Reuse Recorded Resolution)

Record conflict resolutions and auto-apply on future syncs. Stored in `.agents/.mars/rerere/`. Deferred because the same-conflict-recurring pattern is rare in practice.

```bash
mars rerere list              # show recorded resolutions
mars rerere forget <file>     # clear resolution for a file
mars rerere off               # disable auto-resolution
```

### Semantic Frontmatter-Aware Merge

Understand YAML frontmatter in agent profiles. Resolve frontmatter field conflicts at field granularity rather than line-level. Enhancement over raw three-way merge.

## v2: Security & Scripts

### Script Management

Skills can contain scripts alongside SKILL.md. Mars needs a trust model:
- First install: prompt user to approve scripts from new sources
- Allowlist by source in `agents.toml`
- `mars sync --dry-run` shows what scripts would be installed
- Checksum verification on scripts (detect tampering)

### Source Trust Policy

```toml
[trust]
allow = ["git", "local"]         # allowed source types
require-checksum = true           # enforce integrity checks
```

## v2: Cache & Offline

### Content-Addressed Cache

Cache source content by hash in `.agents/.mars/cache/`. Don't re-download unchanged sources.

### Offline Mode

`mars sync --offline` installs from cache only. For CI/air-gapped environments.

### Cache Management

```bash
mars cache list       # show cached sources
mars cache prune      # remove stale entries
mars cache clear      # wipe everything
```

## Future: Registry & Marketplace

### `mars search <query>`

Search registry for packages.

### `mars publish`

Publish a package to the registry.

### `mars install <package>`

Install from registry (vs `mars add` for git/local sources).

### Workspace Support

Monorepo with multiple projects sharing a lock file but different install targets.
