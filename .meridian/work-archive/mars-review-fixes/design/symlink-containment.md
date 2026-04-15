# F1 + F3: Symlink Containment

## F1: Managed Root Escape via Symlink

### Problem

`MarsContext::new` canonicalizes `managed_root`, then derives `project_root = managed_root.parent()`. If `.agents/` is a symlink to `/tmp/evil/agents/`, canonicalization resolves it to `/tmp/evil/agents/`, and `project_root` becomes `/tmp/evil/`. All operations then target the wrong project.

Similarly, `--root /tmp/evil/agents` lets a user (or script) point mars at an arbitrary directory, making `project_root = /tmp/evil/`.

### Analysis

The `project_root` is used for:
1. Link target resolution (`ctx.project_root.join(&target_name)`) — creates symlinks relative to the derived project root
2. Local path source resolution — resolves relative source paths against project root

Both are dangerous if project_root escapes the real project.

### Design: Containment Check in find_agents_root

Add a post-canonicalize validation in `find_agents_root` for auto-discovered roots:

```rust
pub fn find_agents_root(explicit: Option<&Path>) -> Result<MarsContext, MarsError> {
    if let Some(root) = explicit {
        // User explicitly chose this root — trust it
        return MarsContext::new(root.to_path_buf());
    }

    let cwd = std::env::current_dir()?;
    // Canonicalize cwd to resolve ancestor symlinks
    let cwd_canon = cwd.canonicalize().unwrap_or_else(|_| cwd.clone());
    let mut dir = cwd_canon.as_path();

    loop {
        for subdir in WELL_KNOWN.iter().chain(TOOL_DIRS.iter()) {
            let candidate = dir.join(subdir);
            if candidate.join("mars.toml").exists() {
                let ctx = MarsContext::new(candidate)?;
                // Validate: canonical managed_root should be under the directory we found it in
                if !ctx.managed_root.starts_with(dir) {
                    return Err(MarsError::Config(ConfigError::Invalid {
                        message: format!(
                            "{}/{} resolves to {} which is outside {}. \
                             The managed root may be a symlink. Use --root to override.",
                            dir.display(), subdir, ctx.managed_root.display(),
                            dir.display(),
                        ),
                    }));
                }
                return Ok(ctx);
            }
        }

        if dir.join("mars.toml").exists() {
            return MarsContext::new(dir.to_path_buf());
        }

        match dir.parent() {
            Some(parent) => dir = parent,
            None => break,
        }
    }

    // ... existing error ...
}
```

**Key change from initial design (per review S1):** Canonicalize `cwd` before the walk-up loop. Without this, if `cwd` itself is under a symlink (e.g., `/projects/myproject` → `/tmp/evil/myproject`), the containment check passes because the walk-up directory matches the canonical managed root — both resolve through the same symlink. Canonicalizing cwd first means the walk-up operates on real paths, so `.agents/` symlinks pointing outside the real cwd tree are caught.

**Known limitation:** If both `.agents/` AND an ancestor directory are symlinked to the same external location, the containment check passes because the canonical paths are consistent. This is a contrived scenario — documenting it is sufficient.

### `--root` Bypass

When the user passes `--root`, the containment check is skipped. This is intentional:
- **Use case:** CI scripts, editor integrations, and cross-project tooling may legitimately point mars at directories outside cwd
- **Precedent:** `git --work-tree` and `git --git-dir` allow the same kind of override
- The user is explicitly taking responsibility for the root choice

## F3: Symlink Following in check/doctor Scanning

### Problem

Both `check.rs` and `doctor.rs` scan `agents/` and `skills/` directories, reading files and parsing frontmatter. If a skill directory is a symlink to `/etc/` or a huge external tree, the scan follows it without bounds.

### Design: Symlink-Aware Scanning with Different Policies

**Per review S3:** `check` and `doctor` have different semantics and need different symlink policies.

#### check.rs: Skip + Warn (source validation)

`mars check` validates a source package before publishing. Symlinks in a published package are suspicious — they create dependencies on the consumer's filesystem layout. Skip and warn.

```rust
// In check.rs scanning loops:
if entry.path().symlink_metadata()
    .map(|m| m.file_type().is_symlink())
    .unwrap_or(false)
{
    warnings.push(format!(
        "skipping symlinked {} `{}` — source packages should not contain symlinks",
        kind, name
    ));
    continue;
}
```

#### doctor.rs: Skip Unexpected Symlinks, Validate Known Links

`mars doctor` validates installed state. Mars itself creates symlinks via `mars link` — doctor already validates those through `check_link_health()`. The new symlink scanning should only skip **unexpected** symlinks — entries inside `agents/` or `skills/` that are symlinks (not the top-level link dirs which are handled separately).

```rust
// In doctor.rs agent/skill scanning:
// Skip symlinked individual entries within agents/ and skills/
// (Mars doesn't create individual symlinks — only top-level dir links)
if entry.path().symlink_metadata()
    .map(|m| m.file_type().is_symlink())
    .unwrap_or(false)
{
    issues.push(format!(
        "skipping symlinked {} `{}` — individual symlinks in managed dirs are not supported",
        kind, name
    ));
    continue;
}
```

The existing `check_link_health` function validates top-level symlinks (`.claude/agents → .agents/agents`). The new code handles individual files/dirs within the scanned directories. These are orthogonal — no conflict.

### link.rs: Symlinks in Target Dir Are Informational

**Per review S5:** Treating symlinks in the target dir as conflicts is hostile UX. A user might organize agents with symlinks (`.claude/agents/my-agent.md → ../custom/agent.md`).

Change: use `.follow_links(false)` for safety, but report symlinks as informational (logged but not blocking), not as conflicts:

```rust
for entry in walkdir::WalkDir::new(target_subdir)
    .follow_links(false)
    .into_iter()
    .filter_map(|e| e.ok())
{
    if entry.file_type().is_symlink() {
        // Symlinks are skipped — not followed, not treated as conflicts
        // They survive the merge-and-link process since we only remove regular files
        continue;
    }
    // ... existing logic for regular files ...
}
```

### Shared Helper

**Per review S6:** Add a shared helper used by both check.rs and doctor.rs to avoid immediate divergence:

```rust
// src/cli/mod.rs or a small utility module
/// Check if a directory entry is a symlink using symlink_metadata.
pub fn is_symlink(path: &Path) -> bool {
    path.symlink_metadata()
        .map(|m| m.file_type().is_symlink())
        .unwrap_or(false)
}
```

Both check.rs and doctor.rs import and use this helper. The policy logic (warn text, error vs warning) stays in each command.

## Files to Modify

### Phase 4a: Containment (mod.rs only)
- `src/cli/mod.rs` — canonicalize cwd + containment check in `find_agents_root()`, ~15 lines
- Add test: symlinked `.agents/` outside project → error

### Phase 4b: Symlink-Aware Scanning (check.rs, doctor.rs, link.rs)
- `src/cli/mod.rs` — add `is_symlink()` helper, 5 lines
- `src/cli/check.rs` — symlink skip+warn in agent and skill scanning, ~10 lines
- `src/cli/doctor.rs` — symlink skip+warn in agent and skill scanning, ~10 lines
- `src/cli/link.rs` — `.follow_links(false)` and skip symlinks in `scan_dir_recursive`, ~5 lines
- Add tests for each scanning command

## Verification

- `cargo test` passes
- `mars check` with a symlinked skill dir → warns and skips
- `mars doctor` with a symlinked agent file → warns and skips
- `mars doctor` with a valid linked installation → still validates link health
- `mars link` with symlinks in target dir → ignores them, doesn't block
- Normal operations unchanged
