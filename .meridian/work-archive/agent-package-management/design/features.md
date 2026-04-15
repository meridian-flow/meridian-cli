# mars-agents: Feature Spec

## Core Invariant: All Mutations Resolve First

Every command that changes state (`add`, `remove`, `upgrade`, `rename`, `sync`) proposes a new target state and resolves the full dependency graph against it before touching disk. Either the entire proposed state is satisfiable — all version constraints, no unresolvable collisions, no orphaned transitive deps — or the command fails and nothing changes.

No partial mutations. No "upgrade A now, fix B later." The resolver sees the whole picture and either commits the whole change or rejects it with a clear explanation of what conflicts.

This is the architectural backbone — the sync pipeline (resolve → validate → diff → plan → apply) is the single path every mutation flows through.

## Output Modes

Two output modes for every command:

### Normal (default)

Human-readable, concise. Quiet when nothing interesting happened, detailed only when something needs attention. Designed for minimal token consumption — AI agents calling mars shouldn't burn context on verbose output.

```bash
$ mars sync
✓ 2 sources, 11 items, 0 conflicts

$ mars sync
✓ meridian-base@0.8.0 (3 updated)
⚠ agents/coder renamed → agents/coder__haowjy_meridian-base
✗ 1 conflict in agents/reviewer.md — run mars resolve

$ mars update
✓ meridian-base 0.8.0 → 0.9.1

$ mars list
meridian-base        agents/coder.md          v0.8.0  ok
meridian-base        skills/code-review/      v0.8.0  modified
```

### `--json`

Machine-readable JSON for CI pipelines, scripting, and programmatic consumption. Every command supports it.

```bash
$ mars sync --json
{"ok":true,"sources":2,"items":11,"updated":3,"conflicts":0}

$ mars list --json
[{"source":"meridian-base","item":"agents/coder.md","version":"0.8.0","status":"ok"},...]
```

Exit codes are consistent across both modes: 0 = success, 1 = conflicts remain, 2 = resolution error, 3 = I/O error.

## v1: Core Package Management

V1 commands: `init`, `add`, `sync`, `sync --force`, `sync --diff`, `sync --frozen`, `remove`, `resolve`, `rename`, `update`, `outdated`, `override`, `list`, `why`, `doctor`, `repair`.

### `mars init`

Scaffold `.agents/agents.toml`. Detect existing `.agents/` content and offer to adopt it. Add `.agents/.mars/` to `.gitignore` if cache shouldn't be committed.

Note: `mars add` auto-initializes if no `.agents/` exists, so explicit `mars init` is only needed when you want to set up the directory before adding sources.

### `mars add <source>`

Add a source to `agents.toml`, resolve, install, and update the lock file. If `.agents/` doesn't exist, auto-initializes first (no separate `mars init` required).

If the source already exists in config, `mars add` is an **upsert** — updates the version constraint and re-resolves. This is the way to pin a source to a different version without using `mars upgrade`.

Accepts git URLs, GitHub shorthand (`owner/repo`), and local paths. Defaults to `@latest` when no version is specified.

```bash
mars add haowjy/meridian-base                            # GitHub shorthand, @latest, install everything
mars add haowjy/meridian-base@v0.5.0                     # pinned version
mars add github.com/haowjy/meridian-dev-workflow@v2      # full URL, latest v2.x.x
mars add ../meridian-dev-workflow                          # local path

# Intent-based filtering: only install specific items + their deps
mars add haowjy/meridian-base --agents coder --skills frontend-design
# → installs agents/coder, skills/frontend-design, + any skills coder depends on
# → writes agents = ["coder"], skills = ["frontend-design"] to config
# → deps re-resolved on every sync (new deps auto-included)
```

### `mars sync`

The core operation. Fetch sources, resolve dependencies, install into `.agents/`, update lock file.

Acquires an advisory file lock (`flock` on `.agents/.mars/sync.lock`) at the start and holds it through completion. Concurrent `mars sync` processes block until the lock is released — no stale-plan races.

If any source fetch fails (network error, auth failure), the entire sync aborts before modifying `.agents/` or the lock file. Partially updated caches are fine (non-authoritative, reused next run).

Pipeline:

