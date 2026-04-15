# Phase 4a: Symlink Containment in Root Discovery (F1)

## Scope

Add containment validation in `find_agents_root` so auto-discovered managed roots that resolve outside the project tree are rejected.

## Files to Modify

### `src/cli/mod.rs` — `find_agents_root()`

1. Canonicalize `cwd` before the walk-up loop (catches ancestor symlinks)
2. After `MarsContext::new(candidate)`, verify `ctx.managed_root.starts_with(dir)`
3. Error with clear message suggesting `--root` if intentional

See [symlink-containment.md](../design/symlink-containment.md) §F1 for the full code.

Key: the walk-up loop variable `dir` now starts from `cwd_canon` (canonicalized cwd), not raw `cwd`. This means all path comparisons are against real paths, catching both `.agents/` symlinks and ancestor-directory symlinks.

## Dependencies

None — can run in Round 1.

## Verification Criteria

- [ ] `cargo test` passes
- [ ] `cargo clippy --all-targets --all-features` clean
- [ ] Add test: symlinked `.agents/` pointing outside project → `find_agents_root` returns error
- [ ] Add test: normal `.agents/` (not symlinked) → works as before
- [ ] Add test: `--root` with path outside project → succeeds (bypass)
- [ ] Existing `find_root_*` tests still pass
