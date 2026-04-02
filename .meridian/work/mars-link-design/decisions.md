# Decisions Log

## D1: TARGET is a name, not a path

**Context**: Init's positional arg had a dot-prefix heuristic (`path_str.starts_with('.')`) to distinguish target dirs from project roots. This misclassified `./my-project` and `.hidden-project/`.

**Decision**: TARGET is a simple directory name (no `/` allowed). Path-based init uses `--root`.

**Alternatives rejected**:
- Keep heuristic but fix edge cases — fragile, every new case needs a rule
- Remove positional arg entirely, always use `--root` — poor ergonomics for the common case

**Evidence**: Every CLI tool surveyed (git init, cargo init, uv init) treats the path arg as "init IN this directory" with no heuristic disambiguation.

## D2: Separate WELL_KNOWN and TOOL_DIRS

**Context**: WELL_KNOWN was local to `find_agents_root`. Reviewer p665 recommended extracting to module-level shared constant. Question: should `.cursor` and `.claude` be in WELL_KNOWN?

**Decision**: Two separate constants. WELL_KNOWN = `[".agents"]` (mars's conventional root). TOOL_DIRS = `[".claude", ".cursor"]` (tool directories that commonly need linking). Root detection searches both.

**Alternatives rejected**:
- Single `KNOWN_DIRS` array — loses the semantic distinction. Init uses WELL_KNOWN for defaults, link uses TOOL_DIRS for warnings. Merging them removes useful information.
- Configurable via agents.toml — over-engineering for v1. Can add later if needed.

## D3: Lightweight mutate_config instead of full sync pipeline for link mutations

**Context**: Reviewer p665 flagged that `persist_link()` bypasses sync.lock. Options: route through `sync::execute` with a `mutation_only` flag, or extract a lightweight function.

**Decision**: Extract `sync::mutate_config(root, mutation)` — acquires sync.lock, loads config, applies mutation, saves. Reuses `ConfigMutation` enum and `apply_mutation` function.

**Alternatives rejected**:
- Full sync pipeline with `mutation_only: true` — adds a flag to SyncOptions that only link uses, couples link to the full pipeline's validation stages, and runs unnecessary code (resolve, fetch, diff)
- Direct load/save with manual lock acquisition in link.rs — duplicates the lock pattern, doesn't use ConfigMutation enum

## D4: Scan-then-act for conflict resolution

**Context**: Need to handle existing files in target dirs. Question: scan all then act, or scan-and-act per file?

**Decision**: Scan ALL subdirs and files first, then act only if zero conflicts. The entire link operation is all-or-nothing at the scan boundary.

**Alternatives rejected**:
- Per-file scan-and-act — partial state on conflict (some files moved, some not). Harder to reason about, harder to recover from.
- Backup-and-restore — additional complexity, temp dir management, still has partial state during restore if that fails

## D5: Init idempotency — no-op + proceed with --link

**Context**: Current init errors when agents.toml already exists. But `mars init --link .claude` should work on an existing project.

**Decision**: If already initialized, print info and proceed with `--link` flags. Init itself is idempotent; linking is the useful action on re-runs.

**Alternatives rejected**:
- Always error — forces users to run `mars link` separately, making `--link` useless on established projects
- Re-initialize (overwrite) — destroys existing config

## D6: Unlink verifies symlink target before removing

**Context**: Current unlink removes any symlink without checking what it points to.

**Decision**: Only remove symlinks that resolve to THIS mars root (via canonicalize comparison). Warn and skip symlinks pointing elsewhere.

**Rationale**: Prevents accidentally breaking symlinks managed by a different tool or a different mars installation. The user can always use `rm` directly if they need to force-remove.
