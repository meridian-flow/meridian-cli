# Phase 4: Link Command Redesign — Conflict Resolution

**Design refs**: [link.md](../design/link.md), [error-model.md](../design/error-model.md)

## Scope

Rewrite `link.rs` to implement the conflict-aware scan-then-act algorithm. This is the core feature phase — the most complex logic and highest risk.

## Files to Modify

- `src/cli/link.rs` — Full rewrite of `run()`, `unlink()`, and supporting functions. Add conflict scanning, merge logic, `--force` flag, and improved error reporting.

## Interface Contract

### LinkArgs (updated)

```rust
#[derive(Debug, clap::Args)]
pub struct LinkArgs {
    /// Target directory to create symlinks in (e.g. `.claude`).
    pub target: String,

    /// Remove symlinks instead of creating them.
    #[arg(long)]
    pub unlink: bool,

    /// Replace whatever exists with symlinks. Data may be lost.
    #[arg(long)]
    pub force: bool,
}
```

### ScanResult (new internal type)

```rust
enum ScanResult {
    Empty,
    AlreadyLinked,
    ForeignSymlink { target: PathBuf },
    MergeableDir { files_to_move: Vec<PathBuf> },
    ConflictedDir { conflicts: Vec<ConflictInfo> },
}

struct ConflictInfo {
    relative_path: PathBuf,
    target_hash: String,
    managed_hash: String,
}
```

## Algorithm Implementation

### run() Flow

```rust
pub fn run(args: &LinkArgs, ctx: &MarsContext, json: bool) -> Result<i32, MarsError> {
    if args.unlink {
        return unlink(ctx, &args.target, json);
    }

    let target_name = normalize_link_target(&args.target)?;
    let target_dir = ctx.project_root.join(&target_name);

    // Acquire sync lock for the entire operation (scan + act + persist)
    // Prevents races with concurrent mars sync or mars link
    let lock_path = ctx.managed_root.join(".mars").join("sync.lock");
    let _sync_lock = crate::fs::FileLock::acquire(&lock_path)?;

    // Create target directory if needed
    std::fs::create_dir_all(&target_dir)?;

    // Ensure managed subdirs exist
    for subdir in ["agents", "skills"] {
        let source = ctx.managed_root.join(subdir);
        if !source.exists() {
            std::fs::create_dir_all(&source)?;
        }
    }

    // Phase 1: Scan all subdirs
    let rel_root = pathdiff::diff_paths(&ctx.managed_root, &target_dir)
        .unwrap_or_else(|| ctx.managed_root.clone());
    let mut scan_results = Vec::new();
    let mut all_conflicts = Vec::new();
    let mut has_foreign = false;

    for subdir in ["agents", "skills"] {
        let link_path = target_dir.join(subdir);
        let link_target = rel_root.join(subdir);
        let managed_subdir = ctx.managed_root.join(subdir);

        let result = scan_link_target(&link_path, &link_target, &managed_subdir);
        match &result {
            ScanResult::ConflictedDir { conflicts } => {
                all_conflicts.extend(conflicts.iter().map(|c| (subdir, c.clone())));
            }
            ScanResult::ForeignSymlink { .. } => {
                has_foreign = true;
            }
            _ => {}
        }
        scan_results.push((subdir, link_path, link_target, result));
    }

    // Check: any conflicts or foreign symlinks? (unless --force)
    if !args.force && (!all_conflicts.is_empty() || has_foreign) {
        // Print detailed error, return exit 1
        print_conflicts(&target_name, &all_conflicts, &scan_results, json);
        return Err(MarsError::Link {
            target: target_name,
            message: "conflicts found — resolve manually or use --force".to_string(),
        });
    }

    // Phase 2: Act
    let mut linked = 0;
    for (subdir, link_path, link_target, result) in scan_results {
        match result {
            ScanResult::Empty => {
                create_symlink(&link_path, &link_target)?;
                linked += 1;
            }
            ScanResult::AlreadyLinked => {
                if !json { output::print_info(&format!("{target_name}/{subdir} already linked")); }
            }
            ScanResult::MergeableDir { files_to_move } => {
                let managed_subdir = ctx.managed_root.join(subdir);
                merge_and_link(&link_path, &link_target, &managed_subdir, &files_to_move)?;
                linked += 1;
            }
            ScanResult::ForeignSymlink { .. } | ScanResult::ConflictedDir { .. } => {
                // Only reachable with --force
                if link_path.symlink_metadata().is_ok() {
                    if link_path.read_link().is_ok() {
                        std::fs::remove_file(&link_path)?;
                    } else {
                        std::fs::remove_dir_all(&link_path)?;
                    }
                }
                create_symlink(&link_path, &link_target)?;
                linked += 1;
            }
        }
    }

    // Persist link in config (already under sync lock from above)
    // Load config, add link, save — all within the existing lock scope
    let mut config = crate::config::load(&ctx.managed_root)?;
    if !config.settings.links.contains(&target_name) {
        config.settings.links.push(target_name.clone());
        crate::config::save(&ctx.managed_root, &config)?;
    }

    // Output
    // ... print success/info/json
    Ok(0)
}
```