1. Acquire sync lock
2. Read `agents.toml` for declared sources (merged with `agents.local.toml` if present)
3. Fetch/update source content (git clone/pull or local copy) — abort on any failure
4. Read manifests from each source (if present; filesystem discovery otherwise)
5. Resolve dependency graph (topological sort with version constraints)
6. Build target state: apply intent-based filtering (`agents`/`skills`/`exclude`), resolve skill deps from frontmatter
7. Detect collisions on destination paths — auto-rename with `{name}__{owner}_{repo}`
8. Rewrite frontmatter skill references for renamed transitive deps
9. Validate: warn if any `skills: [X]` reference doesn't resolve
10. Diff current `.agents/` against target state (using dual checksums from lock)
11. Apply changes:
    - New files: copy in (atomic write)
    - Unchanged files: skip
    - Clean updates (no local modifications): overwrite
    - Conflicting updates (local mods + upstream changes): three-way merge via `git2::merge_file()`, write conflict markers if needed
12. Prune orphans: items in old lock but not new lock get removed
13. Write new `agents.lock` (atomic write)
14. Release sync lock
15. Report: installed, updated, conflicted, pruned

Exit code: 0 if clean, 1 if unresolved conflicts remain.

### `mars sync --force`

Source wins for managed files. Overwrite managed files with upstream content, discard local modifications. Does NOT touch user-authored files (only mars-managed files per lock file). This is the escape hatch for "I don't care about my local changes, give me what the source ships."

### `mars sync --diff`

Dry run. Show what would change without applying. Preview before committing to a sync.

### `mars sync --frozen`

