# F8: Surface Frontmatter Rewrite Errors

## Problem

`src/sync/target.rs:340`:
```rust
Err(_) => {}
```

Silently swallows frontmatter rewrite errors in `rewrite_skill_refs()`. If a file can't be parsed, the agent keeps its original skill references, which may point to pre-rename names that no longer exist on disk.

## Design

Return a `Vec<String>` of warnings from `rewrite_skill_refs()`. The caller (`src/sync/mod.rs`) logs them to stderr.

Change signature:
```rust
pub fn rewrite_skill_refs(
    target: &mut TargetState,
    renames: &[RenameAction],
    graph: &ResolvedGraph,  // was _graph
) -> Result<Vec<String>, MarsError> {
```

Replace `Err(_) => {}` with:
```rust
Err(e) => {
    warnings.push(format!(
        "warning: could not rewrite skill refs in {}: {e}",
        source_path.display()
    ));
}
```

In `src/sync/mod.rs`, after calling `rewrite_skill_refs()`:
```rust
let rewrite_warnings = target::rewrite_skill_refs(&mut target_state, &renames, &graph)?;
for w in &rewrite_warnings {
    eprintln!("{w}");
}
```

This is informational — warnings don't fail the sync. The agent installs with original references, and `mars doctor` will catch the broken skill reference post-sync.
