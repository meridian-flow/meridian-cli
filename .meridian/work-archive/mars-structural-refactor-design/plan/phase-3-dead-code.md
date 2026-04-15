# Phase 3: Dead Code Cleanup

## Scope
Remove dead `check_collisions()` and `build()` functions from target.rs. Remove dead `DepSpec.items` field from manifest/mod.rs. Migrate tests to use the production code path.

## Files to Modify
- `src/sync/target.rs` — delete `check_collisions()` (lines 117-157), delete `build()` (lines 51-111), update 8 tests
- `src/manifest/mod.rs` — remove `items` field from `DepSpec`, update test

## Dependencies
- Should come after Phase 2 since Phase 2 touches `rewrite_skill_refs()` in the same file

## Implementation Notes

### Delete `build()`
Remove the function. For each test that calls `build(&graph, &config)`, change to:
```rust
let (target, renames) = build_with_collisions(&graph, &config).unwrap();
// renames will be empty for single-source tests
```

Tests affected (all in `src/sync/target.rs` mod tests):
- `build_single_source_no_filter` (line 789)
- unnamed rename mapping test (line 814)
- `build_with_agents_filter` test (line 1015)
- `build_with_exclude_filter` (line 1034)
- `build_target_items_have_correct_hashes` (line 1046)
- `unmanaged_disk_path_collision_errors` (line 1062)
- `unmanaged_collision_skipped_when_hash_matches` (line 1087)
- `unmanaged_collision_still_errors_on_different_content` (line 1109)

For each, also add `assert!(renames.is_empty())` to verify no spurious collisions.

### Delete `check_collisions()`
Remove the entire function. It has no callers.

### Remove `DepSpec.items`
In `src/manifest/mod.rs`:
1. Remove `pub items: Option<Vec<ItemName>>` from `DepSpec` struct
2. In `parse_valid_manifest_with_deps` test: remove `items = ["coder", "reviewer"]` from test TOML, remove the assertion on `base_dep.items`
3. In `roundtrip_manifest` test: remove the `items: Some(vec!["agent1".into()])` from the test `DepSpec` construction

## Verification Criteria
- [ ] `cargo test` passes
- [ ] `cargo clippy --all-targets --all-features` clean — no dead code warnings
- [ ] `build()` function gone from target.rs
- [ ] `check_collisions()` function gone from target.rs
- [ ] `DepSpec` no longer has `items` field
