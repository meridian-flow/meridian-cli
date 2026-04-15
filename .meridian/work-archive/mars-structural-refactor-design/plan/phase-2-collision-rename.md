# Phase 2: Fix Collision Rename for Cross-Package Deps (F15)

## Scope
Use dependency graph in `rewrite_skill_refs()` to find the correct renamed skill for cross-package dependencies instead of falling back to `entries.first()`.

## Files to Modify
- `src/sync/target.rs` — update `rewrite_skill_refs()` (lines 319-327)

## Dependencies
- Independent of Phase 1 (different code paths)

## Implementation Notes

In `rewrite_skill_refs()`, rename `_graph` to `graph`. Replace the fallback logic:

**Before:**
```rust
let selected = entries
    .iter()
    .find(|(_, source)| source == &source_name)
    .or_else(|| entries.first());
```

**After:**
```rust
let agent_deps: &[SourceName] = graph.nodes.get(&source_name)
    .map(|n| n.deps.as_slice())
    .unwrap_or(&[]);

let selected = entries
    .iter()
    .find(|(_, source)| source == &source_name)
    .or_else(|| entries.iter().find(|(_, source)| agent_deps.contains(source)));
```

## Test

Add a test in `src/sync/target.rs` tests module that sets up:
- Source A with agent referencing skill "planning" (with dep on source B)
- Source B providing skill "planning"
- Source C providing skill "planning"
- Collision forces rename to `planning__org_b` and `planning__org_c`
- Verify agent from A gets `planning__org_b` (its dependency), not `planning__org_c`

Use the existing `make_source_tree()` and `make_graph_and_config()` test helpers. Add `deps` to the ResolvedNode for source A.

## Verification Criteria
- [ ] `cargo test` passes
- [ ] `cargo clippy --all-targets --all-features` clean
- [ ] No `_graph` unused parameter warning
- [ ] New test covers cross-package skill rename selection
