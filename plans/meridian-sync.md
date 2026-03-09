# meridian sync -- External Skill and Agent Synchronization

**Status:** design (not started)

## 1. Problem

Users maintain skill and agent collections in separate repos (personal workflows, team standards, shared libraries). There is no mechanism in meridian to install them into harness-discoverable locations (`.agents/skills/`, `.agents/agents/`). The current workaround is shell scripts or manual copying, which breaks when upstream changes and provides no conflict detection, provenance tracking, or reproducibility.

## 2. Solution

A first-class `meridian sync` command that:

- Syncs skills and agents from remote (GitHub) or local sources into the current project
- Supports multiple named sources via project config
- Tracks provenance in a Nix-inspired lock file recording both requested refs and resolved commit SHAs
- Detects local edits via tree hashing and prevents accidental overwrites
- Supports renaming items on install to avoid collisions or customize local names
- Respects locked commits by default; re-resolves floating refs only with `upgrade`
- Never auto-syncs -- explicit `meridian sync` invocation only

Sync is CLI-only. It is not exposed via MCP and is not added to the ops manifest.

## 3. Project Layout

All sync state is project-local. No global `~/.meridian/` directory needed for v1.

```
.meridian/
├── config.toml           # sync sources config
├── sync.lock             # provenance tracking -- what's installed, from where, at what commit
├── cache/
│   └── sync/
│       ├── haowjy-meridian-skills/   # cloned source repos (project-local)
│       └── myorg-team-standards/
└── .spaces/              # existing space state (unchanged)
```

### Why project-local cache?

- Different projects can pin different refs of the same source repo without interference
- No cross-project lock contention or stale-ref bugs
- Clones of markdown-only repos are small -- the duplication cost is negligible
- Eliminates an entire class of bugs around shared mutable state
- The existing `StatePaths` already provides `cache_dir` at `.meridian/cache/`

## 4. Sources

Two types, both supported in v1:

- **Remote:** GitHub repo shorthand (`owner/repo`). Cloned into `.meridian/cache/sync/{owner}-{repo}/`. Full clones (not `--depth 1`) because locked commits may not be at branch tips. The repos are markdown-only so full clones are small.
- **Local:** Filesystem path (relative to repo root or absolute). No caching needed -- reads directly.

Multiple sources supported via `[[sync.sources]]` array in config.

### Source repo structure (expected)

```
skills/
  skill-name/
    SKILL.md
    (other files -- skills are directories, not single files)
agents/
  agent-name.md
```

Auto-discovered -- no manifest required in the source repo. Skills are found by scanning `skills/*/SKILL.md` (each skill is a directory). Agents are found by scanning `agents/*.md` (each agent is a single file).

### Cross-source name collisions

If two different sources export the same skill or agent name (after renames are applied), sync fails with a hard error:

```
ERROR: Name collision for skill "deploy-checklist":
  - source "personal" (haowjy/meridian-skills)
  - source "team" (myorg/team-standards)
Resolve by renaming in one source, e.g.:
  meridian sync install myorg/team-standards --rename deploy-checklist=team-deploy-checklist
```

This is checked after config merge, discovery, and rename application, before any files are copied.

## 5. Config

Config lives in the project's `.meridian/config.toml`. No global config layer in v1.

```toml
[[sync.sources]]
name = "personal"
repo = "haowjy/meridian-skills"
ref = "main"
# no skills/agents filter = sync all from this source

[[sync.sources]]
name = "team"
repo = "myorg/team-standards"
ref = "v1.2.0"
skills = ["deploy-checklist"]
agents = ["qa-reviewer"]
exclude_skills = ["deprecated-thing"]
rename = {review = "code-review", reviewer = "team-reviewer"}
```

