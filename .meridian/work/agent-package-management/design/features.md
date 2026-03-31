# mars-agents: Feature Spec

## v1: Core Package Management

### `mars init`
Scaffold `.agents/agents.toml`. Detect existing `.agents/` content and offer to adopt it. Add `.agents/.mars/` to `.gitignore` if cache shouldn't be committed.

### `mars add <source>`
Add a source to `agents.toml`. Accepts git URL, local path, or registry name (future).

```bash
mars add github.com/haowjy/meridian-base@v0.5.0     # git source, URL is identity
mars add ../meridian-dev-workflow                      # local path
mars add github.com/haowjy/meridian-dev-workflow@v2   # latest v2.x.x
mars add meridian-dev-workflow                         # registry short name (future)
```

### `mars sync`
The core operation. Fetch sources, resolve dependencies, install into `.agents/`, update lock file.

1. Read `agents.toml` for declared sources
2. Fetch/update source content (git clone/pull or local copy)
3. Read manifests from each source
4. Resolve dependency graph (topological sort with version constraints)
5. Validate dependency graph (every `skills: [X]` in agent frontmatter resolves)
6. Diff current `.agents/` against resolved target state
7. Apply changes:
   - New files: copy in
   - Unchanged files: skip
   - Clean updates (no local modifications): overwrite
   - Conflicting updates (local mods + upstream changes): three-way merge, write conflict markers if needed
8. Prune orphans: files in old lock but not new lock, only if mars owns them
9. Write new `agents.lock`
10. Report: installed, updated, conflicted, pruned

Exit code: 0 if clean, 1 if unresolved conflicts remain.

### `mars sync --force`
Source wins. Skip three-way merge, overwrite managed files with upstream content, discard local modifications. Does NOT touch user-authored files (only mars-managed files per lock). This is the escape hatch for "I don't care about my local changes, give me what the provider ships."

### `mars sync --diff`
Dry run. Show what would change without applying. Preview before committing to a sync.

### `mars resolve`
After conflicts are resolved by the user (conflict markers removed), mark files as resolved. Record resolution in rerere database.

```bash
mars resolve                    # resolve all conflicted files
mars resolve agents/coder.md   # resolve specific file
```

### `mars remove <source>`
Remove a source from `agents.toml` and prune all files owned by that source (if no other source provides them).

### `mars doctor`
Validate state:
- Lock file matches actual files on disk (checksums)
- All dependency references resolve
- No orphaned files in lock
- No conflict markers left in files
- Config is well-formed

### `mars repair`
Rebuild `.agents/` from lock file. Re-fetch sources, re-install to match lock. Recovery from corruption or manual deletions.

## v1: Dependency System

### Version Resolution
Sources declare dependencies with version constraints (semver). Mars resolves transitively — not SAT, just topological sort with constraint intersection on a small graph.

If two sources require incompatible versions of a third source, mars errors with a clear message showing the conflict chain.

### Agent → Skill Validation
Agent profiles declare `skills: [X, Y, Z]` in YAML frontmatter. Mars validates that every referenced skill exists in `.agents/skills/` after resolution. Warning at sync time, error at `mars doctor`.

### Rename / Breaking Change Detection
Diff old lock vs new lock. If a name disappears from a source, check if dependents still reference it. Surface: "agent `verifier` depends on `verification-testing` which no longer exists — did you mean `verification`?"

### Provenance Tracking
Lock file records which source provided each file. Enables:
- Safe pruning (only delete if ALL providers dropped it)
- `mars why <name>` to explain why something is installed
- Conflict resolution when multiple sources provide the same name

## v1.5: Merge & Overrides

### Three-Way Merge
Uses `threeway_merge` crate (libgit2/xdiff algorithms). Base = last synced version (from lock/cache). Local = current file on disk. Theirs = new source version.

Clean merges applied automatically. Conflicts get git markers.

### Rerere Database
Stored in `.agents/.mars/rerere/`. Records resolution patterns (file + conflict hash → resolution). Auto-applies on future syncs when the same pattern recurs.

```bash
mars rerere list              # show recorded resolutions
mars rerere forget <file>     # clear resolution for a file
mars rerere off               # disable auto-resolution
```

### Field-Level Frontmatter Awareness
Mars understands YAML frontmatter in agent profiles. Conflicts in frontmatter fields (like `model:`) can be resolved at field granularity rather than line-level. Optional enhancement over raw three-way merge.

## v1.5: Update Workflow

### `mars outdated`
Show sources with newer versions available.

### `mars update`
Update within current version constraints. Like `npm update`.

### `mars upgrade`
Bump version constraints to latest. Like `npm upgrade` / `npx npm-check-updates`.

### `mars why <name>`
Explain why an agent or skill is installed — which source provides it, which agents depend on it.

```bash
$ mars why frontend-design
frontend-design (skill)
  provided by: meridian-dev-workflow@2.1.0
  required by:
    agents/frontend-coder.md (skills: [frontend-design])
```

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
