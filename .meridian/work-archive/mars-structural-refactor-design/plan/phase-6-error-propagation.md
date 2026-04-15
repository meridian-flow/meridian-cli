# Phase 6: Surface Frontmatter Rewrite Errors (F8)

## Scope
Replace silent `Err(_) => {}` in `rewrite_skill_refs()` with warning collection.

## Files to Modify
- `src/sync/target.rs` — change `rewrite_skill_refs()` return type to `Result<Vec<String>, MarsError>`, replace swallowed error
- `src/sync/mod.rs` — log warnings from `rewrite_skill_refs()` to stderr

## Dependencies
- Must come after Phase 2 (which also modifies `rewrite_skill_refs()`)

## Implementation Notes

### target.rs
Change signature:
```rust
pub fn rewrite_skill_refs(
    target: &mut TargetState,
    renames: &[RenameAction],
    graph: &ResolvedGraph,
) -> Result<Vec<String>, MarsError> {
```

Add `let mut warnings = Vec::new();` at top. Replace:
```rust
Err(_) => {}
```
With:
```rust
Err(e) => {
    warnings.push(format!(
        "warning: could not rewrite skill refs in {}: {e}",
        source_path.display()
    ));
}
```

Return `Ok(warnings)` at end.

### mod.rs
After the `rewrite_skill_refs` call (around line 173):
```rust
let rewrite_warnings = target::rewrite_skill_refs(&mut target_state, &renames, &graph)?;
for w in &rewrite_warnings {
    eprintln!("{w}");
}
```

## Verification Criteria
- [ ] `cargo test` passes
- [ ] `cargo clippy --all-targets --all-features` clean
- [ ] No `Err(_) => {}` in rewrite_skill_refs