### Source fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Unique label for the source |
| `repo` | string | XOR with `path` | GitHub shorthand (`owner/repo`) |
| `path` | string | XOR with `repo` | Local filesystem path (relative to repo root or absolute) |
| `ref` | string | no | Branch or tag for remote repos (default: repo's default branch). Only valid with `repo`. |
| `skills` | string[] | no | Include filter. **Omitted** = sync all discovered skills. **Empty array `[]`** = sync no skills. |
| `agents` | string[] | no | Include filter. **Omitted** = sync all discovered agents. **Empty array `[]`** = sync no agents. |
| `exclude_skills` | string[] | no | Exclude filter. Listed skills are never synced. Applied after `skills` include filter. |
| `exclude_agents` | string[] | no | Exclude filter. Listed agents are never synced. Applied after `agents` include filter. |
| `rename` | {string: string} | no | Rename map. Keys are source item names, values are local names. Applied after include/exclude filters. Works for both skills and agents. |

### Rename semantics

The `rename` map applies to any discovered item (skill or agent) whose source name matches a key. The item is installed under the mapped name instead:

- Source has `skills/review/` → with `rename = {review = "code-review"}` → installed as `.agents/skills/code-review/`
- Source has `agents/reviewer.md` → with `rename = {reviewer = "team-reviewer"}` → installed as `.agents/agents/team-reviewer.md`
- Renames are applied after include/exclude filters. The include/exclude filters use the **source** name, not the renamed name.
- Cross-source collision checks use the **renamed** name (the destination name).
- Lock entries key by the **renamed** name and also record the `source_item_name` for provenance.

### Validation

- Duplicate `name` within the config is an error
- Each source must have exactly one of `repo` or `path`
- `ref` is only valid with `repo`, not `path`
- `repo` format validated as `owner/repo` (must contain exactly one `/`, both parts non-empty)

### TOML normalization rules

When reading `[[sync.sources]]` from TOML:

- Each element maps to a `SyncSourceConfig` Pydantic model
- `repo` XOR `path` is enforced via model validator (neither or both is an error)
- `ref` with `path` source raises a validation error
- `repo` format validated as `owner/repo` (must contain exactly one `/`, both parts non-empty)
- `skills` and `agents` arrays: each entry must be a non-empty string after stripping whitespace
- Omitted `skills`/`agents` field means "sync all" (represented as `None` in the model)
- Explicit empty array `skills = []` means "sync none" (represented as empty tuple `()`)
- `rename` is an inline TOML table mapping source names to local names (represented as `dict[str, str]`)

## 6. Destination

Sync installs into `.agents/` as the canonical location, then creates **per-item symlinks** in `.claude/` for Claude Code discoverability:

- `.agents/skills/foo/` and `.agents/agents/bar.md` — canonical, harness-agnostic. Codex, OpenCode, and other harnesses read from here directly.
- `.claude/skills/foo -> ../../.agents/skills/foo` — per-item symlink so Claude Code discovers it immediately without requiring `meridian start`.

**Why symlinks, not copies:**
- One source of truth — no drift between `.agents/` and `.claude/`
- Edits to `.agents/skills/foo/SKILL.md` are immediately reflected in `.claude/`
- Sync only manages the symlink, not a second copy of content

**Conflict handling for `.claude/` symlinks:**
- If `.claude/skills/foo` already exists as a **real directory or file** (not a symlink): this is an unmanaged conflict. Block unless `--force`. The user has a manually-created skill there.
- If `.claude/skills/foo` already exists as a **symlink that sync created** (points to `.agents/`): no conflict, update or skip as normal.
- If `.agents/skills/foo` is deleted: the `.claude/` symlink becomes dangling. `sync status` reports "missing", `sync` reinstalls both.

The lock file tracks one entry per logical item (e.g. `skills/github-issues`). Conflict detection runs against `.agents/` only — that's the canonical source of truth.

This makes `meridian sync` a standalone tool — it works whether or not you use meridian for launching.

**Implementation note:** The `.claude/` symlinks exist because Claude Code doesn't read from `.agents/` — unlike Codex and OpenCode which do. If Claude Code ever adds `.agents/` to its search path, the symlink step can be removed. Comment this coupling clearly in the code.

No configurable destination in v1.

## 7. CLI Interface

Subcommand group:

```bash
meridian sync install haowjy/meridian-skills                          # add source, resolve latest, install, lock
meridian sync install haowjy/meridian-skills --ref v1.2.0             # at specific tag/branch
meridian sync install haowjy/meridian-skills --name personal          # custom name (default: owner-repo)
meridian sync install haowjy/meridian-skills --rename review=code-review  # rename item on install
meridian sync install ./local/skills --name local-skills              # local path source
meridian sync remove personal                                         # remove source from config + uninstall
meridian sync update                                                  # install from lock (reproducible)
meridian sync update --source personal                                # update one source only
meridian sync upgrade                                                 # re-resolve refs to latest upstream
meridian sync upgrade --source personal                               # upgrade one source only
meridian sync status                                                  # offline: compare lock vs local files
```

### Subcommands

| Subcommand | Description |
|------------|-------------|
| `install <repo-or-path>` | Add source to config, resolve ref, install items, write lock. Auto-derives name from `owner-repo` unless `--name` given. Checks for conflicts before writing. |
| `remove <name>` | Remove source from config and uninstall its managed items. Preserves user-edited files (warns instead of deleting). |
| `update` | Install/sync from lock file. Reproducible — uses locked commits, does not re-resolve refs. For first-time setup after cloning a repo with existing config + lock. |
| `upgrade` | Re-resolve floating refs (branches) to latest upstream commit, then sync. Tags and pinned commits are unchanged. |
| `status` | Offline comparison of lock vs local files. No network access. |

### Shared flags

These flags work with `install`, `update`, and `upgrade`:

| Flag | Description |
|------|-------------|
| `--force` | Overwrite local modifications and unmanaged files |
| `--dry-run` | Fetch/resolve but do not write. Shows what WOULD change. |

### `install` flags

| Flag | Description |
|------|-------------|
| `--name NAME` | Custom source name. Default: auto-derived from repo (`owner-repo`) or path (last component). |
| `--ref REF` | Branch or tag for remote repos. Default: repo's default branch. |
| `--skills SKILL,...` | Include filter — only sync these skills. Omit to sync all. |
| `--agents AGENT,...` | Include filter — only sync these agents. Omit to sync all. |
| `--rename OLD=NEW` | Rename an item on install. Repeatable. Written to config for future syncs. |

### `update` / `upgrade` flags

| Flag | Description |
|------|-------------|
| `--source NAME` | Sync only the named source. |
| `--prune` | Remove orphaned managed content (source no longer in config or item no longer discovered). Preserves user-edited files. |

### `install` behavior

`install` is a single command that both configures AND installs:
1. Writes a `[[sync.sources]]` entry to `.meridian/config.toml` (with name, repo/path, ref, filters, renames)
2. Fetches/resolves the source
3. Runs the full sync algorithm (discover, conflict check, apply) for that source
4. Writes the lock file

If the source name already exists in config, error with message to use `remove` first or pick a different `--name`.

### `remove` behavior

`remove` deletes the source entry from `.meridian/config.toml` and uninstalls items that source provided:
- Items whose local body matches the lock hash: deleted from `.agents/` and `.claude/` symlink removed.
- Items whose local body was edited by the user: kept on disk with a warning. Lock entry removed.
- Items shared with another source: not possible (cross-source collision is a hard error at `install` time).

### `status` semantics

`meridian sync status` does NOT fetch from the network. It compares lock state against local files only:

- **in-sync**: local file matches lock checksum
- **locally-modified**: local file differs from lock checksum
- **missing**: lock entry exists but file is gone from `.agents/`
- **orphaned**: lock entry's source is no longer in config

To check for upstream changes, use `meridian sync upgrade --dry-run` (which does fetch).

## 8. Lock File

`.meridian/sync.lock` is a JSON file that records full provenance for every synced item. It follows the Nix "original vs locked" pattern: both the requested ref and the resolved commit SHA are recorded.

**Git tracking:** `sync.lock` SHOULD be committed to git (like `package-lock.json` or `Cargo.lock`). The existing `.meridian/.gitignore` ignores `.spaces/` and `cache/` but should whitelist `sync.lock` so it's tracked. This ensures reproducible syncs across team members.

### Schema

```json
{
  "version": 1,
  "items": {
    "skills/github-issues": {
      "source_name": "personal",
      "source_type": "repo",
      "source_value": "haowjy/meridian-skills",
      "source_item_name": "github-issues",
      "requested_ref": "main",
      "locked_commit": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
      "item_kind": "skill",
      "dest_path": ".agents/skills/github-issues",
      "tree_hash": "sha256:9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
      "synced_at": "2026-03-08T14:30:00Z"
    },
    "skills/code-review": {
      "source_name": "team",
      "source_type": "repo",
      "source_value": "myorg/team-standards",
      "source_item_name": "review",
      "requested_ref": "v1.2.0",
      "locked_commit": "b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3",
      "item_kind": "skill",
      "dest_path": ".agents/skills/code-review",
      "tree_hash": "sha256:d7a8fbb307d7809469ca9abcb0082e4f8d5651e46d3cdb762d02d0bf37c9e592",
      "synced_at": "2026-03-08T14:30:00Z"
    }
  }
}
```

In the second entry, `source_item_name` is `"review"` (the name in the source repo) but the lock key and `dest_path` use the renamed name `"code-review"`.

For local path sources, `source_type` is `"path"`, `source_value` is the path, and `requested_ref` / `locked_commit` are `null`.

### Lock entry fields

| Field | Type | Description |
|-------|------|-------------|
| `source_name` | string | Name of the config source |
| `source_type` | `"repo"` or `"path"` | Source kind |
| `source_value` | string | `owner/repo` for remote, filesystem path for local |
| `source_item_name` | string | Original item name in the source repo (before rename). Same as the lock key if not renamed. |
| `requested_ref` | string or null | The ref from config (e.g. `"main"`, `"v1.2.0"`). Null for local sources. |
| `locked_commit` | string or null | Resolved full commit SHA at time of sync. Null for local sources. |
| `item_kind` | `"skill"` or `"agent"` | What was synced |
| `dest_path` | string | Relative path from repo root (e.g. `.agents/skills/github-issues`) |
| `tree_hash` | string | `sha256:...` hash of the synced content (see Tree Hash below) |
| `synced_at` | string | ISO 8601 timestamp of last successful sync |

### Content hashing: body-only diffing

Sync only tracks the **markdown body** of entry-point files (`SKILL.md` for skills, the agent `.md` file for agents), not their YAML frontmatter. The frontmatter is local configuration (model, tools, sandbox, permissions) that users customize per-project. The body is the actual content the source provides (prompt, instructions, domain knowledge).

**Scope of body-only diffing:** This split applies ONLY to the entry-point file of each item — `SKILL.md` for skills, and the single `.md` file for agents. Other `.md` files within a skill directory (supporting docs, templates, etc.) are treated as raw content — hashed and synced in full, including any frontmatter they may have. Only the entry-point file has the "frontmatter = local config" semantics.

This split is implemented using `python-frontmatter` (already a dependency):

```python
import frontmatter

post = frontmatter.load(path)
post.content    # ← tracked by sync (hashed, diffed)
post.metadata   # ← ignored by sync (user's local config)
```

**Why body-only for entry points?**
- Users can set `model`, `tools`, `sandbox`, `mcp`, `permission` in the frontmatter without triggering a sync conflict
- Source repo updates to the prompt/instructions are detected and applied
- Source repo changes to frontmatter metadata are ignored — the local project's config choices are preserved
- A user who disables a skill in their harness config (by editing frontmatter) won't get their changes overwritten on next sync

### Tree hash algorithm

Skills are directories (not single files). The tree hash provides a deterministic checksum for a directory's **body content**:

1. Enumerate all files in the directory recursively (excluding `.git/` and any symlinks, which are rejected).
2. Sort file paths lexicographically (using forward-slash separators, relative to the skill directory root).
3. For the entry-point file (`SKILL.md`), extract the markdown body via `frontmatter.load()` and compute `sha256(body)`. For all other files (including other `.md` files), compute `sha256(file_contents)` on raw bytes.
4. Concatenate: for each file in sorted order, append `"{relative_path}\0{hex_digest}\n"`.
5. Compute `sha256(concatenated_string)`.
6. Format as `"sha256:{hex_digest}"`.

For agents (single `.md` files), the tree hash is `sha256` of the extracted markdown body (not the raw file), formatted as `"sha256:{hex_digest}"`.

This algorithm is deterministic regardless of filesystem ordering, timestamps, or permissions. Frontmatter changes (local config) do not affect the hash.

### Update vs Upgrade behavior

- `meridian sync update`: for each source, if a `locked_commit` exists in the lock file, use it. Do NOT re-resolve the branch ref. This means `update` is reproducible — running it twice gives the same result. Use this after cloning a repo with an existing lock file.
- `meridian sync upgrade`: re-resolve floating refs (branches) to their current upstream commit. Tags already point to fixed commits and do not need upgrading. After upgrade, the lock file is updated with the new resolved commits.
- With `update`, the only way a locked commit changes is if the `ref` in config changes (e.g., from `v1.2.0` to `v1.3.0`), or if the lock entry does not yet exist for that source.

## 9. Conflict Detection and Resolution

Conflict detection prevents overwriting local edits. The lock file tree hash serves as the baseline. Tree hashes extract **body content only from entry-point files** (`SKILL.md` / agent `.md`) — their YAML frontmatter is excluded. All other files in the tree are hashed raw (see Content Hashing above).

This means:
- User edits entry-point frontmatter (model, tools, sandbox) → no conflict, sync ignores it
- User edits the entry-point markdown body → conflict detected, sync warns
- Source updates the markdown body → detected as upstream change
- Source changes frontmatter → ignored, local frontmatter preserved

### Decision matrix

| Destination exists? | Lock entry? | Lock hash vs local body | Source body hash vs lock | Action |
|---------------------|-------------|------------------------|------------------------|--------|
| No | No | -- | -- | **INSTALL**: copy from source, create lock entry |
| Yes | No | -- | -- | **CONFLICT (unmanaged)**: destination exists but is not managed by sync. Block unless `--force`. |
| Yes | Yes | Same | Same | **SKIP**: everything in sync |
| Yes | Yes | Same | Different | **UPDATE**: user did not edit body locally; safe to overwrite body. **Preserve local frontmatter.** Copy body from source, keep local frontmatter, update lock. |
| Yes | Yes | Different | Same | **SKIP (user-edited)**: user edited body locally, upstream unchanged. Leave it alone. |
| Yes | Yes | Different | Different | **CONFLICT (diverged)**: both local body and upstream body changed. Block unless `--force`. |
| No | Yes | -- | -- | **REINSTALL**: file was deleted locally but lock exists. Copy from source, update lock. |

### Edge cases

- **Unmanaged content**: If `.agents/skills/foo/` exists but has no lock entry, it is treated as a conflict. The user must `--force` to overwrite. This prevents accidentally destroying hand-written skills.
- **Force behavior**: `--force` overwrites in all conflict cases. The old lock entry (if any) is replaced with the new state.
- **Undo local edits**: Delete the file from `.agents/` and re-run `meridian sync update`. The REINSTALL row in the decision matrix handles "file missing + lock exists" — it copies from source and updates the lock.

## 10. Sync Algorithm

```
1. LOAD CONFIG
   a. If `install` subcommand: write new [[sync.sources]] entry to .meridian/config.toml first
      (error if source name already exists in config)
   b. Read [[sync.sources]] from .meridian/config.toml
   c. If `install`: filter to just the newly added source
      If --source flag: filter sources to that one name
   d. Validate: each source has repo XOR path, repo format, ref only with repo

2. FETCH SOURCES (skip if `status` subcommand)
   For each remote source:
   a. Compute cache dir: .meridian/cache/sync/{owner}-{repo}/
   b. Determine target ref:
      - If `upgrade` or `install`: use the ref from config (resolve to latest)
      - If `update` AND lock file has a locked_commit for this source AND config ref unchanged:
        use locked_commit (do not re-resolve)
      - If `update` AND no lock entry or config ref changed: resolve from upstream
   c. If cache dir does not exist: clone
        git clone https://github.com/{owner}/{repo}.git {cache_dir}
   d. If cache dir exists: fetch and checkout target
      - If using locked_commit (`update` with existing lock entry):
        git fetch origin  (ensure we have the commit)
        git checkout {locked_commit}  (detached HEAD at exact commit)
      - If `upgrade`/`install` or no lock entry:
        Branch: git fetch origin {branch} && git checkout FETCH_HEAD
        Tag: git fetch origin tag {tag} && git checkout tags/{tag}
   e. Record resolved commit: git rev-parse HEAD
   NOTE: We use full clones (not --depth 1) because locked commits may not
   be at branch tips. Shallow clones cannot checkout arbitrary commits.
   The repos are markdown-only, so full clones are still small.
   For local sources:
   f. Resolve path relative to repo root (or absolute)
   g. Validate path exists

3. DISCOVER ITEMS
   For each source's resolved directory:
   a. Skills: scan skills/*/SKILL.md -- each matching directory is a skill
   b. Agents: scan agents/*.md -- each matching file is an agent
   c. Apply include filter: if config has skills/agents lists, intersect.
      - skills = None (omitted): include all discovered skills
      - skills = () (empty array): include no skills
      - skills = ("foo", "bar"): include only those names
      NOTE: include/exclude filters use SOURCE names (before rename).
   d. Same for agents.
   e. Apply exclude filter: remove any items in exclude_skills/exclude_agents.
      Exclude is applied after include, so you can do "sync all except X".
   f. Apply rename map: for each remaining item, if its source name is a key
      in the rename dict, use the mapped value as the local (destination) name.
      Record both source_item_name and local_name for lock entry.

4. CHECK CROSS-SOURCE COLLISIONS
   Build a map of (item_kind, local_name) -> source_name.
   Uses RENAMED names (destination names), not source names.
   If any item appears in two or more sources: hard error with clear message.

5. PRE-FLIGHT: CHECK .claude/ CONFLICTS
   Before mutating anything, check all destinations in .claude/ for unmanaged conflicts:
   a. For each discovered item, check if .claude/{skills,agents}/{name} exists
   b. If it exists as a real file/directory (not a sync-managed symlink pointing to .agents/):
      - Record as unmanaged conflict
      - Block that item unless --force
   This runs before any writes, so .agents/ is never mutated for an item
   that would fail at the .claude/ symlink step.

6. APPLY (for each discovered item that passed pre-flight)
   a. Read lock entry from .meridian/sync.lock (if exists)
   b. Compute source tree hash (from cache dir or local path; body-only for entry-point .md, raw for all other files)
   c. Compute local tree hash (from .agents/ destination, if exists; same entry-point-only body extraction)
   d. Consult decision matrix (see section 9)
   e. If action is INSTALL or REINSTALL (or CONFLICT with --force):
      - Copy source files to temp directory adjacent to destination
      - Use shutil.copytree for skills (directories):
        * ignore callback to skip .git/ dirs
        * copy_function=shutil.copy2 to preserve metadata
        * Reject symlinks: if any symlink encountered, raise error and abort this item
        * Reject path traversal: if any file path escapes the skill directory, raise error
      - For agents (single files):
        * Reject if source path is a symlink
        * Use shutil.copy2 to temp file
      - Atomic swap into .agents/:
        * For directories (skills): if dest exists, rename dest to a backup path,
          then os.rename(temp, dest), then shutil.rmtree(backup). If rename fails,
          restore backup. (os.replace does not work on non-empty dirs on Linux.)
        * For single files (agents): os.replace(temp, dest) works directly.
      - Create symlink in .claude/ pointing to .agents/ item (pre-flight already confirmed no conflict)
      - Update lock entry in memory
   g. If action is UPDATE:
      - Build a complete temp tree from the source
      - For the entry-point file only (SKILL.md for skills, the .md file for agents):
        * If the local entry-point exists:
          Read local file as raw text, split frontmatter from body using `python-frontmatter`
          Read source file as raw text, split frontmatter from body
          Splice: preserve local raw frontmatter block + substitute source body
          (Use raw text splicing, not frontmatter.dumps(), to preserve formatting and comments)
        * If the local entry-point does not exist (was deleted): use source file as-is
      - All other files (including non-entry-point .md files): copy from source directly
      - Files that exist locally but not in source: removed (source is authoritative for non-entry-point files)
      - Files that exist in source but not locally: added
      - Atomic swap of the entire directory into .agents/
      - Create/update symlink in .claude/ pointing to .agents/ item
      - Update lock entry in memory
   h. If action is SKIP: no-op
   i. If action is CONFLICT (without --force): record conflict, continue

7. PRUNE PHASE
   After applying all sources:
   a. Build set of "desired items" from step 3 discovery (post-include/exclude filtering)
   b. Iterate all lock entries
   c. An entry is orphaned if ANY of:
      - source_name is NOT in the merged config (source removed)
      - source_name exists but item is no longer in the discovered set
        (upstream removed it, or include/exclude filters now exclude it)
   d. For each orphaned entry:
      - If --prune flag:
        * Compute current local tree hash
        * If local matches lock tree_hash: safe to remove (user did not edit). Delete from .agents/ and remove .claude/ symlink. Remove lock entry.
        * If local differs from lock tree_hash: user edited. Warn but do NOT delete. Remove lock entry but keep files.
      - If no --prune flag: warn only ("orphaned: skills/foo from source 'old-source' -- use --prune to remove")

8. WRITE LOCK FILE
   Write the final lock file state (all updates accumulated in memory during step 6 and 7).
   Atomic write: serialize to JSON, write to .meridian/sync.lock.tmp, os.replace to .meridian/sync.lock.

   NOTE: The flock (see lock.py) must be held for the ENTIRE sync operation
   (steps 1-9), not just the lock file write. This prevents two concurrent
   sync runs from racing their filesystem mutations against `.agents/`.
   The lock_file_guard context manager wraps the full sync, not individual steps.

9. REPORT RESULTS
   - Installed: N new items
   - Updated: M items
   - Skipped: K items (in sync or user-edited)
   - Conflicts: J blocked (list each with source, destination, reason)
   - Orphaned: P items (with/without prune)
   - Errors: E failed sources (network failures, validation errors)
   For each item, surface provenance: source name, repo/path, commit SHA.

10. EXIT CODE
   - 0: all requested syncs succeeded, no conflicts
   - 1: unexpected error (crash, permission denied, etc.)
   - 2: conflicts blocked (some items could not be synced without --force)
   - 3: partial failure (some sources failed to fetch, others succeeded)
```

## 11. Error Handling

### Network failures

- **Per-source failure isolation**: If a remote source fails to fetch, skip it with a warning and continue with other sources. Return nonzero exit code (3) if any requested source failed.
- **First-time clone failure**: If `git clone` fails, remove the partial cache directory to avoid leaving corrupt state.
- **Timeout**: Git operations inherit the process timeout. No custom timeout in v1.
- **Local path TOCTOU**: For local path sources, the source could change between hash computation and file copy. Mitigation: compute the tree hash from the *copied* content (the temp tree), not the source. This ensures the lock hash always matches what was actually installed.

### Validation errors

- **Invalid config**: Fail fast with clear error message. Do not partially sync.
- **Missing source directory**: If a local path source does not exist, skip with error, continue with others.
- **Missing skills/agents subdirectory**: If source has neither `skills/` nor `agents/`, warn and skip (the source may be empty or structured differently).
- **Filter references nonexistent item**: If config filters to `skills = ["foo"]` but the source has no skill named "foo", warn (not error) -- the filter simply yields nothing for that name.

### Copy errors

- **Symlink detected**: Hard error for that item. Log which file is a symlink, skip the item, continue with others.
- **Path traversal detected**: Hard error for that item. Log the offending path, skip the item.
- **Permission denied on destination**: Hard error for that item with clear message.
- **Atomic rename failure**: If `os.replace` fails, leave the temp directory for debugging. Log the temp path.

## 12. Security

- **Provenance in output**: Every sync operation logs the source name, repo/path, and resolved commit SHA. The lock file permanently records this provenance.
- **Symlink rejection**: During copy, reject any symlinks encountered in source content. Symlinks can escape the intended directory boundary.
- **Path traversal rejection**: Validate that all files within a skill directory are actually contained within it. Reject any path component that is `..` or resolves outside the skill root.
- **No code execution**: Sync only copies files. It never executes scripts, hooks, or post-install commands from source repos.

## 13. Files to Create / Change

| File | Purpose |
|------|---------|
| `src/meridian/lib/sync/config.py` | `SyncSourceConfig`, `SyncConfig` Pydantic models; config read/write (TOML append for `install`, remove for `remove`) |
| `src/meridian/lib/sync/lock.py` | `SyncLockEntry`, `SyncLockFile` models; lock file read/write with flock |
| `src/meridian/lib/sync/cache.py` | Source resolution: clone, fetch, checkout; cache directory management |
| `src/meridian/lib/sync/hash.py` | Tree hash algorithm for skills (directories) and agents (files) |
| `src/meridian/lib/sync/engine.py` | Core sync engine: discover, diff, apply, prune. Pydantic I/O models for results |
| `src/meridian/lib/sync/__init__.py` | Public API surface |
| `src/meridian/cli/sync_cmd.py` | CLI handler with `register_sync_commands(sync_app, emit)` following existing pattern |
| `src/meridian/cli/main.py` | Register `sync_app` as top-level command |
| `src/meridian/lib/state/paths.py` | Add `sync_lock_path` and `sync_cache_dir` to `StatePaths` |
| `tests/lib/sync/` | Test files for each module |

### Config models (`sync/config.py`)

Two frozen Pydantic models:

- **`SyncSourceConfig`** — one named sync source with fields: `name`, `repo | path` (XOR), `ref`, `skills`, `agents`, `exclude_skills`, `exclude_agents`, `rename` (dict[str, str]). Validators enforce: non-empty name (alphanumeric/hyphens/underscores), `owner/repo` format for repo, `repo` XOR `path`, `ref` only with `repo`, non-empty filter entries, non-empty rename keys/values.
- **`SyncConfig`** — wraps `sources: tuple[SyncSourceConfig, ...]` with unique-name validation.
- **`load_sync_config(config_path) -> SyncConfig`** — reads `[[sync.sources]]` from TOML, returns empty `SyncConfig` if file missing.

### Lock file models (`sync/lock.py`)

- **`SyncLockEntry`** (frozen) — provenance record per synced item: `source_name`, `source_type`, `source_value`, `source_item_name`, `requested_ref`, `locked_commit`, `item_kind`, `dest_path`, `tree_hash`, `synced_at`.
- **`SyncLockFile`** (mutable) — `version: int = 1`, `items: dict[str, SyncLockEntry]`. Not frozen because the engine mutates `items` in-place during sync.
- **`read_lock_file(lock_path) -> SyncLockFile`** — parse JSON, return empty lock if missing.
- **`write_lock_file(lock_path, lock)`** — atomic write via tmp + `os.replace`.
- **`lock_file_guard(lock_path)`** — context manager, `fcntl.flock` on a `.flock` sidecar file.

### Path additions (`paths.py`)

Add to `StatePaths`:

```python
class StatePaths(BaseModel):
    """Resolved on-disk Meridian state paths."""

    model_config = ConfigDict(frozen=True)

    root_dir: Path
    artifacts_dir: Path
    spawns_dir: Path
    all_spaces_dir: Path
    active_spaces_dir: Path
    cache_dir: Path
    config_path: Path
    models_path: Path
    sync_lock_path: Path       # NEW: .meridian/sync.lock
    sync_cache_dir: Path       # NEW: .meridian/cache/sync/
```

Update `resolve_state_paths`:

```python
def resolve_state_paths(repo_root: Path) -> StatePaths:
    root_dir = _resolve_state_root(repo_root)
    return StatePaths(
        root_dir=root_dir,
        artifacts_dir=root_dir / "artifacts",
        spawns_dir=root_dir / "spawns",
        all_spaces_dir=root_dir / _SPACES_DIR,
        active_spaces_dir=root_dir / "active-spaces",
        cache_dir=root_dir / "cache",
        config_path=root_dir / "config.toml",
        models_path=root_dir / "models.toml",
        sync_lock_path=root_dir / "sync.lock",
        sync_cache_dir=root_dir / "cache" / "sync",
    )
```

## 14. Scope

### v1 (this plan)

- Project-local config and cache (`.meridian/config.toml`, `.meridian/cache/sync/`)
- Remote (GitHub) and local path sources
- Skills (directories) AND agents (single files)
- Multiple named sources in config with include/exclude filters
- Nix-inspired lock file with requested ref + resolved commit SHA + tree hashes
- Body-only diffing: entry-point YAML frontmatter (model, tools, sandbox) is local config, ignored by sync
- Conflict detection: lock hash vs local body vs source body, with unmanaged file protection
- Pre-flight `.claude/` conflict check before any writes
- Per-item symlinks from `.claude/` to `.agents/` for Claude Code discoverability
- `install`, `remove`, `update`, `upgrade`, `status` subcommands
- Item renaming via `--rename` flag and `rename` config field
- `--force`, `--dry-run`, `--source`, `--prune` flags
- Cross-source name collision detection (hard error)
- Symlink and path traversal rejection in source content
- Per-source network failure isolation
- `fcntl.flock` concurrency protection over entire sync operation
- Branches and tags only for ref types; commit SHA pinning is future
- CLI-only -- not exposed via MCP, not added to ops manifest

### Future

- `meridian sync restore` (revert local edits to match lock state)
- Permission warnings for agent profiles declaring tool/sandbox access
- Stale cache fallback (use local cache when fetch fails)
- Global `~/.meridian/config.toml` for user-level sync sources shared across projects
- Commit SHA pinning (`ref = "a1b2c3d..."` targeting exact commits)
- `meridian sync --locked` for CI (fail if lock file would change, a la `cargo install --locked`)
- Push direction (local edits back to source repo)
- `meridian sync diff` (show content diffs between local and upstream)
- Version pinning with `ref` per-skill (not just per-source)
- Auto-sync on `git checkout` (hook integration)
- Private repo auth handling (SSH keys, tokens)

## 15. Implementation Order

Each step is independently testable. Commit after each step passes tests.

| Step | Description | Scope | Dependencies |
|------|-------------|-------|-------------|
| 1 | **Config models and I/O** | `src/meridian/lib/sync/config.py` -- `SyncSourceConfig`, `SyncConfig`, `load_sync_config()`, `add_sync_source()`, `remove_sync_source()`. TOML parsing and writing for `[[sync.sources]]`. Full validation including rename maps. | None |
| 2 | **Tree hash algorithm** | `src/meridian/lib/sync/hash.py` -- `compute_tree_hash(path)` for directories (skills) and files (agents). Entry-point body extraction. Symlink detection. | None |
| 3 | **Lock file model and I/O** | `src/meridian/lib/sync/lock.py` -- `SyncLockEntry`, `SyncLockFile`, read/write with atomic tmp+rename, `fcntl.flock` guard. | None |
| 4 | **State path additions** | `src/meridian/lib/state/paths.py` -- Add `sync_lock_path`, `sync_cache_dir` to `StatePaths`. | None |
| 5 | **Source/cache manager** | `src/meridian/lib/sync/cache.py` -- Clone, fetch, checkout (branch vs tag strategies). Cache directory lifecycle (create, update, cleanup on failed clone). | Steps 1, 4 |
| 6 | **Sync engine** | `src/meridian/lib/sync/engine.py` -- Discovery, collision check, pre-flight `.claude/` check, diff (decision matrix), apply (copy + symlink with security checks), prune. Pydantic result models. | Steps 1-5 |
| 7 | **CLI wiring** | `src/meridian/cli/sync_cmd.py`, `src/meridian/cli/main.py` -- Register `sync` command group with `install`, `remove`, `update`, `upgrade`, `status` subcommands. Wire all flags. | Step 6 |

Steps 1-4 have no dependencies on each other and can be developed in parallel. Steps 5-6-7 are sequential.