Install exactly from the committed lock file. Error if the lock is stale (config changed but lock wasn't updated), or if any resolution would produce different versions than what's locked. No fetching of new versions, no resolution — just install what the lock says.

For teammates cloning a project and CI pipelines:

```bash
# Teammate clones and gets exact same versions
git clone repo && cd repo && mars sync --frozen

# CI enforces lock is up to date
mars sync --frozen || { echo "Lock is stale, run mars sync and commit"; exit 1; }
```

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

### `mars rename`

Rename a managed item. Updates the `rename` config in `agents.toml` and re-syncs. CLI-first way to override auto-generated collision names or give any managed item a custom filename.

```bash
mars rename agents/coder__haowjy_meridian-base agents/coder   # custom name
mars rename agents/coder agents/my-coder                       # rename any managed item
```

Rename only changes the filename on disk — frontmatter `name:` field is preserved. The agent remains reachable by its original frontmatter name.

Explicit renames (via `mars rename`) take precedence over auto-renames. If an explicit rename causes a new collision, mars errors rather than silently re-auto-renaming.

### `mars update`

Update sources to the newest versions satisfying current constraints. Resolves all targets simultaneously.

```bash
mars update                              # update all sources within constraints
mars update meridian-base                # update one source + its deps
mars update meridian-base cool-agents    # update multiple together
```

The resolver finds the newest versions satisfying all constraints across all sources simultaneously. Resolving together avoids intermediate states where one update breaks another's constraints.

If no compatible set exists:

```
error: cannot update — version constraints conflict:
  cool-agents requires meridian-base >=0.5.0, <0.6.0
  dev-workflow requires meridian-base >=0.6.0
  hint: use `mars add cool-agents@newversion` to widen its constraint
```

To go past current constraints (e.g., jump to a new major version), use `mars add source@newversion` which upserts the constraint in config.

`mars update` also attempts to resolve transitive dependency conflicts first — if updating source A requires updating its transitive dep B, mars tries to find a compatible B version before erroring.

### `mars outdated`

Show which sources have newer versions available — both within current constraints and beyond.

```bash
$ mars outdated
SOURCE              LOCKED    CONSTRAINT      UPDATEABLE  LATEST
meridian-base       v0.8.0    >=0.5.0, <1.0   v0.9.1      v1.2.0
cool-agents         v1.3.0    ^1.0            v1.3.0      v2.0.0
dev-workflow        v2.1.0    ^2.0            v2.1.0      v2.1.0

1 source can be updated (mars update), 2 have newer major versions (mars add source@newversion)
```

Informational only — doesn't change anything. Shows what `mars update` would do vs what requires a constraint change via `mars add`.

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

### `mars doctor`

Validate state — check that everything is consistent:

- Lock file matches actual files on disk (checksums)
- All agent→skill dependency references resolve
- No orphaned entries in lock (files that don't exist on disk)
- No unresolved conflict markers left in files
- Config is well-formed TOML
- All source URLs are reachable (optional, with `--network`)

```bash
$ mars doctor
✓ lock checksums match disk
✓ all skill references resolve
✗ agents/coder.md has unresolved conflict markers
✗ lock references skills/old-skill/ which doesn't exist on disk

2 issues found. Run `mars repair` to fix.
```

### `mars repair`

Rebuild `.agents/` state from lock + sources. Re-fetch sources, re-install to match lock. Recovery from corruption, manual deletions, or diverged state (e.g., lock written but files missing after a crash).

```bash
mars repair                # re-sync everything from lock
mars repair --adopt        # no lock exists — adopt current disk state as baseline
```

`--adopt` is for the case where `agents.lock` was deleted but `.agents/` files remain. Mars re-resolves from config, matches existing files to sources by content, and rebuilds the lock without overwriting anything.

## v1: Three-Way Merge

Three-way merge is the core differentiating feature. Without it, mars offers the same binary keep/overwrite behavior as existing tools.

Uses `git2::merge_file()` — libgit2's built-in three-way merge with conflict markers (git2 is already a dependency for git operations, no extra crate needed). Base = last synced version (cached content from lock). Local = current file on disk. Theirs = new source version.

Four cases on sync, determined by comparing checksums against lock:

| Source changed? | Local changed? | Action |
|---|---|---|
| No | No | Skip |
| Yes | No | Overwrite (clean update) |
| No | Yes | Keep local |
| Yes | Yes | Three-way merge, conflict markers if needed |

Clean merges are applied automatically. Conflicts get standard git conflict markers (`<<<<<<<` / `=======` / `>>>>>>>`). Users resolve in their editor with full IDE support.

## v1: Name Collisions and Auto-Rename

Collision detection runs on **destination paths** after all filtering and renaming. When two items from different sources would land at the same path, mars auto-renames both using `{name}__{owner}_{repo}` (name-first for autocomplete grouping):

```
warning: agents/coder is provided by both `meridian-base` and `cool-agents`
  auto-renamed to:
    agents/coder__haowjy_meridian-base.md
    agents/coder__someone_cool-agents.md
```

No implicit precedence — both get renamed. User can override with `mars rename` for custom names, or `exclude` to skip one.

### Transitive Dependency Collisions

When two sources transitively depend on different implementations of the same skill:

- `dev-workflow` depends on `meridian-base`'s `skills/code-review`
- `other-pack` depends on `cool-tools`'s `skills/code-review`

Mars auto-renames both skills AND rewrites the frontmatter `skills:` references in affected agents to point at the correct renamed version. Mars uses the manifest dependency chain to determine which agents should reference which renamed skill:

1. Collision detected: `skills/code-review` from two sources
2. Auto-rename both: `skills/code-review__haowjy_meridian-base/`, `skills/code-review__someone_cool-tools/`
3. Walk the manifest dep graph: `dev-workflow` depends on `meridian-base` → its agents get `skills: [code-review__haowjy_meridian-base]`
4. `other-pack` depends on `cool-tools` → its agents get `skills: [code-review__someone_cool-tools]`

This is the one case where mars modifies file content — only when a collision forces a rename AND the affected agents have frontmatter skill references that need updating.

### Dual Checksums in Lock

Because mars may rewrite frontmatter, the lock stores two checksums per item:

- **`source_checksum`**: what upstream provided (pre-rewrite)
- **`installed_checksum`**: what mars actually wrote to disk (post-rewrite, if any)

The diff logic uses these to correctly classify changes:
- Source changed? Compare new source content against `source_checksum`
- Local changed? Compare disk content against `installed_checksum`

This prevents mars-managed rewrites from triggering false conflicts on the next sync.

When no collision/rewrite occurs, both checksums are identical.

### Collision with User-Authored Files

If a source tries to install an item at a path that already exists on disk but isn't in the lock (i.e., user-created), mars errors:

```
error: can't install skills/my-custom-skill from `meridian-base` — a user-authored file already exists at that path
  hint: rename the source item via `rename` in agents.toml, or remove your file
```

Mars never silently overwrites user content.

## v1: Dependency System

### Transitive Source Installation

When a source has a `mars.toml` declaring dependencies, mars fetches and installs from those dependencies too. The user doesn't need to `mars add` every transitive dependency.

```bash
mars add haowjy/meridian-dev-workflow
# dev-workflow's mars.toml depends on meridian-base for skills/code-review
# → mars fetches meridian-base and installs skills/code-review automatically
```

Transitive deps are tracked in the lock with provenance — `mars why code-review` shows the full chain.

### Version Resolution

URL-based package identity with constraint-based version resolution and lock file. Git tags are versions:

- `@v0.5.0` — exact version
- `@v2` — latest v2.x.x
- `@latest` — newest tag (default when unspecified)
- `@branch` or `@commit` — pin to ref
- `>=0.5.0, <1.0` — range constraint in dependencies

Transitive resolution via topological sort with constraint intersection. If constraints conflict, clear error showing the chain. Lock stores both tag name and commit SHA — if a tag is force-pushed, mars warns loudly.

### Agent-to-Skill Validation

Agent profiles declare `skills: [X, Y, Z]` in YAML frontmatter. After resolution (including any auto-renames), mars validates that every referenced skill exists in `.agents/skills/`. **Warning at sync time** (not error) — a missing skill doesn't prevent sync from completing but is surfaced clearly.

### Pruning

One-owner-per-item model. If an item is in the old lock but not the new lock, remove it. Transitive deps are pruned when no remaining source requires them.

## v1: Config

### `agents.toml`

TOML format. Lives in `.agents/`. Primarily managed via CLI, not hand-edited.

```toml
[sources.meridian-base]
url = "github.com/haowjy/meridian-base"
version = ">=0.5.0"
agents = ["coder"]              # intent: only this agent + its skill deps
skills = ["frontend-design"]    # intent: explicitly requested skill

[sources.meridian-dev-workflow]
url = "github.com/haowjy/meridian-dev-workflow"
version = "^2.0"
exclude = ["agents/deprecated-agent"]  # everything except these

[sources.my-local-agents]
path = "./my-agents"
# no agents/skills/exclude = install everything
```

Filtering modes (pick one per source):
- **`agents`/`skills`**: Intent-based. Install these + auto-resolve skill deps from frontmatter. New deps auto-included on future syncs.
- **`exclude`**: Install everything except these.
- **Neither**: Install everything (default).

Auto-generated renames (from collision resolution) are tracked in the lock, not in `agents.toml`. User-explicit renames via `mars rename` are written to config.

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
source_checksum = "sha256:abc123..."
installed_checksum = "sha256:abc123..."

[skills."__meridian-spawn"]
source = "meridian-base"
version = "0.5.2"
commit = "f6e5d4c3b2a1..."
source_checksum = "sha256:def456..."
installed_checksum = "sha256:def456..."
```

## v2: Security, Scripts, and Polish

### Patches / Persistent Customizations

Save local modifications as patches that are automatically reapplied after every sync. Solves "I always change `model: sonnet` on this agent" without conflict markers on every update. Cleanly separates "what upstream provides" from "what I customized."

### Rerere (Reuse Recorded Resolution)

Record conflict resolutions and auto-apply on future syncs. For the rare case where the same conflict recurs.

### Semantic Frontmatter-Aware Merge

Resolve frontmatter field conflicts at field granularity rather than line-level. Enhancement over raw three-way merge.

### Script Management

Skills can contain scripts alongside SKILL.md. Mars needs a trust model:
- First install: prompt user to approve scripts from new sources
- Allowlist by source in `agents.toml`
- `mars sync --diff` shows what scripts would be installed
- Checksum verification on scripts (detect tampering)

### Source Trust Policy

```toml
[trust]
allow = ["git", "local"]         # allowed source types
require-checksum = true           # enforce integrity checks
```

### `mars diff <source>`

Show what changed upstream since your lock — preview upstream changes before updating. Like `git diff` for your sources.

### `mars audit`

Security scan of installed agents/skills. Check for known vulnerabilities, suspicious patterns, overly broad permissions. Relevant given Vett's positioning in the space.

### Plugin Hooks

Pre/post sync hooks for custom workflows. The sync pipeline's discrete steps with clear inputs/outputs make this a natural extension point.

```toml
[hooks]
pre-sync = "scripts/validate-agents.sh"
post-sync = "scripts/notify-team.sh"
```

### Private Registry Auth

API tokens, org-scoped packages, credential management for private registries.

### `mars init --from <template>`

Initialize from an existing project's config. Template projects for teams.

## Future: Registry & Marketplace

### `mars search <query>`

Search registry for packages.

### `mars publish`

Publish a package to the registry.

### `mars install <package>`

Install from registry (vs `mars add` for git/local sources).

### Workspace Support

Monorepo with multiple projects sharing a lock file but different install targets.

## v1 Architecture Notes for Future Extensibility

These don't require changes — just awareness during implementation:

- **Lock schema**: extensible via optional fields + `version: 1` field. New fields (signatures, patch metadata) can be added without breaking old locks.
- **Source resolution**: behind `SourceFetcher` trait. Registry = new adapter, no pipeline change.
- **Sync pipeline**: discrete steps with clear inputs/outputs. Hooks insert between steps. Patches layer after apply.
- **Auth**: `git2` credential callbacks already support SSH agent, HTTPS tokens, git credential helpers. Don't bypass them.
- **Trust**: lock stores checksums + commit SHAs. Signature verification = checking an additional field on the existing data.