### scan_link_target()

```rust
fn scan_link_target(
    link_path: &Path,
    expected_symlink_target: &Path,
    managed_subdir: &Path,
) -> ScanResult {
    // Check if anything exists at link_path
    if link_path.symlink_metadata().is_err() {
        return ScanResult::Empty;
    }

    // Check if it's a symlink
    if let Ok(actual_target) = link_path.read_link() {
        // Use canonicalize for comparison — textually different but semantically
        // identical paths (e.g., ../.agents/agents vs ../.agents/./agents) should match.
        // Both must succeed for AlreadyLinked.
        let actual_resolved = link_path.parent()
            .map(|p| p.join(&actual_target))
            .and_then(|p| p.canonicalize().ok());
        let expected_resolved = link_path.parent()
            .map(|p| p.join(expected_symlink_target))
            .and_then(|p| p.canonicalize().ok());

        match (actual_resolved, expected_resolved) {
            (Some(a), Some(b)) if a == b => return ScanResult::AlreadyLinked,
            _ => return ScanResult::ForeignSymlink { target: actual_target },
        }
    }

    // It's a real directory — scan recursively
    scan_dir_recursive(link_path, managed_subdir)
}
```

### scan_dir_recursive()

```rust
fn scan_dir_recursive(target_subdir: &Path, managed_subdir: &Path) -> ScanResult {
    let mut files_to_move = Vec::new();
    let mut conflicts = Vec::new();

    // Walk the target directory recursively
    for entry in walkdir::WalkDir::new(target_subdir)
        .into_iter()
        .filter_map(|e| e.ok())
    {
        let ft = entry.file_type();
        if ft.is_dir() {
            continue; // Directories are structural, handled during cleanup
        }

        let relative = entry.path().strip_prefix(target_subdir).unwrap();

        // Non-regular files (symlinks, fifos, sockets) → treat as conflict
        if !ft.is_file() {
            conflicts.push(ConflictInfo {
                relative_path: relative.to_path_buf(),
                target_hash: format!("<non-regular: {:?}>", ft),
                managed_hash: String::new(),
            });
            continue;
        }

        let managed_path = managed_subdir.join(relative);

        if !managed_path.exists() {
            // Unique file — can be moved
            files_to_move.push(relative.to_path_buf());
        } else if managed_path.is_file() {
            // Both exist as files — compare content
            let target_hash = hash_file(entry.path());
            let managed_hash = hash_file(&managed_path);
            if target_hash != managed_hash {
                conflicts.push(ConflictInfo {
                    relative_path: relative.to_path_buf(),
                    target_hash,
                    managed_hash,
                });
            }
            // If hashes match, file is identical — skip
        } else {
            // Type mismatch (file in target, dir in managed or vice versa)
            conflicts.push(ConflictInfo {
                relative_path: relative.to_path_buf(),
                target_hash: "file".to_string(),
                managed_hash: "directory".to_string(),
            });
        }
    }

    if !conflicts.is_empty() {
        ScanResult::ConflictedDir { conflicts }
    } else {
        ScanResult::MergeableDir { files_to_move }
    }
}
```

### merge_and_link()

