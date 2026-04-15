# Phase 4b: Symlink-Aware Scanning (F3)

## Scope

Add symlink detection and skipping to the scanning loops in check.rs, doctor.rs, and link.rs. Different policies per command.

## Files to Modify

### `src/cli/mod.rs` — shared helper

Add a public `is_symlink(path: &Path) -> bool` helper:

```rust
/// Check if a path is a symlink (uses symlink_metadata, doesn't follow).
pub fn is_symlink(path: &Path) -> bool {
    path.symlink_metadata()
        .map(|m| m.file_type().is_symlink())
        .unwrap_or(false)
}
```

### `src/cli/check.rs` — skip + warn

In both scanning loops (agents and skills), before processing each entry:

```rust
if super::is_symlink(&path) {
    warnings.push(format!(
        "skipping symlinked {} `{}` — source packages should not contain symlinks",
        kind, name
    ));
    continue;
}
```

Where `kind` is "agent" or "skill" and `name` is the filename/dirname.

### `src/cli/doctor.rs` — skip unexpected symlinks

In both scanning loops, before processing:

```rust
if super::is_symlink(&path) {
    issues.push(format!(
        "skipping symlinked {} `{}` — individual symlinks in managed dirs are not validated",
        kind, name
    ));
    continue;
}
```

**Important:** This does NOT affect `check_link_health()` — that function validates top-level directory symlinks (`.claude/agents → .agents/agents`), which are mars-created. The new scanning skip handles individual files/dirs within `agents/` and `skills/`.

### `src/cli/link.rs` — `scan_dir_recursive()`

Add `.follow_links(false)` and skip symlink entries (informational, not blocking):

```rust
for entry in walkdir::WalkDir::new(target_subdir)
    .follow_links(false)  // NEW: don't follow symlinks
    .into_iter()
    .filter_map(|e| e.ok())
{
    let ft = entry.file_type();
    if ft.is_dir() {
        continue;
    }
    if ft.is_symlink() {
        // Skip — don't follow, don't treat as conflict
        // Symlinks survive merge-and-link (we only remove regular files)
        continue;
    }
    // ... existing file processing unchanged ...
}
```

## Dependencies

- Should run after Phase 4a (both touch mod.rs)
- Independent of Phases 1-3 and 5

## Patterns to Follow

Look at the existing `scan_link_target` in link.rs for how symlinks are detected via `read_link()`. The new helper uses `symlink_metadata()` which is the standard Rust approach.

## Verification Criteria

- [ ] `cargo test` passes
- [ ] `cargo clippy --all-targets --all-features` clean
- [ ] Add test: symlinked agent file → `mars check` warns and skips
- [ ] Add test: symlinked skill dir → `mars check` warns and skips
- [ ] Add test: symlinked entry in doctor scan → reports and skips
- [ ] Add test: symlink in link target dir → ignored (not a conflict)
- [ ] Existing scan tests unchanged
