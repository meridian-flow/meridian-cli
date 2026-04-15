# Phase 3: Resolve Lock and Conflict-Marker Cleanup

## Task

Two changes in /home/jimyao/gitrepos/mars-agents/:

### 1. Add sync lock to mars resolve (R2)

In `src/cli/resolve_cmd.rs`, acquire the sync advisory lock at the top of `run()` before any lock file operations. Pattern matches `sync/mod.rs`.

```rust
pub fn run(args: &ResolveArgs, ctx: &super::MarsContext, json: bool) -> Result<i32, MarsError> {
    let mars_dir = ctx.project_root.join(".mars");
    let lock_path = mars_dir.join("sync.lock");
    let _sync_lock = crate::fs::FileLock::acquire(&lock_path)?;

    let mut lock = crate::lock::load(&ctx.project_root)?;
    // ... existing logic unchanged ...
}
```

### 2. Consolidate has_conflict_markers (REF-02)

Three implementations exist:
1. `merge/mod.rs::has_conflict_markers(content: &[u8])` — correct, line-start aware
2. `cli/resolve_cmd.rs` — duplicate, string-based, naive
3. `cli/list.rs` — duplicate, string-based, naive

Make merge::has_conflict_markers pub (if not already). Add a file-level wrapper:

```rust
// In merge/mod.rs, add:
pub fn file_has_conflict_markers(path: &Path) -> bool {
    std::fs::read(path)
        .map(|content| has_conflict_markers(&content))
        .unwrap_or(false)
}
```

Then replace the duplicates in `cli/resolve_cmd.rs` and `cli/list.rs` with calls to `crate::merge::file_has_conflict_markers(path)`.

## Files to Touch

- /home/jimyao/gitrepos/mars-agents/src/cli/resolve_cmd.rs
- /home/jimyao/gitrepos/mars-agents/src/cli/list.rs
- /home/jimyao/gitrepos/mars-agents/src/merge/mod.rs

## Verification

Run from /home/jimyao/gitrepos/mars-agents/:
```bash
cargo build && cargo test && cargo clippy && cargo fmt --check
```

## EARS Claims: LOCK-07, LOCK-08, LOCK-09