```rust
fn merge_and_link(
    link_path: &Path,      // e.g. .claude/agents/
    link_target: &Path,    // e.g. ../.agents/agents
    managed_subdir: &Path, // e.g. .agents/agents/
    files_to_move: &[PathBuf],
) -> Result<(), MarsError> {
    // Move unique files into managed root (copy+delete for cross-fs safety)
    for relative in files_to_move {
        let src = link_path.join(relative);
        let dst = managed_subdir.join(relative);

        // Create parent dirs in managed root if needed
        if let Some(parent) = dst.parent() {
            std::fs::create_dir_all(parent)?;
        }

        std::fs::copy(&src, &dst).map_err(|e| MarsError::Link {
            target: link_path.display().to_string(),
            message: format!("failed to copy {}: {e}", relative.display()),
        })?;
        std::fs::remove_file(&src)?;
    }

    // Remove remaining files (identical copies we skipped during scan)
    // and clean up directory tree bottom-up
    remove_dir_contents_and_tree(link_path)?;

    // Create symlink
    create_symlink(link_path, link_target)
}

/// Remove all remaining files in a directory, then remove empty dirs bottom-up.
/// Uses remove_dir (not remove_dir_all) so non-empty dirs fail safely.
fn remove_dir_contents_and_tree(dir: &Path) -> Result<(), MarsError> {
    // First, remove all regular files
    for entry in walkdir::WalkDir::new(dir)
        .into_iter()
        .filter_map(|e| e.ok())
        .filter(|e| e.file_type().is_file())
    {
        std::fs::remove_file(entry.path())?;
    }

    // Then, remove empty directories bottom-up (deepest first)
    let mut dirs: Vec<_> = walkdir::WalkDir::new(dir)
        .into_iter()
        .filter_map(|e| e.ok())
        .filter(|e| e.file_type().is_dir())
        .map(|e| e.into_path())
        .collect();
    dirs.sort_by(|a, b| b.cmp(a)); // Reverse order = deepest first

    for d in dirs {
        // remove_dir fails if non-empty — that's the safety net
        let _ = std::fs::remove_dir(&d);
    }

    Ok(())
}
```

### normalize_link_target()

```rust
fn normalize_link_target(target: &str) -> Result<String, MarsError> {
    let normalized = target.trim_end_matches('/').trim_end_matches('\\');
    if normalized.contains('/') || normalized.contains('\\') {
        return Err(MarsError::Link {
            target: target.to_string(),
            message: "link target must be a directory name, not a path".to_string(),
        });
    }
    if normalized.is_empty() {
        return Err(MarsError::Link {
            target: target.to_string(),
            message: "link target cannot be empty".to_string(),
        });
    }
    Ok(normalized.to_string())
}
```

## Dependencies

- **Requires**: Phase 1 (MarsError::Link), Phase 2 (MarsContext), Phase 3 (mutate_config)
- **Produces**: Fully functional `mars link` with conflict resolution
- **Independent of**: Phase 5

## New Dependencies (Cargo.toml)

- `walkdir` — recursive directory traversal (may already be a dependency; check first)

## Verification Criteria

- [ ] `cargo build` succeeds
- [ ] `cargo test` passes
- [ ] Scenario 1: `mars link .test` on empty dir → creates symlinks
- [ ] Scenario 2: re-running → "already linked" info
- [ ] Scenario 3: symlink pointing elsewhere → error with target path shown
- [ ] Scenario 4: dir with unique files → files moved to managed root, symlink created
- [ ] Scenario 5: dir with conflicting files → error, zero mutations, all conflicts listed
- [ ] Scenario 6: `--force` → replaces whatever exists
- [ ] Unlink: only removes symlinks pointing to this root
- [ ] Unlink: warns on foreign symlinks
- [ ] Normalize: rejects paths with `/`, strips trailing slash
- [ ] Config: link persisted in settings.links under sync lock

## Agent Staffing

**Risk**: High — core feature, complex algorithm, filesystem mutations.
- **Coder**: Strong reasoning model (gpt-5.3-codex or equivalent)
- **Reviewers**: 2 — correctness focus + security/filesystem focus
- **Verifier**: Yes — tests, type check, lint
