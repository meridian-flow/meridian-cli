# Link Command — Conflict-Aware Symlink Management

## Interface

```
mars link <DIR> [--force] [--unlink]
```

- **DIR** — Target directory name (e.g. `.claude`). Resolved relative to project root.
- **--force** — Replace whatever exists with symlinks. Data may be lost.
- **--unlink** — Remove symlinks. Only removes if they point to THIS mars root.

## Conflict Resolution Algorithm

The core safety property: **if any conflict exists, zero filesystem mutations occur.** The algorithm is scan-then-act with two distinct phases.

### Phase 1: Scan (read-only)

For each subdirectory to link (`agents/`, `skills/`):

```rust
enum ScanResult {
    /// Nothing at the link path — create symlink
    Empty,
    /// Already a symlink pointing to our managed root
    AlreadyLinked,
    /// Symlink pointing somewhere else
    ForeignSymlink { target: PathBuf },
    /// Real directory with no conflicts against managed root
    MergeableDir { files_to_move: Vec<PathBuf> },
    /// Real directory with conflicts (same filename, different content)
    ConflictedDir { conflicts: Vec<ConflictInfo> },
}

struct ConflictInfo {
    /// Relative path within the subdir (e.g. "reviewer.md")
    relative_path: PathBuf,
    /// What exists in the target dir
    target_hash: String,
    /// What exists in the managed root
    managed_hash: String,
}
```

For each file in the target's subdir (e.g. `.claude/agents/reviewer.md`):
1. Does the same relative path exist in the managed root (e.g. `.agents/agents/reviewer.md`)?
2. If no → file is unique, can be moved (mergeable)
3. If yes, are contents identical? → skip (already present)
4. If yes but different content → **conflict**

This uses the existing `crate::hash` module for content comparison — same hash function used by the sync pipeline for checksum verification.

### Phase 2: Act (all-or-nothing)

After scanning ALL subdirs, check results:

```
if any ScanResult is ConflictedDir or ForeignSymlink:
    print all conflicts
    return Error (exit 1, zero mutations)

for each subdir:
    match scan_result:
        Empty → create symlink
        AlreadyLinked → skip (print info)
        MergeableDir → move files into managed root, remove dir, create symlink
        ConflictedDir → unreachable (caught above)
        ForeignSymlink → unreachable (caught above)

persist link in settings
```

### Atomicity of Merge

When moving files from target dir to managed root (MergeableDir case):

1. Move each file: `rename(target_dir/agents/foo.md, managed_root/agents/foo.md)`
2. Verify target subdir is empty after moves
3. Remove empty target subdir
4. Create symlink

If any move fails mid-way, we're in a partially-moved state. This is acceptable because:
- Files that moved are now in the managed root (correct final location)
- Files that didn't move are still in the target dir (still accessible)
- Re-running `mars link` will continue where it left off (idempotent scan)

The scan phase prevents the dangerous case (overwriting different content) — once we're in the act phase, we know every move is safe.

### Recursive Directory Handling

Both `agents/` and `skills/` can contain nested directories (skills are directory-based: `skills/my-skill/SKILL.md`). The scan and merge operate recursively:

```rust
fn scan_dir_recursive(
    target_subdir: &Path,    // e.g. .claude/skills/
    managed_subdir: &Path,   // e.g. .agents/skills/
) -> ScanResult {
    let mut files_to_move = Vec::new();
    let mut conflicts = Vec::new();

    for entry in walk_dir(target_subdir) {
        let relative = entry.strip_prefix(target_subdir);
        let managed_path = managed_subdir.join(&relative);

        if !managed_path.exists() {
            files_to_move.push(relative);
        } else if same_content(&entry, &managed_path) {
            // Identical — skip
        } else {
            conflicts.push(ConflictInfo { relative_path: relative, ... });
        }
    }

    if !conflicts.is_empty() {
        ScanResult::ConflictedDir { conflicts }
    } else if !files_to_move.is_empty() {
        ScanResult::MergeableDir { files_to_move }
    } else {
        // All files identical — dir can be removed
        ScanResult::MergeableDir { files_to_move: vec![] }
    }
}
```

## Unlink

```rust
fn unlink(ctx: &MarsContext, target_name: &str, target_dir: &Path, json: bool) -> Result<i32, MarsError> {
    let mut removed = 0;

    for subdir in ["agents", "skills"] {
        let link_path = target_dir.join(subdir);

        if let Ok(link_target) = link_path.read_link() {
            // Resolve the symlink target to absolute and compare
            let resolved = target_dir.join(&link_target);
            let expected = ctx.managed_root.join(subdir);

            if resolved.canonicalize().ok() == expected.canonicalize().ok() {
                std::fs::remove_file(&link_path)?;
                removed += 1;
            } else {
                // Symlink points elsewhere — warn but don't remove
                if !json {
                    output::print_warn(&format!(
                        "{}/{subdir} is a symlink to {} (not this mars root) — skipping",
                        target_name,
                        link_target.display()
                    ));
                }
            }
        }
    }

    // Remove from settings (via ConfigMutation under lock)
    // ... see config-mutations.md

    Ok(0)
}
```

**Key change from current**: Verifies the symlink actually points to THIS mars root before removing. Prevents accidentally removing symlinks managed by a different mars installation.

## --force

When `--force` is passed, the scan phase still runs but ConflictedDir and ForeignSymlink are treated as actionable rather than error conditions:

- **ConflictedDir**: Remove the target subdir entirely, create symlink. Conflicting files in the target dir are lost.
- **ForeignSymlink**: Remove the symlink, create new one pointing to our root.

The user explicitly asked for this — data loss is acknowledged.

## Error Reporting

When conflicts prevent linking, the error output lists every conflict:

```
error: cannot link .claude — 2 conflicts found:

  agents/reviewer.md
    .claude/agents/reviewer.md  (sha256: a1b2c3...)
    .agents/agents/reviewer.md  (sha256: d4e5f6...)

  skills/review/SKILL.md
    .claude/skills/review/SKILL.md  (sha256: 789abc...)
    .agents/skills/review/SKILL.md  (sha256: def012...)

hint: resolve conflicts manually, then retry `mars link .claude`
hint: or use `mars link .claude --force` to replace with symlinks (data loss)
```

JSON output includes structured conflict data:

```json
{
    "ok": false,
    "conflicts": [
        {
            "path": "agents/reviewer.md",
            "target_hash": "a1b2c3...",
            "managed_hash": "d4e5f6..."
        }
    ]
}
```

## Relative Symlinks

Symlinks use relative paths computed via `pathdiff::diff_paths`:

```
.claude/agents -> ../.agents/agents
.claude/skills -> ../.agents/skills
```

Relative symlinks survive repository moves and clones. The current implementation already does this correctly.

## Full Scenario Matrix

| # | State of `.claude/agents/` | Action | Result |
|---|---|---|---|
| 1 | Doesn't exist | Create symlink | `.claude/agents -> ../.agents/agents` |
| 2 | Symlink → `../.agents/agents` | No-op | Print "already linked" |
| 3 | Symlink → `/other/path/agents` | Error | "symlink points to /other/path/agents" |
| 4 | Dir with unique files | Move files, create symlink | Files preserved in `.agents/agents/` |
| 5 | Dir with identical files | Remove dir, create symlink | No data loss |
| 6 | Dir with conflicting files | Error, zero mutations | Print all conflicts |
| 7 | Any of 3/6 + `--force` | Replace with symlink | Data may be lost |
