# Phase 3: Sync Crash Tolerance (F12)

## Scope

Make the sync pipeline tolerant of partial state from a prior crash, WITHOUT reordering the config/apply/lock steps.

The original design proposed moving config save to after apply. **This was rejected by review** — `mars sync` runs with `mutation: None`, so it can't replay the original mutation if config isn't saved. The current order (save config first) is correct.

The fix: make `check_unmanaged_collisions` tolerant of partially-installed files from a prior crash. When a planned install targets a file that already exists on disk with the same content, it's a partial prior install — skip the collision error.

## Files to Modify

### `src/sync/target.rs` — `check_unmanaged_collisions()`

Find the collision check where a planned install would overwrite a file on disk that isn't tracked in the lock. Add a hash comparison:

```rust
// When file exists on disk but not in lock, and we plan to install it:
// Check if the existing file matches what we'd install
let disk_hash = crate::hash::compute_hash(&disk_path, item_kind).ok();
let planned_hash = Some(&planned_item.checksum);
if disk_hash.as_ref() == Some(planned_hash) {
    // Content matches — this is a partial prior install, safe to overwrite
    continue;
}
// Otherwise: genuine unmanaged collision, error as before
```

**Note:** The exact API for accessing `planned_item.checksum` needs to be verified against the actual `TargetItem` struct. The coder should inspect `src/sync/target.rs` to find the right field names.

## Dependencies

- Independent of Phase 1, 2, 4, and 5.

## Verification Criteria

- [ ] `cargo test` passes
- [ ] `cargo clippy --all-targets --all-features` clean
- [ ] Add test: simulate partial install (file on disk, not in lock, same content as planned) → sync succeeds without collision error
- [ ] Add test: genuine unmanaged file (different content) → sync still errors
